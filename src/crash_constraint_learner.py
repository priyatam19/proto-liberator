#!/usr/bin/env python3
"""
Crash-driven constraint learner.

For each crashing artifact, generate "shadow" inputs by flipping one byte and
replay. If a shadow no longer crashes, attribute that byte to a likely
constraint boundary and map it to (action_index, api, param) using the v2
protobuf wire layout.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


CRASH_PREFIXES = ("crash-", "leak-", "timeout-", "oom-")


@dataclass(frozen=True)
class ParsedField:
    number: int
    wire_type: int
    field_start: int
    field_end: int
    value_start: int
    value_end: int
    payload_start: Optional[int] = None
    payload_end: Optional[int] = None
    varint_value: Optional[int] = None


@dataclass(frozen=True)
class ProtoSchema:
    action_tag_to_api: Dict[int, str]
    action_tag_to_params_msg: Dict[int, str]
    params_fields: Dict[str, Dict[int, str]]


@dataclass(frozen=True)
class OffsetLocation:
    action_index: int
    action_tag: int
    api_name: str
    params_msg: str
    param_number: int
    param_name: str
    param_wire_type: int
    original_param_value: Optional[int]


def _decode_varint(data: bytes, start: int, end: int) -> Tuple[int, int]:
    shift = 0
    value = 0
    i = start
    while i < end and shift <= 63:
        b = data[i]
        value |= (b & 0x7F) << shift
        i += 1
        if (b & 0x80) == 0:
            return value, i - start
        shift += 7
    raise ValueError("invalid/truncated varint")


def _parse_message_fields(data: bytes, start: int, end: int) -> List[ParsedField]:
    out: List[ParsedField] = []
    i = max(0, start)
    end = min(len(data), end)
    while i < end:
        field_start = i
        try:
            key, key_len = _decode_varint(data, i, end)
        except Exception:
            break
        i += key_len
        number = key >> 3
        wire_type = key & 0x7
        if number <= 0:
            break

        if wire_type == 0:  # varint
            value_start = i
            try:
                v, v_len = _decode_varint(data, i, end)
            except Exception:
                break
            i += v_len
            out.append(
                ParsedField(
                    number=number,
                    wire_type=wire_type,
                    field_start=field_start,
                    field_end=i,
                    value_start=value_start,
                    value_end=i,
                    varint_value=v,
                )
            )
            continue

        if wire_type == 1:  # fixed64
            if i + 8 > end:
                break
            value_start = i
            i += 8
            out.append(
                ParsedField(
                    number=number,
                    wire_type=wire_type,
                    field_start=field_start,
                    field_end=i,
                    value_start=value_start,
                    value_end=i,
                )
            )
            continue

        if wire_type == 2:  # len-delimited
            len_start = i
            try:
                length, len_len = _decode_varint(data, i, end)
            except Exception:
                break
            i += len_len
            payload_start = i
            payload_end = min(end, i + int(length))
            if payload_end < payload_start:
                break
            i = payload_end
            out.append(
                ParsedField(
                    number=number,
                    wire_type=wire_type,
                    field_start=field_start,
                    field_end=i,
                    value_start=len_start,
                    value_end=i,
                    payload_start=payload_start,
                    payload_end=payload_end,
                )
            )
            continue

        if wire_type == 5:  # fixed32
            if i + 4 > end:
                break
            value_start = i
            i += 4
            out.append(
                ParsedField(
                    number=number,
                    wire_type=wire_type,
                    field_start=field_start,
                    field_end=i,
                    value_start=value_start,
                    value_end=i,
                )
            )
            continue

        break

    return out


def _extract_message_blocks(proto_text: str) -> Dict[str, List[str]]:
    lines = proto_text.splitlines()
    blocks: Dict[str, List[str]] = {}
    msg_re = re.compile(r"^\s*message\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")

    i = 0
    while i < len(lines):
        m = msg_re.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        brace = lines[i].count("{") - lines[i].count("}")
        block: List[str] = [lines[i]]
        j = i + 1
        while j < len(lines) and brace > 0:
            block.append(lines[j])
            brace += lines[j].count("{") - lines[j].count("}")
            j += 1
        blocks[name] = block
        i = j
    return blocks


def _parse_proto_schema(proto_path: Path) -> ProtoSchema:
    text = proto_path.read_text(encoding="utf-8")
    blocks = _extract_message_blocks(text)

    action_tag_to_api: Dict[int, str] = {}
    action_tag_to_params_msg: Dict[int, str] = {}
    params_fields: Dict[str, Dict[int, str]] = {}

    field_re = re.compile(
        r"^\s*(optional|required|repeated)\s+[A-Za-z0-9_\.<>]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)\s*(?:\[[^\]]*\])?\s*;"
    )

    for msg_name, block in blocks.items():
        if not msg_name.endswith("_Params"):
            continue
        mapping: Dict[int, str] = {}
        for line in block:
            m = field_re.match(line)
            if not m:
                continue
            field_name = m.group(2)
            field_no = int(m.group(3))
            mapping[field_no] = field_name
        params_fields[msg_name] = mapping

    action_block = blocks.get("Action", [])
    oneof_re = re.compile(r"^\s*oneof\s+action\s*\{")
    oneof_field_re = re.compile(
        r"^\s*([A-Za-z0-9_\.]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)\s*(?:\[[^\]]*\])?\s*;"
    )
    in_oneof = False
    oneof_brace = 0
    for line in action_block:
        if not in_oneof:
            if oneof_re.match(line):
                in_oneof = True
                oneof_brace = line.count("{") - line.count("}")
            continue

        oneof_brace += line.count("{") - line.count("}")
        m = oneof_field_re.match(line)
        if m:
            type_name = m.group(1).split(".")[-1]
            tag = int(m.group(3))
            action_tag_to_params_msg[tag] = type_name
            if type_name.endswith("_Params"):
                action_tag_to_api[tag] = type_name[: -len("_Params")]
            else:
                action_tag_to_api[tag] = type_name
        if oneof_brace <= 0:
            in_oneof = False

    return ProtoSchema(
        action_tag_to_api=action_tag_to_api,
        action_tag_to_params_msg=action_tag_to_params_msg,
        params_fields=params_fields,
    )


def _discover_fuzzer_bin(workdir: Path, explicit: str) -> Path:
    if explicit:
        p = Path(explicit).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"fuzzer binary not found: {p}")
    bins = sorted(workdir.glob("*_fuzzer.bin"))
    if bins:
        return bins[0].resolve()
    raise FileNotFoundError(f"fuzzer binary not found under {workdir} (*_fuzzer.bin)")


def _discover_proto_path(workdir: Path, explicit: str) -> Path:
    if explicit:
        p = Path(explicit).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"proto file not found: {p}")
    candidates = sorted(workdir.glob("*.v2.proto"))
    if not candidates:
        candidates = sorted(workdir.glob("*.proto"))
    if not candidates:
        raise FileNotFoundError(f"no proto schema found in {workdir}")
    return candidates[0].resolve()


def _iter_crash_inputs(crash_dir: Path) -> List[Path]:
    if not crash_dir.is_dir():
        return []
    out: List[Path] = []
    for p in sorted(crash_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name.endswith((".txt", ".json", ".log")):
            continue
        if p.name.startswith(CRASH_PREFIXES):
            out.append(p)
    return out


def _replay_path(fuzzer_bin: Path, input_path: Path, timeout_sec: int) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            [str(fuzzer_bin), "-runs=1", "-detect_leaks=0", str(input_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=max(1, int(timeout_sec)),
            check=False,
        )
        return int(proc.returncode), proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        out = ""
        if exc.stdout:
            out += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
        if exc.stderr:
            out += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
        return 124, out


def _mutation_candidates(orig: int) -> List[int]:
    out = [orig ^ 0x01, orig ^ 0xFF, 0x00, 0x7F, 0xFF]
    uniq: List[int] = []
    seen = set()
    for v in out:
        v = v & 0xFF
        if v == orig or v in seen:
            continue
        seen.add(v)
        uniq.append(v)
    return uniq


def _select_offsets(size: int, max_byte_flips: int) -> List[int]:
    if size <= 0 or max_byte_flips <= 0:
        return []
    if size <= max_byte_flips:
        return list(range(size))
    stride = max(1, size // max_byte_flips)
    offsets = list(range(0, size, stride))
    if offsets and offsets[-1] != size - 1:
        offsets.append(size - 1)
    return offsets[:max_byte_flips]


def _find_param_by_location(data: bytes, loc: OffsetLocation) -> Optional[ParsedField]:
    top = _parse_message_fields(data, 0, len(data))
    action_seen = 0
    for tf in top:
        if tf.number != 2 or tf.wire_type != 2 or tf.payload_start is None or tf.payload_end is None:
            continue
        if action_seen != loc.action_index:
            action_seen += 1
            continue
        action_fields = _parse_message_fields(data, tf.payload_start, tf.payload_end)
        for af in action_fields:
            if af.number != loc.action_tag or af.wire_type != 2 or af.payload_start is None or af.payload_end is None:
                continue
            params_fields = _parse_message_fields(data, af.payload_start, af.payload_end)
            for pf in params_fields:
                if pf.number == loc.param_number:
                    return pf
        return None
    return None


def _locate_offset(data: bytes, offset: int, schema: ProtoSchema) -> Optional[OffsetLocation]:
    if offset < 0 or offset >= len(data):
        return None
    top = _parse_message_fields(data, 0, len(data))
    action_idx = 0
    for tf in top:
        if tf.number != 2 or tf.wire_type != 2 or tf.payload_start is None or tf.payload_end is None:
            continue
        in_action = tf.field_start <= offset < tf.field_end
        action_fields = _parse_message_fields(data, tf.payload_start, tf.payload_end)
        for af in action_fields:
            if af.wire_type != 2 or af.payload_start is None or af.payload_end is None:
                continue
            if not (af.field_start <= offset < af.field_end):
                continue
            action_tag = af.number
            params_msg = schema.action_tag_to_params_msg.get(action_tag, "")
            api_name = schema.action_tag_to_api.get(action_tag, f"tag_{action_tag}")
            param_names = schema.params_fields.get(params_msg, {})
            params_fields = _parse_message_fields(data, af.payload_start, af.payload_end)
            for pf in params_fields:
                if pf.field_start <= offset < pf.field_end:
                    return OffsetLocation(
                        action_index=action_idx,
                        action_tag=action_tag,
                        api_name=api_name,
                        params_msg=params_msg,
                        param_number=pf.number,
                        param_name=param_names.get(pf.number, f"field_{pf.number}"),
                        param_wire_type=pf.wire_type,
                        original_param_value=pf.varint_value if pf.wire_type == 0 else None,
                    )
            return OffsetLocation(
                action_index=action_idx,
                action_tag=action_tag,
                api_name=api_name,
                params_msg=params_msg,
                param_number=0,
                param_name="unknown",
                param_wire_type=-1,
                original_param_value=None,
            )
        if in_action:
            return None
        action_idx += 1
    return None


def _analyze_crash(
    *,
    crash_path: Path,
    fuzzer_bin: Path,
    schema: ProtoSchema,
    timeout_sec: int,
    max_byte_flips: int,
) -> Dict[str, object]:
    data = crash_path.read_bytes()
    baseline_rc, baseline_out = _replay_path(fuzzer_bin, crash_path, timeout_sec)
    if baseline_rc == 0:
        return {
            "artifact": crash_path.name,
            "reproducible": False,
            "baseline_exit_code": baseline_rc,
            "events": [],
            "tested_offsets": 0,
            "baseline_log_excerpt": baseline_out[:400],
        }

    offsets = _select_offsets(len(data), max_byte_flips)
    events: List[Dict[str, object]] = []
    tested_offsets = 0

    with tempfile.TemporaryDirectory() as td:
        candidate = Path(td) / "shadow_input"
        for offset in offsets:
            tested_offsets += 1
            orig = data[offset]
            loc = _locate_offset(data, offset, schema)
            for new_val in _mutation_candidates(orig):
                mutated = bytearray(data)
                mutated[offset] = new_val
                candidate.write_bytes(bytes(mutated))
                rc, _ = _replay_path(fuzzer_bin, candidate, timeout_sec)
                if rc != 0:
                    continue

                mutated_param_value: Optional[int] = None
                if loc is not None:
                    mutated_field = _find_param_by_location(bytes(mutated), loc)
                    if mutated_field and mutated_field.wire_type == 0:
                        mutated_param_value = mutated_field.varint_value

                events.append(
                    {
                        "artifact": crash_path.name,
                        "offset": offset,
                        "original_byte": int(orig),
                        "mutated_byte": int(new_val),
                        "action_index": None if loc is None else int(loc.action_index),
                        "api": None if loc is None else loc.api_name,
                        "params_msg": None if loc is None else loc.params_msg,
                        "param": None if loc is None else loc.param_name,
                        "param_number": None if loc is None else int(loc.param_number),
                        "param_wire_type": None if loc is None else int(loc.param_wire_type),
                        "original_param_value": None if loc is None else loc.original_param_value,
                        "mutated_param_value": mutated_param_value,
                    }
                )
                break

    return {
        "artifact": crash_path.name,
        "reproducible": True,
        "baseline_exit_code": baseline_rc,
        "events": events,
        "tested_offsets": tested_offsets,
        "baseline_log_excerpt": baseline_out[:400],
    }


def _build_constraints(events: List[Dict[str, object]], *, min_evidence: int) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str], Dict[str, object]] = {}
    for ev in events:
        api = str(ev.get("api") or "")
        param = str(ev.get("param") or "")
        if not api or not param or param == "unknown":
            continue
        key = (api, param)
        entry = grouped.setdefault(
            key,
            {
                "api": api,
                "param": param,
                "evidence": 0,
                "kind": "varint" if ev.get("param_wire_type") == 0 else "bytes",
                "learnt_vals": set(),
                "crash_vals": set(),
            },
        )
        entry["evidence"] = int(entry["evidence"]) + 1

        mutated_param_value = ev.get("mutated_param_value")
        if mutated_param_value is not None:
            entry["learnt_vals"].add(int(mutated_param_value))
        else:
            entry["learnt_vals"].add(int(ev.get("mutated_byte", 0)))

        original_param_value = ev.get("original_param_value")
        if original_param_value is not None:
            entry["crash_vals"].add(int(original_param_value))

    out: List[Dict[str, object]] = []
    for _, entry in sorted(grouped.items()):
        evidence = int(entry["evidence"])
        if evidence < min_evidence:
            continue
        learnt_vals = sorted(int(v) for v in entry["learnt_vals"])
        crash_vals = sorted(int(v) for v in entry["crash_vals"])
        ranges: List[Dict[str, int]] = []
        if learnt_vals:
            ranges.append({"min": int(min(learnt_vals)), "max": int(max(learnt_vals))})
        out.append(
            {
                "api": entry["api"],
                "param": entry["param"],
                "kind": entry["kind"],
                "evidence": evidence,
                "learnt_vals": learnt_vals[:128],
                "crash_vals": crash_vals[:128],
                "ranges": ranges,
            }
        )
    return out


def learn_constraints(
    *,
    workdir: Path,
    fuzzer_bin: Path,
    crash_dir: Path,
    proto_path: Path,
    out_json: Path,
    timeout_sec: int,
    max_crashes: int,
    max_byte_flips: int,
    min_evidence: int,
) -> Dict[str, object]:
    schema = _parse_proto_schema(proto_path)
    crash_inputs = _iter_crash_inputs(crash_dir)[: max(0, int(max_crashes))]

    crash_results: List[Dict[str, object]] = []
    all_events: List[Dict[str, object]] = []
    total_tested_offsets = 0
    reproducible = 0

    for crash in crash_inputs:
        result = _analyze_crash(
            crash_path=crash,
            fuzzer_bin=fuzzer_bin,
            schema=schema,
            timeout_sec=timeout_sec,
            max_byte_flips=max_byte_flips,
        )
        crash_results.append(result)
        total_tested_offsets += int(result.get("tested_offsets", 0))
        if result.get("reproducible"):
            reproducible += 1
        evs = result.get("events", [])
        if isinstance(evs, list):
            all_events.extend([e for e in evs if isinstance(e, dict)])

    constraints = _build_constraints(all_events, min_evidence=max(1, int(min_evidence)))
    output = {
        "meta": {
            "workdir": str(workdir),
            "fuzzer_bin": str(fuzzer_bin),
            "crash_dir": str(crash_dir),
            "proto": str(proto_path),
            "input_crashes": len(crash_inputs),
            "reproducible_crashes": reproducible,
            "tested_offsets": total_tested_offsets,
            "successful_shadow_mutations": len(all_events),
            "constraint_count": len(constraints),
            "max_crashes": int(max_crashes),
            "max_byte_flips": int(max_byte_flips),
            "min_evidence": int(min_evidence),
            "generated_at_unix": int(time.time()),
        },
        "constraints": constraints,
        "events": all_events,
        "crashes": crash_results,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Learn crash constraints via shadow byte mutations.")
    parser.add_argument("workdir", nargs="?", default=None, help="Work directory")
    parser.add_argument("--workdir", dest="workdir_flag", default=None, help="Work directory (same as positional)")
    parser.add_argument("--fuzzer-bin", default=None, help="Fuzzer binary path")
    parser.add_argument("--crash-dir", default=None, help="Crash directory (default: <workdir>/crashes/genuine)")
    parser.add_argument("--proto", default=None, help="v2 proto schema path (default: autodetect in workdir)")
    parser.add_argument(
        "--out-json",
        default=None,
        help="Output JSON path (default: <workdir>/crashes/crash_learned_constraints.json)",
    )
    parser.add_argument("--timeout-sec", type=int, default=20, help="Per-replay timeout in seconds")
    parser.add_argument("--max-crashes", type=int, default=16, help="Max crash artifacts to analyze")
    parser.add_argument("--max-byte-flips", type=int, default=64, help="Max byte offsets to test per crash")
    parser.add_argument("--min-evidence", type=int, default=1, help="Minimum evidence count per learned constraint")
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

    try:
        proto_path = _discover_proto_path(workdir, args.proto or "")
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 2

    crash_dir = Path(args.crash_dir).resolve() if args.crash_dir else (workdir / "crashes" / "genuine")
    out_json = (
        Path(args.out_json).resolve()
        if args.out_json
        else (workdir / "crashes" / "crash_learned_constraints.json").resolve()
    )

    out = learn_constraints(
        workdir=workdir,
        fuzzer_bin=fuzzer_bin,
        crash_dir=crash_dir,
        proto_path=proto_path,
        out_json=out_json,
        timeout_sec=max(1, int(args.timeout_sec)),
        max_crashes=max(0, int(args.max_crashes)),
        max_byte_flips=max(1, int(args.max_byte_flips)),
        min_evidence=max(1, int(args.min_evidence)),
    )
    meta = out.get("meta", {}) if isinstance(out, dict) else {}
    print(
        "[CrashLearner] "
        f"constraints={int(meta.get('constraint_count', 0))} "
        f"events={int(meta.get('successful_shadow_mutations', 0))} "
        f"reproducible={int(meta.get('reproducible_crashes', 0))} "
        f"out={out_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
