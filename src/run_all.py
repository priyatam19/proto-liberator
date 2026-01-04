#!/usr/bin/env python3
"""
Orchestrator - run the proto-liberator pipeline end-to-end.

This script is intentionally conservative: it does not run libErator analysis.
Instead, it consumes libErator outputs (conditions/apis/driver meta) and:

  schema -> nanopb bindings -> harness -> (optional) seeds -> (optional) build -> (optional) fuzz

It supports both schema contracts:
  - v1: fixed-sequence harness (driver.meta api_sequence/api_multiset)
  - v2: dynamic dispatch “super harness” (Action.oneof + repeated actions)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class Cmd:
    argv: List[str]
    cwd: Optional[Path] = None
    env: Optional[dict] = None

    def to_shell(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(cmd: Cmd, *, dry_run: bool) -> None:
    prefix = "[Orch:DRY]" if dry_run else "[Orch]"
    print(f"{prefix} {cmd.to_shell()}")
    if dry_run:
        return
    subprocess.check_call(
        cmd.argv,
        cwd=str(cmd.cwd) if cmd.cwd else None,
        env=cmd.env,
    )


def _write_json(path: Path, obj: object, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[Orch:DRY] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def _resolve_python(python: str) -> str:
    return python or sys.executable


def _rewrite_flag_values_starting_with_dash(argv: List[str], *, flag: str) -> List[str]:
    """
    argparse treats tokens starting with '-' as new options, so `--flag -foo` is ambiguous.
    Rewrite `--flag -foo` into `--flag=-foo` for better UX when passing clang-style flags.
    """

    rewritten: List[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == flag and i + 1 < len(argv):
            value = argv[i + 1]
            if value.startswith("-") and not value.startswith("--") and value != "-":
                rewritten.append(f"{flag}={value}")
                i += 2
                continue
        rewritten.append(argv[i])
        i += 1
    return rewritten


def _target_libs_for_profile(target_libs: List[str]) -> List[str]:
    """
    llvm-cov only reports coverage for code compiled with:
      -fprofile-instr-generate -fcoverage-mapping

    If a target is linked as a prebuilt archive (.a), we cannot retroactively add
    coverage mapping to its already-compiled objects. Many libErator builds also
    provide LLVM bitcode next to the archive (e.g. libcjson.a.bc). When building
    the *_profile.bin, prefer that bitcode sibling so the library itself is
    instrumented and appears in coverage reports.
    """
    out: List[str] = []
    for p in target_libs:
        if p.endswith(".a") and os.path.exists(p + ".bc"):
            out.append(p + ".bc")
        else:
            out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Proto-libErator Orchestrator")

    parser.add_argument("--library", required=True, help="Library name (e.g., cjson)")
    parser.add_argument("--conditions", required=True, help="Path to libErator conditions.json")
    parser.add_argument("--apis", required=True, help="Path to libErator apis_clang.json (JSONL)")
    parser.add_argument(
        "--minimum-apis",
        default=None,
        help="Optional apis_minimized.txt (one function per line) to restrict schema/harness/seeds",
    )
    parser.add_argument(
        "--apipass-dir",
        default=None,
        help="Optional apipass directory (defaults to parent of conditions.json)",
    )
    parser.add_argument("--driver", help="Path to libErator driver.meta (required for v1; optional for v2)")
    parser.add_argument("--out-dir", required=True, help="Output directory (created if missing)")

    parser.add_argument("--schema-mode", choices=["v1", "v2"], default="v2", help="Schema contract version")
    parser.add_argument("--mutation-mode", choices=["nanopb", "lpm"], default="lpm", help="Mutation engine")
    parser.add_argument("--max-actions", type=int, default=64, help="(v2) max Action entries")
    parser.add_argument("--max-calls-per-api", type=int, default=4, help="(v1) max params per API")
    parser.add_argument("--max-bytes-size", type=int, default=65536, help="Nanopb max_size for bytes fields")

    parser.add_argument("--package", default=None, help="Protobuf package prefix for generated C structs")
    parser.add_argument("--header", action="append", default=[], help="Extra header include (repeatable)")
    parser.add_argument(
        "--harness-style",
        choices=["strict", "simple"],
        default="strict",
        help="Validation strictness for generated harness",
    )

    parser.add_argument("--python", default=None, help="Python interpreter for generator scripts")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")

    parser.add_argument("--nanopb-dir", default=None, help="Path to nanopb checkout (default: external/nanopb)")

    parser.add_argument("--generate-seeds", action="store_true", help="(v2) Generate an initial seed corpus")
    parser.add_argument("--seeds-dir", default=None, help="Seed output dir (default: <out-dir>/corpus)")
    parser.add_argument("--num-seeds", type=int, default=64, help="(v2) number of seeds")
    parser.add_argument("--seed-max-len", type=int, default=16, help="(v2) max actions per seed")
    parser.add_argument("--seed-rng", type=int, default=0, help="(v2) deterministic RNG seed")
    parser.add_argument(
        "--seed-constants-json",
        default=None,
        help="Optional JSON mapping function -> {field_name: value} for seed generation",
    )

    parser.add_argument("--build", action="store_true", help="Compile a libFuzzer binary")
    parser.add_argument(
        "--build-profile",
        action="store_true",
        help="Compile a coverage-instrumented binary for llvm-cov (writes <out-dir>/<library>_profile.bin)",
    )
    parser.add_argument(
        "--profile-no-bitcode",
        action="store_true",
        help="Do not prefer `*.a.bc` when building *_profile.bin (useful when the bitcode requires unsupported CPU features).",
    )
    parser.add_argument("--fuzz", action="store_true", help="Run the fuzzer after build")
    parser.add_argument(
        "--detect-leaks",
        action="store_true",
        help="Enable LeakSanitizer detection (default: disabled via -detect_leaks=0)",
    )
    parser.add_argument("--clang", default="clang", help="clang path")
    parser.add_argument("--cc-arg", action="append", default=[], help="Extra clang args (repeatable)")
    parser.add_argument("--target-include", action="append", default=[], help="Add -I<dir> (repeatable)")
    parser.add_argument("--target-lib", action="append", default=[], help="Link a library/archive (repeatable)")
    parser.add_argument("--extra-src", action="append", default=[], help="Compile extra .c/.cc files (repeatable)")
    parser.add_argument(
        "--profile-extra-src",
        action="append",
        default=[],
        help="Compile extra sources into *_profile.bin only (repeatable)",
    )
    parser.add_argument(
        "--profile-keep-target-lib",
        action="store_true",
        help="Also link --target-lib into *_profile.bin (useful when --profile-extra-src does not replace the target)",
    )

    argv = sys.argv[1:]
    argv = _rewrite_flag_values_starting_with_dash(argv, flag="--cc-arg")
    args = parser.parse_args(argv)

    root = _repo_root()
    src_dir = root / "src"
    out_dir = Path(args.out_dir).resolve()
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    python = _resolve_python(args.python)
    safe_lib = re.sub(r"[^A-Za-z0-9_]+", "_", str(args.library))
    if not safe_lib or safe_lib[0].isdigit():
        safe_lib = f"lib_{safe_lib}"
    package = args.package or f"{safe_lib}_fuzzer"

    conditions = Path(args.conditions).resolve()
    apis = Path(args.apis).resolve()
    driver = Path(args.driver).resolve() if args.driver else None

    if args.mutation_mode == "lpm" and args.schema_mode != "v2":
        raise SystemExit("--mutation-mode lpm currently requires --schema-mode v2")

    schema_proto = out_dir / f"{args.library}.{args.schema_mode}.proto"
    bindings_dir = out_dir / "bindings"
    harness_c = out_dir / ("harness.cc" if args.mutation_mode == "lpm" else "harness.c")
    driver_meta_path = out_dir / "driver.meta.json"

    nanopb_dir = Path(args.nanopb_dir).resolve() if args.nanopb_dir else (root / "external" / "nanopb")
    nanopb_protoc = nanopb_dir / "generator" / "protoc"
    if (args.build or args.fuzz) and args.mutation_mode == "nanopb":
        if not nanopb_protoc.exists():
            raise SystemExit(f"nanopb protoc wrapper not found: {nanopb_protoc}")

    # 0) Driver meta for wrapper generator
    if args.schema_mode == "v1" and not driver:
        raise SystemExit("--driver is required for --schema-mode v1")

    wrapper_meta = {"headers": list(args.header)}
    if driver:
        if driver.exists() and not args.dry_run:
            wrapper_meta.update(json.loads(driver.read_text()))
    if args.schema_mode == "v2":
        wrapper_meta.setdefault("api_sequence", [])
    _write_json(driver_meta_path, wrapper_meta, dry_run=args.dry_run)

    # 1) Schema
    schema_argv: List[str] = [
        python,
        str(src_dir / "proto_generator.py"),
        "--conditions",
        str(conditions),
        "--apis",
        str(apis),
        "--output",
        str(schema_proto),
        "--library",
        args.library,
        "--schema-mode",
        args.schema_mode,
        "--mutation-mode",
        args.mutation_mode,
        "--max-bytes-size",
        str(args.max_bytes_size),
        "--max-calls-per-api",
        str(args.max_calls_per_api),
        "--max-actions",
        str(args.max_actions),
    ]
    if args.minimum_apis:
        schema_argv += ["--minimum-apis", str(Path(args.minimum_apis).resolve())]
    if args.apipass_dir:
        schema_argv += ["--apipass-dir", str(Path(args.apipass_dir).resolve())]
    _run(Cmd(schema_argv), dry_run=args.dry_run)

    # 2) Bindings
    if not args.dry_run:
        bindings_dir.mkdir(parents=True, exist_ok=True)
    
    if args.mutation_mode == "lpm":
        # Use LPM's protoc
        lpm_protoc = root / "external/libprotobuf-mutator/build/external.protobuf/bin/protoc"
        if not lpm_protoc.exists():
             # Fallback or error? Let's assume it exists if we are in LPM mode
             print(f"Warning: LPM protoc not found at {lpm_protoc}, trying system protoc")
             lpm_protoc = Path("protoc")

        bindings_cmd = Cmd(
            [
                str(lpm_protoc),
                f"--cpp_out={bindings_dir}",
                f"-I{out_dir}",
                str(schema_proto),
            ]
        )
    else:
        # Nanopb
        bindings_cmd = Cmd(
            [
                str(nanopb_protoc),
                f"--nanopb_out={bindings_dir}",
                f"-I{out_dir}",
                str(schema_proto),
            ]
        )
    _run(bindings_cmd, dry_run=args.dry_run)

    # 3) Harness
    wrapper_argv: List[str] = [
        python,
        str(src_dir / "wrapper_generator.py"),
        "--proto",
        str(schema_proto),
        "--driver",
        str(driver_meta_path),
        "--conditions",
        str(conditions),
        "--apis",
        str(apis),
        "--output",
        str(harness_c),
        "--package",
        package,
        "--schema-mode",
        args.schema_mode,
        "--mutation-mode",
        args.mutation_mode,
        "--max-actions",
        str(args.max_actions),
        "--harness-style",
        args.harness_style,
        *sum([["--header", h] for h in args.header], []),
    ]
    if args.minimum_apis:
        wrapper_argv += ["--minimum-apis", str(Path(args.minimum_apis).resolve())]
    if args.apipass_dir:
        wrapper_argv += ["--apipass-dir", str(Path(args.apipass_dir).resolve())]
    _run(Cmd(wrapper_argv), dry_run=args.dry_run)

    # 4) Seeds (v2)
    seeds_dir = Path(args.seeds_dir).resolve() if args.seeds_dir else (out_dir / "corpus")
    if args.generate_seeds:
        if args.schema_mode != "v2":
            raise SystemExit("--generate-seeds is only supported for --schema-mode v2")
        seed_argv: List[str] = [
            python,
            str(src_dir / "seed_generator.py"),
            "--conditions",
            str(conditions),
            "--output-dir",
            str(seeds_dir),
            "--num-seeds",
            str(args.num_seeds),
            "--max-len",
            str(args.seed_max_len),
            "--rng-seed",
            str(args.seed_rng),
            "--driver",
            str(driver_meta_path),
            "--mode",
            "wire",
        ]
        if args.minimum_apis:
            seed_argv += ["--minimum-apis", str(Path(args.minimum_apis).resolve())]
        if args.apipass_dir:
            seed_argv += ["--apipass-dir", str(Path(args.apipass_dir).resolve())]
        if args.seed_constants_json:
            seed_argv += ["--constants-json", str(Path(args.seed_constants_json).resolve())]
        _run(Cmd(seed_argv), dry_run=args.dry_run)

    # 5) Build
    if args.fuzz:
        args.build = True
    fuzzer_bin = out_dir / f"{args.library}_fuzzer.bin"
    profile_bin = out_dir / f"{args.library}_profile.bin"

    if args.build or args.build_profile:
        target_libs_profile = (
            list(args.target_lib) if args.profile_no_bitcode else _target_libs_for_profile(list(args.target_lib))
        )
        if args.mutation_mode == "lpm":
            # LPM Build
            pb_cc = bindings_dir / f"{args.library}.{args.schema_mode}.pb.cc"
            
            lpm_root = root / "external/libprotobuf-mutator"
            lpm_build = lpm_root / "build"
            
            # Gather all static libs from LPM build
            # We need: libprotobuf-mutator-libfuzzer.a, libprotobuf-mutator.a, libprotobuf.a, and absl libs
            # A simple approach is to find all .a files in lpm_build
            # But order matters. libprotobuf-mutator-libfuzzer -> libprotobuf-mutator -> libprotobuf -> absl
            
            libs = []
            libs.append(str(lpm_build / "src/libfuzzer/libprotobuf-mutator-libfuzzer.a"))
            libs.append(str(lpm_build / "src/libprotobuf-mutator.a"))
            libs.append(str(lpm_build / "external.protobuf/lib/libprotobuf.a"))
            
            # Add all other .a files in external.protobuf/lib (absl, etc)
            # We exclude libprotobuf.a (already added) and libprotoc.a (not needed for runtime)
            ext_lib_dir = lpm_build / "external.protobuf/lib"
            if ext_lib_dir.exists():
                for lib in ext_lib_dir.glob("*.a"):
                    if lib.name not in ["libprotobuf.a", "libprotoc.a", "libprotobuf-lite.a"]:
                        libs.append(str(lib))

            def _lpm_cc_base(*, with_asan: bool) -> List[str]:
                sanitize = "-fsanitize=fuzzer,address" if with_asan else "-fsanitize=fuzzer"
                return [
                    args.clang + "++",  # Use clang++
                    "-g",
                    "-O1",
                    sanitize,
                    "-fno-pie",
                    "-no-pie",
                    "-std=c++17",
                    f"-I{bindings_dir}",
                    f"-I{out_dir}",
                    f"-I{lpm_root}",  # For src/libfuzzer/libfuzzer_macro.h
                    f"-I{lpm_build}/external.protobuf/include",  # For google/protobuf
                ]

            def _lpm_sources() -> List[str]:
                return [
                    str(harness_c),
                    str(pb_cc),
                    *args.extra_src,
                ]

            profile_extra_objects: List[str] = []
            if args.build_profile and args.profile_extra_src:
                obj_dir = out_dir / "profile_objs"
                if not args.dry_run:
                    obj_dir.mkdir(parents=True, exist_ok=True)

                for src in args.profile_extra_src:
                    src_path = Path(src)
                    obj_path = obj_dir / (src_path.name + ".o")

                    is_cxx = src_path.suffix.lower() in {".cc", ".cpp", ".cxx"}
                    compiler = (args.clang + "++") if is_cxx else args.clang

                    cc: List[str] = [
                        compiler,
                        "-g",
                        "-O1",
                        "-c",
                        str(src_path),
                        "-o",
                        str(obj_path),
                        "-fprofile-instr-generate",
                        "-fcoverage-mapping",
                    ]
                    if is_cxx:
                        cc.append("-std=c++17")
                    for inc in args.target_include:
                        cc.append(f"-I{inc}")
                    cc.extend(args.cc_arg)
                    _run(Cmd(cc), dry_run=args.dry_run)
                    profile_extra_objects.append(str(obj_path))

            def _lpm_link(
                out_path: Path, *, extra_cflags: Optional[List[str]] = None, with_asan: bool = True
            ) -> None:
                cc: List[str] = _lpm_cc_base(with_asan=with_asan)
                for inc in args.target_include:
                    cc.append(f"-I{inc}")
                cc.extend(args.cc_arg)
                if extra_cflags:
                    cc.extend(extra_cflags)
                cc.extend(_lpm_sources())
                if out_path == profile_bin and profile_extra_objects:
                    cc.extend(profile_extra_objects)
                cc.extend(["-Wl,--start-group"])
                cc.extend(libs)
                cc.extend(["-Wl,--end-group"])
                cc.extend(["-lpthread", "-lz"])
                if out_path == profile_bin:
                    # If profile-only sources are provided, they usually replace the prebuilt target archive.
                    if args.profile_extra_src and not args.profile_keep_target_lib:
                        pass
                    else:
                        cc.extend(target_libs_profile)
                else:
                    cc.extend(args.target_lib)
                cc.extend(["-o", str(out_path)])
                _run(Cmd(cc), dry_run=args.dry_run)

            if args.build:
                _lpm_link(fuzzer_bin, with_asan=True)
            if args.build_profile:
                _lpm_link(
                    profile_bin,
                    extra_cflags=["-fprofile-instr-generate", "-fcoverage-mapping"],
                    with_asan=False,
                )

        else:
            # Nanopb Build
            pb_c = bindings_dir / f"{args.library}.{args.schema_mode}.pb.c"
            if not pb_c.exists() and not args.dry_run:
                # nanopb names output after the input proto stem
                pb_c = bindings_dir / f"{schema_proto.stem}.pb.c"

            def _nanopb_cc_base(*, with_asan: bool) -> List[str]:
                sanitize = "-fsanitize=fuzzer,address" if with_asan else "-fsanitize=fuzzer"
                return [
                    args.clang,
                    "-g",
                    "-O1",
                    sanitize,
                    "-fno-pie",
                    "-no-pie",
                    "-DPB_FIELD_32BIT",
                    f"-I{bindings_dir}",
                    f"-I{nanopb_dir}",
                    f"-I{out_dir}",
                ]

            def _nanopb_sources() -> List[str]:
                return [
                    str(harness_c),
                    str(pb_c),
                    str(nanopb_dir / "pb_common.c"),
                    str(nanopb_dir / "pb_decode.c"),
                    str(nanopb_dir / "pb_encode.c"),
                    *args.extra_src,
                ]

            profile_extra_objects: List[str] = []
            if args.build_profile and args.profile_extra_src:
                obj_dir = out_dir / "profile_objs"
                if not args.dry_run:
                    obj_dir.mkdir(parents=True, exist_ok=True)

                for src in args.profile_extra_src:
                    src_path = Path(src)
                    obj_path = obj_dir / (src_path.name + ".o")

                    compiler = args.clang
                    cc: List[str] = [
                        compiler,
                        "-g",
                        "-O1",
                        "-c",
                        str(src_path),
                        "-o",
                        str(obj_path),
                        "-fprofile-instr-generate",
                        "-fcoverage-mapping",
                    ]
                    for inc in args.target_include:
                        cc.append(f"-I{inc}")
                    cc.extend(args.cc_arg)
                    _run(Cmd(cc), dry_run=args.dry_run)
                    profile_extra_objects.append(str(obj_path))

            def _nanopb_link(
                out_path: Path, *, extra_cflags: Optional[List[str]] = None, with_asan: bool = True
            ) -> None:
                cc: List[str] = _nanopb_cc_base(with_asan=with_asan)
                for inc in args.target_include:
                    cc.append(f"-I{inc}")
                cc.extend(args.cc_arg)
                if extra_cflags:
                    cc.extend(extra_cflags)
                cc.extend(_nanopb_sources())
                if out_path == profile_bin and profile_extra_objects:
                    cc.extend(profile_extra_objects)

                if out_path == profile_bin:
                    if args.profile_extra_src and not args.profile_keep_target_lib:
                        pass
                    else:
                        cc.extend(target_libs_profile)
                else:
                    cc.extend(args.target_lib)
                cc.extend(["-o", str(out_path)])
                _run(Cmd(cc), dry_run=args.dry_run)

            if args.build:
                _nanopb_link(fuzzer_bin, with_asan=True)
            if args.build_profile:
                _nanopb_link(
                    profile_bin,
                    extra_cflags=["-fprofile-instr-generate", "-fcoverage-mapping"],
                    with_asan=False,
                )

    # 6) Fuzz
    if args.fuzz:
        artifacts_dir = out_dir / "artifacts"
        if not args.dry_run:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
        fuzz_argv: List[str] = [str(fuzzer_bin)]
        if args.generate_seeds:
            fuzz_argv.append(str(seeds_dir))
        if not args.detect_leaks:
            fuzz_argv.append("-detect_leaks=0")
        fuzz_argv.append(f"-artifact_prefix={artifacts_dir.as_posix()}/")
        fuzz_argv.extend(["-runs=100"])
        env = os.environ.copy()
        if not args.detect_leaks:
            opts = env.get("ASAN_OPTIONS", "")
            if "detect_leaks=" not in opts:
                env["ASAN_OPTIONS"] = (opts + ":" if opts else "") + "detect_leaks=0"
        _run(Cmd(fuzz_argv, cwd=out_dir, env=env), dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
