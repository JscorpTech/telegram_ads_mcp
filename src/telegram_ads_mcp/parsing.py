"""Parsing helpers for ads.telegram.org table and form values."""

from __future__ import annotations

import re

_AD_ID_RE = re.compile(r"/account/ad/(\d+)")


def parse_int_commas(value: str) -> int:
    cleaned = re.sub(r"[,\s]", "", value.strip())
    if not cleaned or cleaned in {"-", "–", "—"}:
        return 0
    return int(cleaned)


def parse_decimal(value: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
    if not cleaned:
        return 0.0
    return float(cleaned)


def extract_ad_id(href: str | None) -> int | None:
    if not href:
        return None
    match = _AD_ID_RE.search(href)
    return int(match.group(1)) if match else None
