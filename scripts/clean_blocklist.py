#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import dataclass
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
# Query multiple DNS-over-HTTPS resolvers to avoid relying on local sinkholes.
DOH_ENDPOINTS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
    "https://dns.quad9.net/dns-query",
)
# Treat typical sinkhole answers as still-active trackers.
SINKHOLE_IPS = frozenset({"0.0.0.0", "127.0.0.1", "::", "::1"})


@dataclass(frozen=True)
class ResolutionResult:
    addresses: tuple[str, ...]
    has_authority: bool
    status: int

    @property
    def has_non_sinkhole(self) -> bool:
        return any(address not in SINKHOLE_IPS for address in self.addresses)

    @property
    def sinkhole_only(self) -> bool:
        return bool(self.addresses) and not self.has_non_sinkhole

    def indicates_presence(self) -> bool:
        if self.has_non_sinkhole:
            return True
        if self.sinkhole_only:
            return True
        return False


_RESOLUTION_CACHE: dict[str, ResolutionResult] = {}


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
        return True
    except requests.RequestException:
        return False


def is_full_url(entry: str) -> bool:
    if "://" not in entry:
        return False
    parsed = urlparse(entry)
    return bool(parsed.scheme and parsed.netloc)


def resolve_domain(domain: str, *, visited: frozenset[str] | None = None) -> ResolutionResult:
    key = domain.rstrip(".").lower()
    cached = _RESOLUTION_CACHE.get(key)
    if cached is not None:
        return cached

    if visited is None:
        visited = frozenset()
    if key in visited or len(visited) > 5:
        return ResolutionResult((), False, status=2)
    next_visited = visited | {key}

    addresses: set[str] = set()
    has_authority = False
    status_codes: List[int] = []

    for endpoint in DOH_ENDPOINTS:
        for record_type in ("A", "AAAA", "CNAME"):
            data = _query_doh(endpoint, key, record_type)
            if not data:
                continue
            status = int(data.get("Status", 0))
            status_codes.append(status)

            for answer in data.get("Answer") or []:
                ans_type = int(answer.get("type", 0))
                value = (answer.get("data") or "").strip()
                if not value:
                    continue
                if ans_type in {1, 28}:  # A / AAAA records
                    addresses.add(value.rstrip("."))
                elif ans_type == 5:  # CNAME
                    target = value.rstrip(".")
                    if target and target not in next_visited:
                        target_result = resolve_domain(target, visited=next_visited)
                        addresses.update(target_result.addresses)
                        if target_result.has_authority:
                            has_authority = True

            if not has_authority and status != 3:
                for authority in data.get("Authority") or []:
                    authority_type = int(authority.get("type", 0))
                    if authority_type in {2, 6}:  # NS or SOA
                        has_authority = True
                        break

    status = min(status_codes) if status_codes else 2
    result = ResolutionResult(tuple(sorted(addresses)), has_authority, status)
    _RESOLUTION_CACHE[key] = result
    return result


def _query_doh(endpoint: str, domain: str, record_type: str) -> dict | None:
    params = {"name": domain, "type": record_type}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/dns-json"}
    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def is_entry_live(entry: str, urls: List[str]) -> bool:
    if is_full_url(entry):
        return any(responds(url) for url in urls)

    domain = entry.lower()
    resolution = resolve_domain(domain)
    if resolution.indicates_presence():
        return True

    if resolution.has_authority:
        www_domain = f"www.{domain}"
        www_urls = [f"http://{www_domain}", f"https://{www_domain}"]
        if any(responds(url) for url in www_urls):
            return True
        www_resolution = resolve_domain(www_domain)
        if www_resolution.indicates_presence():
            return True

    return any(responds(url) for url in urls)


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
            is_live = is_entry_live(stripped, urls)
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
