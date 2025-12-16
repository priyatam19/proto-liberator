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


def main() -> int:
    parser = argparse.ArgumentParser(description="Proto-libErator Orchestrator")

    parser.add_argument("--library", required=True, help="Library name (e.g., cjson)")
    parser.add_argument("--conditions", required=True, help="Path to libErator conditions.json")
    parser.add_argument("--apis", required=True, help="Path to libErator apis_clang.json (JSONL)")
    parser.add_argument("--driver", help="Path to libErator driver.meta (required for v1; optional for v2)")
    parser.add_argument("--out-dir", required=True, help="Output directory (created if missing)")

    parser.add_argument("--schema-mode", choices=["v1", "v2"], default="v2", help="Schema contract version")
    parser.add_argument("--max-actions", type=int, default=64, help="(v2) max Action entries")
    parser.add_argument("--max-calls-per-api", type=int, default=4, help="(v1) max params per API")
    parser.add_argument("--max-bytes-size", type=int, default=65536, help="Nanopb max_size for bytes fields")

    parser.add_argument("--package", default=None, help="Protobuf package prefix for generated C structs")
    parser.add_argument("--header", action="append", default=[], help="Extra header include (repeatable)")

    parser.add_argument("--python", default=None, help="Python interpreter for generator scripts")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")

    parser.add_argument("--nanopb-dir", default=None, help="Path to nanopb checkout (default: external/nanopb)")

    parser.add_argument("--generate-seeds", action="store_true", help="(v2) Generate an initial seed corpus")
    parser.add_argument("--seeds-dir", default=None, help="Seed output dir (default: <out-dir>/corpus)")
    parser.add_argument("--num-seeds", type=int, default=64, help="(v2) number of seeds")
    parser.add_argument("--seed-max-len", type=int, default=16, help="(v2) max actions per seed")
    parser.add_argument("--seed-rng", type=int, default=0, help="(v2) deterministic RNG seed")

    parser.add_argument("--build", action="store_true", help="Compile a libFuzzer binary")
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

    args = parser.parse_args()

    root = _repo_root()
    src_dir = root / "src"
    out_dir = Path(args.out_dir).resolve()
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    python = _resolve_python(args.python)
    package = args.package or f"{args.library}_fuzzer"

    conditions = Path(args.conditions).resolve()
    apis = Path(args.apis).resolve()
    driver = Path(args.driver).resolve() if args.driver else None

    schema_proto = out_dir / f"{args.library}.{args.schema_mode}.proto"
    bindings_dir = out_dir / "bindings"
    harness_c = out_dir / "harness.c"
    driver_meta_path = out_dir / "driver.meta.json"

    nanopb_dir = Path(args.nanopb_dir).resolve() if args.nanopb_dir else (root / "external" / "nanopb")
    nanopb_protoc = nanopb_dir / "generator" / "protoc"
    if args.build or args.fuzz:
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
    schema_cmd = Cmd(
        [
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
            "--max-bytes-size",
            str(args.max_bytes_size),
            "--max-calls-per-api",
            str(args.max_calls_per_api),
            "--max-actions",
            str(args.max_actions),
        ]
    )
    _run(schema_cmd, dry_run=args.dry_run)

    # 2) Bindings (nanopb)
    if not args.dry_run:
        bindings_dir.mkdir(parents=True, exist_ok=True)
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
    wrapper_cmd = Cmd(
        [
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
            *sum([["--header", h] for h in args.header], []),
        ]
    )
    _run(wrapper_cmd, dry_run=args.dry_run)

    # 4) Seeds (v2)
    seeds_dir = Path(args.seeds_dir).resolve() if args.seeds_dir else (out_dir / "corpus")
    if args.generate_seeds:
        if args.schema_mode != "v2":
            raise SystemExit("--generate-seeds is only supported for --schema-mode v2")
        seed_cmd = Cmd(
            [
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
                "--mode",
                "wire",
            ]
        )
        _run(seed_cmd, dry_run=args.dry_run)

    # 5) Build
    if args.fuzz:
        args.build = True
    fuzzer_bin = out_dir / f"{args.library}_fuzzer.bin"

    if args.build:
        pb_c = bindings_dir / f"{args.library}.{args.schema_mode}.pb.c"
        if not pb_c.exists() and not args.dry_run:
            # nanopb names output after the input proto stem
            pb_c = bindings_dir / f"{schema_proto.stem}.pb.c"

        cc: List[str] = [
            args.clang,
            "-g",
            "-O1",
            "-fsanitize=fuzzer,address",
            "-fno-pie",
            "-no-pie",
            "-DPB_FIELD_32BIT",
            f"-I{bindings_dir}",
            f"-I{nanopb_dir}",
            f"-I{out_dir}",
        ]
        for inc in args.target_include:
            cc.append(f"-I{inc}")
        cc.extend(args.cc_arg)

        sources: List[str] = [
            str(harness_c),
            str(pb_c),
            str(nanopb_dir / "pb_common.c"),
            str(nanopb_dir / "pb_decode.c"),
            str(nanopb_dir / "pb_encode.c"),
            *args.extra_src,
        ]
        cc.extend(sources)
        cc.extend(args.target_lib)
        cc.extend(["-o", str(fuzzer_bin)])

        _run(Cmd(cc), dry_run=args.dry_run)

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
