#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
BLOCKLIST_PATH = ROOT / "domains" / "blocklist.txt"
OUTPUT_DIR = ROOT / "cleaned"
OUTPUT_FILE = OUTPUT_DIR / "blocklist.txt"
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; blocklist-cleaner/1.0)"


def candidate_urls(entry: str) -> List[str]:
    """Return possible URLs to probe for a blocklist entry."""
    entry = entry.strip()
    if not entry:
        return []

    if "://" in entry:
        parsed = urlparse(entry)
        if parsed.scheme and parsed.netloc:
            return [entry]
        return []

    # basic filter to avoid regex-like rules or invalid hostnames
    invalid_chars = set(' \t"\'`<>|(){}[]')
    if entry.startswith("/") or invalid_chars.intersection(entry):
        return []
    if "." not in entry:
        return []

    return [f"http://{entry}", f"https://{entry}"]


def responds(url: str) -> bool:
    try:
        response = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code == 405:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
        # any HTTP response counts as a reply
        return True
    except requests.RequestException:
        return False


def load_blocklist(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Blocklist not found at {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_cleaned(lines: Iterable[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    destination.write_text(text, encoding="utf-8")


def main() -> int:
    try:
        raw_lines = load_blocklist(BLOCKLIST_PATH)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    cleaned_lines: List[str] = []
    removed: List[str] = []
    skipped_checks: List[str] = []
    cache: dict[str, bool] = {}

    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            cleaned_lines.append(raw)
            continue

        urls = candidate_urls(stripped)
        if not urls:
            cleaned_lines.append(raw)
            skipped_checks.append(stripped)
            continue

        key = stripped.lower()
        if key in cache:
            is_live = cache[key]
        else:
            is_live = any(responds(url) for url in urls)
            cache[key] = is_live

        if is_live:
            cleaned_lines.append(stripped)
        else:
            removed.append(stripped)

    write_cleaned(cleaned_lines, OUTPUT_FILE)

    print(f"Cleaned blocklist written to {OUTPUT_FILE.relative_to(ROOT)}")
    print(f"Checks performed for {len(cache)} entries; removed {len(removed)} unreachable domains.")
    if skipped_checks:
        print("Skipped checks for entries that do not look like plain domains or URLs:")
        for entry in sorted(set(skipped_checks)):
            print(f"  - {entry}")
    if removed:
        print("Removed entries:")
        for entry in removed:
            print(f"  - {entry}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
