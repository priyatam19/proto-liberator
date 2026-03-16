#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "crash_decoder.sh"


class TestCrashDecoder(unittest.TestCase):
    def test_classifies_constraint_redirect_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir = root / "work"
            crash_dir = workdir / "artifacts"
            out_dir = workdir / "crashes"
            workdir.mkdir(parents=True, exist_ok=True)
            crash_dir.mkdir(parents=True, exist_ok=True)

            # Fake fuzzer: emits redirect marker when input contains "misuse".
            fuzzer = workdir / "demo_fuzzer.bin"
            fuzzer.write_text(
                "\n".join(
                    [
                        "#!/bin/bash",
                        "set -eu",
                        'inp="${@: -1}"',
                        'if grep -q "misuse" "${inp}"; then',
                        '  echo "PLB_CONSTRAINT_REDIRECTED=1" >&2',
                        "fi",
                        'echo "simulated crash" >&2',
                        "exit 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(fuzzer, os.stat(fuzzer).st_mode | stat.S_IXUSR)

            (crash_dir / "crash-a").write_text("misuse input", encoding="utf-8")
            (crash_dir / "crash-b").write_text("normal input", encoding="utf-8")

            subprocess.run(
                [
                    str(SCRIPT),
                    str(workdir),
                    "--crash-dir",
                    str(crash_dir),
                    "--out-dir",
                    str(out_dir),
                    "--fuzzer-bin",
                    str(fuzzer),
                    "--timeout-sec",
                    "2",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            self.assertTrue((out_dir / "constraint_misuse" / "crash-a").exists())
            self.assertTrue((out_dir / "genuine" / "crash-b").exists())
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["constraint_misuse"], 1)
            self.assertEqual(summary["genuine_bug"], 1)


if __name__ == "__main__":
    unittest.main()
