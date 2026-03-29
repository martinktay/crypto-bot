"""Simple repository secret scanner for local/CI safety checks."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = {
    "openai": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "telegram_bot_token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),
}

IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv"}
IGNORE_FILES = {".env.example", "test_secret_scanner.py"}


def should_scan(path: Path) -> bool:
    if any(part in IGNORE_DIRS for part in path.parts):
        return False
    if path.name in IGNORE_FILES:
        return False
    return path.is_file()


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(f"{path}:{name}:{match.group(0)[:12]}...")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings: list[str] = []
    for path in root.rglob("*"):
        if should_scan(path):
            findings.extend(scan_file(path))

    if findings:
        print("Potential secrets detected:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("No potential secrets detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
