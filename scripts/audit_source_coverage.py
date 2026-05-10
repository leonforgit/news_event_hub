#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
INVESTMENT_ROOT = ROOT.parent.parent
DEFAULT_REGISTRY = ROOT / "config" / "source_registry_v1.yaml"
DEFAULT_CATALOG = INVESTMENT_ROOT / "config" / "news_source_catalog.json"
DEFAULT_RADAR_POLICY = INVESTMENT_ROOT / "量化" / "industry_signal_radar" / "scripts" / "radar_news_policy.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit how much legacy news-source coverage has been absorbed into News Event Hub.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--radar-policy", type=Path, default=DEFAULT_RADAR_POLICY)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser.parse_args()


def normalize_source_key(value: str) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def load_registry(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text) or {}
        rows = payload.get("sources")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    except ModuleNotFoundError:
        pass

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- source_id:"):
            if current:
                rows.append(current)
            current = {"source_id": stripped.split(":", 1)[1].strip()}
            continue
        if current is None or ":" not in stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = value.strip().strip('"')
    if current:
        rows.append(current)
    return rows


def load_catalog(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("sources")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def load_radar_source_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    source_ids = re.findall(r'"source_id"\s*:\s*"([^"]+)"', text)
    deduped: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        if source_id in seen:
            continue
        seen.add(source_id)
        deduped.append(source_id)
    return deduped


def enabled_value(row: dict[str, Any], default: bool = True) -> bool:
    value = row.get("enabled", default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no"}


def classify_gap_bucket(source_key: str) -> str:
    key = str(source_key or "").strip().lower()
    if key in {"company_rumor_bing", "company_rumor_china_bing"}:
        return "signal_gap"
    if key.startswith("company_"):
        return "core_news_gap"
    if key.startswith("investor_"):
        return "commentary_gap"
    return "other_gap"


def summarize(
    registry_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    radar_source_ids: list[str],
) -> dict[str, Any]:
    registry_total = len(registry_rows)
    registry_enabled = [row for row in registry_rows if enabled_value(row, default=True)]

    shared_names = {
        normalize_source_key(str(row.get("source_id") or "")): str(row.get("source_id") or "")
        for row in registry_rows
        if str(row.get("source_id") or "").strip()
    }
    for row in registry_rows:
        for candidate in (row.get("legacy_key"), row.get("source_id")):
            text = str(candidate or "").strip()
            if text:
                shared_names.setdefault(normalize_source_key(text), str(row.get("source_id") or text))

    enabled_catalog_rows = [row for row in catalog_rows if enabled_value(row, default=True)]
    catalog_only: list[str] = []
    covered_catalog: list[str] = []
    for row in enabled_catalog_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        if normalize_source_key(key) in shared_names:
            covered_catalog.append(key)
        else:
            catalog_only.append(key)

    radar_missing: list[str] = []
    radar_covered: list[str] = []
    for source_id in radar_source_ids:
        if normalize_source_key(source_id) in shared_names:
            radar_covered.append(source_id)
        else:
            radar_missing.append(source_id)

    classified_catalog_missing = {
        "core_news_gap": sorted([item for item in catalog_only if classify_gap_bucket(item) == "core_news_gap"]),
        "signal_gap": sorted([item for item in catalog_only if classify_gap_bucket(item) == "signal_gap"]),
        "commentary_gap": sorted([item for item in catalog_only if classify_gap_bucket(item) == "commentary_gap"]),
        "other_gap": sorted([item for item in catalog_only if classify_gap_bucket(item) == "other_gap"]),
    }
    in_scope_missing = sorted(
        [
            item
            for item in catalog_only
            if classify_gap_bucket(item) in {"core_news_gap", "signal_gap", "other_gap"}
        ]
    )

    return {
        "shared_registry_total": registry_total,
        "shared_registry_enabled": len(registry_enabled),
        "legacy_catalog_total": len(catalog_rows),
        "legacy_catalog_enabled": len(enabled_catalog_rows),
        "legacy_catalog_covered_by_shared": len(covered_catalog),
        "legacy_catalog_missing_from_shared": sorted(catalog_only),
        "legacy_catalog_missing_by_bucket": classified_catalog_missing,
        "legacy_catalog_in_scope_missing_from_shared": in_scope_missing,
        "radar_private_source_ids": radar_source_ids,
        "radar_private_covered_by_shared": len(radar_covered),
        "radar_private_missing_from_shared": sorted(radar_missing),
    }


def print_text(summary: dict[str, Any]) -> None:
    print(f"shared_registry_total: {summary['shared_registry_total']}")
    print(f"shared_registry_enabled: {summary['shared_registry_enabled']}")
    print(f"legacy_catalog_total: {summary['legacy_catalog_total']}")
    print(f"legacy_catalog_enabled: {summary['legacy_catalog_enabled']}")
    print(f"legacy_catalog_covered_by_shared: {summary['legacy_catalog_covered_by_shared']}")
    print(f"radar_private_source_ids: {len(summary['radar_private_source_ids'])}")
    print(f"radar_private_covered_by_shared: {summary['radar_private_covered_by_shared']}")

    print("\nlegacy_catalog_missing_from_shared:")
    for item in summary["legacy_catalog_missing_from_shared"]:
        print(f"- {item}")

    print("\nlegacy_catalog_in_scope_missing_from_shared:")
    for item in summary["legacy_catalog_in_scope_missing_from_shared"]:
        print(f"- {item}")

    print("\nlegacy_catalog_missing_by_bucket:")
    for bucket_name in ("core_news_gap", "signal_gap", "commentary_gap", "other_gap"):
        print(f"{bucket_name}:")
        for item in summary["legacy_catalog_missing_by_bucket"][bucket_name]:
            print(f"- {item}")

    print("\nradar_private_missing_from_shared:")
    for item in summary["radar_private_missing_from_shared"]:
        print(f"- {item}")


def main() -> None:
    args = parse_args()
    summary = summarize(
        load_registry(args.registry),
        load_catalog(args.catalog),
        load_radar_source_ids(args.radar_policy),
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print_text(summary)


if __name__ == "__main__":
    main()
