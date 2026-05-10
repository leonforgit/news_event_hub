#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


PLATFORM_DOMAIN_TERMS = {
    "twitter": ["x.com", "twitter.com", "t.co"],
    "reddit": ["reddit.com"],
    "xiaohongshu": ["xiaohongshu.com", "xhscdn.com"],
    "weibo": ["weibo.com", "weibo.cn", "sina.com.cn"],
    "xueqiu": ["xueqiu.com"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract per-platform cookie inventory from a Playwright storage-state file.")
    parser.add_argument(
        "--state-in",
        type=Path,
        default=Path("state/auth/agent_reach/playwright_shared_auth.json"),
        help="Input Playwright storage-state JSON.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("state/auth/agent_reach/platforms"),
        help="Output directory for per-platform cookie exports.",
    )
    return parser.parse_args()


def cookie_matches_domain_terms(cookie: dict[str, object], domain_terms: list[str]) -> bool:
    domain = str(cookie.get("domain") or "").lower()
    normalized = domain.lstrip(".")
    return any(normalized == term or normalized.endswith(f".{term}") for term in domain_terms)


def build_cookie_header(cookies: list[dict[str, object]]) -> str:
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies if cookie.get("name"))


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.state_in.exists():
        raise SystemExit(f"missing state file: {args.state_in}")

    payload = json.loads(args.state_in.read_text(encoding="utf-8"))
    cookies = payload.get("cookies") if isinstance(payload, dict) else []
    if not isinstance(cookies, list):
        raise SystemExit(f"state file has no cookies list: {args.state_in}")

    inventory: dict[str, object] = {
        "state_file": str(args.state_in),
        "cookie_total": len(cookies),
        "platforms": {},
    }

    for platform, domain_terms in PLATFORM_DOMAIN_TERMS.items():
        platform_cookies = [cookie for cookie in cookies if isinstance(cookie, dict) and cookie_matches_domain_terms(cookie, domain_terms)]
        domains = sorted({str(cookie.get("domain") or "") for cookie in platform_cookies if cookie.get("domain")})
        names = sorted({str(cookie.get("name") or "") for cookie in platform_cookies if cookie.get("name")})
        platform_dir = args.out_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        (platform_dir / "cookies.json").write_text(json.dumps(platform_cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        (platform_dir / "cookies.txt").write_text(build_cookie_header(platform_cookies), encoding="utf-8")
        inventory["platforms"][platform] = {
            "cookie_count": len(platform_cookies),
            "domains": domains,
            "cookie_names": names,
        }

    (args.out_dir / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
