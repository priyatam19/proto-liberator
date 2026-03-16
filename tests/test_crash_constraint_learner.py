#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "src" / "crash_constraint_learner.py"


class TestCrashConstraintLearner(unittest.TestCase):
    def test_learns_param_from_shadow_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir = root / "work"
            crashes = workdir / "crashes" / "genuine"
            workdir.mkdir(parents=True, exist_ok=True)
            crashes.mkdir(parents=True, exist_ok=True)

            proto = workdir / "demo.v2.proto"
            proto.write_text(
                "\n".join(
                    [
                        'syntax = "proto2";',
                        "message Foo_Params {",
                        "  optional uint32 param_0 = 1;",
                        "}",
                        "message Action {",
                        "  oneof action {",
                        "    Foo_Params foo = 1;",
                        "  }",
                        "}",
                        "message FuzzInput {",
                        "  repeated Action actions = 2;",
                        "}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            # Crash if param_0 == 7 (encoded in payload as b'\x08\x07').
            fuzzer = workdir / "demo_fuzzer.bin"
            fuzzer.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import sys",
                        "data = open(sys.argv[-1], 'rb').read()",
                        "if b'\\x08\\x07' in data:",
                        "    sys.stderr.write('simulated crash\\n')",
                        "    raise SystemExit(1)",
                        "raise SystemExit(0)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(fuzzer, os.stat(fuzzer).st_mode | stat.S_IXUSR)

            # FuzzInput(actions=[Action(foo=Foo_Params(param_0=7))])
            # bytes: 12 04 0A 02 08 07
            crash = crashes / "crash-a"
            crash.write_bytes(bytes([0x12, 0x04, 0x0A, 0x02, 0x08, 0x07]))

            out_json = workdir / "crashes" / "crash_learned_constraints.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workdir",
                    str(workdir),
                    "--fuzzer-bin",
                    str(fuzzer),
                    "--proto",
                    str(proto),
                    "--crash-dir",
                    str(crashes),
                    "--out-json",
                    str(out_json),
                    "--max-crashes",
                    "1",
                    "--max-byte-flips",
                    "16",
                    "--timeout-sec",
                    "2",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            meta = payload.get("meta", {})
            self.assertEqual(meta.get("input_crashes"), 1)
            self.assertEqual(meta.get("reproducible_crashes"), 1)
            self.assertGreaterEqual(int(meta.get("constraint_count", 0)), 1)

            constraints = payload.get("constraints", [])
            self.assertTrue(any(c.get("api") == "Foo" and c.get("param") == "param_0" for c in constraints))


if __name__ == "__main__":
    unittest.main()
