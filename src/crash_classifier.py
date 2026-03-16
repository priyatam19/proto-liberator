#!/usr/bin/env python3
"""
Classify crash artifacts into genuine bugs vs constraint-misuse crashes.

Classification rule:
  - replay output contains "PLB_CONSTRAINT_REDIRECTED=1" -> constraint_misuse
  - otherwise                                            -> genuine
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple


REDIRECT_MARKER = "PLB_CONSTRAINT_REDIRECTED=1"
CRASH_PREFIXES = ("crash-", "leak-", "timeout-", "oom-")


def _discover_fuzzer_bin(workdir: Path, explicit: str) -> Path:
    if explicit:
        candidate = Path(explicit).resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"fuzzer binary not found: {candidate}")

    bins = sorted(workdir.glob("*_fuzzer.bin"))
    if bins:
        return bins[0].resolve()
    raise FileNotFoundError(f"fuzzer binary not found under {workdir} (*_fuzzer.bin)")


def _discover_crash_dir(workdir: Path, explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    artifacts = workdir / "artifacts"
    if artifacts.is_dir():
        return artifacts.resolve()
    crashes = workdir / "crashes"
    if crashes.is_dir():
        return crashes.resolve()
    return workdir.resolve()


def _iter_crash_inputs(crash_dir: Path) -> List[Path]:
    if not crash_dir.is_dir():
        return []
    out: List[Path] = []
    for p in sorted(crash_dir.iterdir()):
        if not p.is_file():
            continue
        # Skip classifier sidecar/log files to avoid recursive reprocessing.
        if p.name.endswith((".exit_code.txt", ".timeout.txt", ".repro.log", ".json", ".txt", ".log")):
            continue
        if p.name.startswith(CRASH_PREFIXES):
            out.append(p)
    return out


def _safe_output_text(data: object) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _replay_once(
    *,
    fuzzer_bin: Path,
    crash_path: Path,
    timeout_sec: int,
) -> Tuple[int, str, bool]:
    argv = [str(fuzzer_bin), "-runs=1", "-detect_leaks=0", str(crash_path)]
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=max(1, int(timeout_sec)),
            check=False,
        )
        return int(proc.returncode), proc.stdout or "", False
    except subprocess.TimeoutExpired as exc:
        out = _safe_output_text(exc.stdout) + _safe_output_text(exc.stderr)
        return 124, out, True


def _classify_output(output: str) -> str:
    return "constraint_misuse" if REDIRECT_MARKER in output else "genuine"


def _write_summary(
    *,
    summary_path: Path,
    workdir: Path,
    fuzzer_bin: Path,
    crash_dir: Path,
    total: int,
    genuine: int,
    misuse: int,
    timeout_sec: int,
) -> None:
    summary = {
        "workdir": str(workdir),
        "fuzzer_bin": str(fuzzer_bin),
        "crash_dir": str(crash_dir),
        "total": int(total),
        "genuine": int(genuine),
        "genuine_bug": int(genuine),  # backward-compatible key name
        "constraint_misuse": int(misuse),
        "timeout_sec": int(timeout_sec),
        "marker": REDIRECT_MARKER,
        "generated_at_unix": int(time.time()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify_crashes(
    *,
    workdir: Path,
    fuzzer_bin: Path,
    crash_dir: Path,
    out_dir: Path,
    timeout_sec: int,
) -> Path:
    crash_inputs = _iter_crash_inputs(crash_dir)

    genuine_dir = out_dir / "genuine"
    misuse_dir = out_dir / "constraint_misuse"
    logs_dir = out_dir / "logs"
    genuine_dir.mkdir(parents=True, exist_ok=True)
    misuse_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    genuine = 0
    misuse = 0
    for crash_path in crash_inputs:
        rc, output, timed_out = _replay_once(
            fuzzer_bin=fuzzer_bin,
            crash_path=crash_path,
            timeout_sec=timeout_sec,
        )
        bucket = _classify_output(output)
        dst_root = misuse_dir if bucket == "constraint_misuse" else genuine_dir
        if bucket == "constraint_misuse":
            misuse += 1
        else:
            genuine += 1

        base = crash_path.name
        shutil.copy2(crash_path, dst_root / base)
        (dst_root / f"{base}.exit_code.txt").write_text(f"{rc}\n", encoding="utf-8")
        if timed_out:
            (dst_root / f"{base}.timeout.txt").write_text("1\n", encoding="utf-8")
        (logs_dir / f"{base}.repro.log").write_text(output, encoding="utf-8", errors="replace")

    summary_path = out_dir / "summary.json"
    _write_summary(
        summary_path=summary_path,
        workdir=workdir,
        fuzzer_bin=fuzzer_bin,
        crash_dir=crash_dir,
        total=len(crash_inputs),
        genuine=genuine,
        misuse=misuse,
        timeout_sec=timeout_sec,
    )
    return summary_path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify proto-liberator crash artifacts.")
    parser.add_argument("workdir", nargs="?", default=None, help="Work directory (contains *_fuzzer.bin and artifacts)")
    parser.add_argument("--workdir", dest="workdir_flag", default=None, help="Work directory (same as positional)")
    parser.add_argument("--crash-dir", default=None, help="Crash artifact directory (default: auto-detect from workdir)")
    parser.add_argument("--out-dir", default=None, help="Output dir (default: <workdir>/crashes)")
    parser.add_argument("--fuzzer-bin", default=None, help="Fuzzer binary path (default: first <workdir>/*_fuzzer.bin)")
    parser.add_argument("--timeout-sec", type=int, default=20, help="Per-replay timeout in seconds (default: 20)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    workdir_raw = args.workdir_flag or args.workdir
    if not workdir_raw:
        parser.error("workdir is required (positional or --workdir)")

    workdir = Path(workdir_raw).resolve()
    if not workdir.is_dir():
        print(f"[ERROR] workdir not found: {workdir}")
        return 2

    try:
        fuzzer_bin = _discover_fuzzer_bin(workdir, args.fuzzer_bin or "")
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 2

    crash_dir = _discover_crash_dir(workdir, args.crash_dir or "")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (workdir / "crashes")
    timeout_sec = max(1, int(args.timeout_sec))

    summary_path = classify_crashes(
        workdir=workdir,
        fuzzer_bin=fuzzer_bin,
        crash_dir=crash_dir,
        out_dir=out_dir,
        timeout_sec=timeout_sec,
    )

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        summary = {}

    print(
        "[CrashClassifier] "
        f"total={int(summary.get('total', 0))} "
        f"genuine={int(summary.get('genuine', 0))} "
        f"constraint_misuse={int(summary.get('constraint_misuse', 0))} "
        f"summary={summary_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
