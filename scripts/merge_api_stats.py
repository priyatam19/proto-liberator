#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_api_stats(path: Path) -> list:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    apis = data.get("apis")
    if not isinstance(apis, list):
        return []
    return apis


def merge_stats(paths: list[Path]) -> list[dict]:
    merged: dict[str, dict] = {}
    for path in paths:
        for item in load_api_stats(path):
            name = item.get("name")
            if not name:
                continue
            entry = merged.setdefault(
                name,
                {"name": name, "seen": 0, "executed": 0, "skipped": 0},
            )
            entry["seen"] += int(item.get("seen") or 0)
            entry["executed"] += int(item.get("executed") or 0)
            entry["skipped"] += int(item.get("skipped") or 0)
    return [merged[k] for k in sorted(merged.keys())]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge proto-liberator api_stats.*.json into a single summary",
    )
    parser.add_argument(
        "--input-dir",
        default="api_stats",
        help="Directory containing api_stats.*.json (default: api_stats)",
    )
    parser.add_argument(
        "--output",
        default="api_stats/merged_api_stats.json",
        help="Output JSON path (default: api_stats/merged_api_stats.json)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    paths = sorted(input_dir.glob("api_stats.*.json"))
    merged = merge_stats(paths)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"apis": merged}, indent=2) + "\n")

    print(f"Merged {len(paths)} files -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
