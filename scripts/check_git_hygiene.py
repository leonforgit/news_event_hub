#!/usr/bin/env python3
# codex-workspace-bootstrap:managed-script-wrapper
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
GLOBAL_SCRIPT = CODEX_HOME / "scripts" / "check_git_hygiene.py"


def main(argv: list[str]) -> int:
    command = [sys.executable, str(GLOBAL_SCRIPT), *argv[1:]]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
