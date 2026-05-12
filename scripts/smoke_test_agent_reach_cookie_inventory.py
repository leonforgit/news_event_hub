#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "export_agent_reach_cookie_inventory.py"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def main() -> None:
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        state_path = base / "state.json"
        out_dir = base / "platforms"
        secret_value = "secret-cookie-value"
        state_path.write_text(
            json.dumps(
                {
                    "cookies": [
                        {"name": "auth_token", "value": secret_value, "domain": ".twitter.com"},
                        {"name": "sid", "value": "reddit-secret", "domain": ".reddit.com"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        inventory = subprocess.run(
            [sys.executable, str(SCRIPT), "--state-in", str(state_path), "--out-dir", str(out_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(inventory.stdout)
        assert_true(payload["raw_cookie_exports_written"] is False, "raw cookie export must default off")
        assert_true(secret_value not in inventory.stdout, "inventory stdout must not contain raw cookie values")
        assert_true(not out_dir.exists(), "inventory-only mode must not write raw cookie directories")

        raw_export = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--state-in",
                str(state_path),
                "--out-dir",
                str(out_dir),
                "--export-raw-cookies",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        raw_payload = json.loads(raw_export.stdout)
        cookie_file = out_dir / "twitter" / "cookies.txt"
        assert_true(raw_payload["raw_cookie_exports_written"] is True, "raw export flag should be reflected in inventory")
        assert_true(cookie_file.read_text(encoding="utf-8") == f"auth_token={secret_value}", "raw cookie file content mismatch")
        assert_true(mode(out_dir) == 0o700, "raw export root directory should be 0700")
        assert_true(mode(cookie_file.parent) == 0o700, "platform directory should be 0700")
        assert_true(mode(cookie_file) == 0o600, "raw cookie file should be 0600")
        assert_true(mode(out_dir / "inventory.json") == 0o600, "raw export inventory file should be 0600")

    print("agent_reach_cookie_inventory_smoke_ok")


if __name__ == "__main__":
    os.umask(0o022)
    main()
