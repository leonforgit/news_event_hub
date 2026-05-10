#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge multiple Playwright storage-state JSON files.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Input storage-state JSON files.")
    parser.add_argument("--out", required=True, type=Path, help="Output merged storage-state JSON file.")
    return parser.parse_args()


def load_state(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"invalid storage-state payload: {path}")
    payload.setdefault("cookies", [])
    payload.setdefault("origins", [])
    return payload


def cookie_key(cookie: dict) -> tuple[str, str, str]:
    return (
        str(cookie.get("domain") or ""),
        str(cookie.get("path") or ""),
        str(cookie.get("name") or ""),
    )


def origin_key(origin: dict) -> str:
    return str(origin.get("origin") or "")


def main() -> None:
    args = parse_args()
    merged_cookies: dict[tuple[str, str, str], dict] = {}
    merged_origins: dict[str, dict] = {}

    for path in args.inputs:
        state = load_state(path)
        for cookie in state.get("cookies", []):
            if isinstance(cookie, dict):
                merged_cookies[cookie_key(cookie)] = cookie
        for origin in state.get("origins", []):
            if isinstance(origin, dict):
                key = origin_key(origin)
                if key:
                    merged_origins[key] = origin

    merged = {
        "cookies": list(merged_cookies.values()),
        "origins": list(merged_origins.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
