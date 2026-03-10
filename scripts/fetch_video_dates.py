#!/usr/bin/env python3
"""Utility: Fetch the date for every video asset that has been QA-extracted.

For each QA file in data/qa/, resolves the real IA identifier (using
classified_candidates.jsonl as ground truth), then fetches the best available
date from the Internet Archive API.

Date resolution priority (for each IA item):
  1. ``publicdate`` field   (e.g. "2022-09-30 09:45:13") → YYYY-MM-DD
  2. ``addeddate`` field    (same format)
  3. mtime of the largest video file in the IA item
  4. ``date`` field         (often just a year like "2022")

Output: data/video_dates.json
  {
    "<ia_identifier>": {
      "date": "YYYY-MM-DD",   # best available; empty string if IA has nothing
      "source": "ia_api",
      "qa_files": ["<qa_filename>", ...]
    },
    ...
  }

Run this once after QA extraction to populate date metadata without re-running
the full overnight scan.  Re-running is safe and will refresh all dates.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from astro_ia_harvest.config import CLASSIFIED_JSONL, QA_DIR  # noqa: E402
from astro_ia_harvest.download_utils import canonical_video_key  # noqa: E402
from astro_ia_harvest.ia_api import fetch_item_metadata  # noqa: E402

OUTPUT_FILE = ROOT / "data" / "video_dates.json"

VIDEO_EXTENSIONS = (".mp4", ".mxf", ".mov", ".m4v", ".avi", ".mpg", ".mpeg", ".webm")


# ---------------------------------------------------------------------------
# Identifier resolution
# ---------------------------------------------------------------------------

def build_identifier_lookups() -> tuple[set[str], dict[str, str]]:
    """Return (real_identifiers, canonical_key_to_identifier) from classified_candidates.jsonl.

    ``real_identifiers`` is the set of all IA identifiers that have been through the pipeline.
    ``canonical_key_to_identifier`` maps canonical_video_key(filename) → identifier so that
    a QA filename prefix that is actually an IA filename stem can still be resolved.
    """
    real_idents: set[str] = set()
    ck_to_ident: dict[str, str] = {}

    if not CLASSIFIED_JSONL.exists():
        return real_idents, ck_to_ident

    with open(CLASSIFIED_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ident = str(rec.get("identifier", "")).strip()
            filename = str(rec.get("filename", "")).strip()
            if not ident:
                continue
            real_idents.add(ident)
            if filename:
                ck_to_ident[canonical_video_key(filename)] = ident

    return real_idents, ck_to_ident


def resolve_identifier(qa_prefix: str, real_idents: set[str], ck_to_ident: dict[str, str]) -> str:
    """Return the true IA identifier for a prefix extracted from a QA filename.

    QA files created from downloads via the pipeline use the format
    ``<identifier>__<stem>_lowres.qa.json`` so the prefix IS the identifier.

    Files copied from the ISSiRT legacy directory keep the IA filename as their
    base name (e.g. ``<ia_filename_stem>__lowres.qa.json``), in which case the
    prefix is an IA filename stem — not the identifier.  We detect this case by
    checking whether the prefix exists in the set of real identifiers; if not,
    we fall back to a canonical-key lookup against classified_candidates.
    """
    if qa_prefix in real_idents:
        return qa_prefix
    ck = canonical_video_key(qa_prefix)
    return ck_to_ident.get(ck, qa_prefix)


# ---------------------------------------------------------------------------
# QA file collection
# ---------------------------------------------------------------------------

def collect_qa_files(real_idents: set[str], ck_to_ident: dict[str, str]) -> dict[str, list[str]]:
    """Return {real_identifier: [qa_filename, ...]}."""
    result: dict[str, list[str]] = {}
    for p in sorted(QA_DIR.glob("*.qa.json")):
        if "__" not in p.name:
            continue
        qa_prefix = p.name.split("__")[0]
        ident = resolve_identifier(qa_prefix, real_idents, ck_to_ident)
        result.setdefault(ident, []).append(p.name)
    return result


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

def resolve_best_date(metadata: dict) -> str:
    """Return the best available date string from an IA metadata response.

    Priority:
      1. publicdate / addeddate  → YYYY-MM-DD (these have full calendar dates)
      2. mtime of the largest video file → YYYY-MM-DD
      3. date field              → as-is (often just a year)
    """
    m = metadata.get("metadata", {})

    # 1. publicdate / addeddate
    for field in ("publicdate", "addeddate"):
        val = str(m.get(field, "")).strip()
        if val and len(val) >= 10:
            return val[:10]  # YYYY-MM-DD

    # 2. mtime of largest video file
    files = metadata.get("files", [])
    video_files = [
        f for f in files
        if any(str(f.get("name", "")).lower().endswith(ext) for ext in VIDEO_EXTENSIONS)
    ]
    if video_files:
        largest = max(video_files, key=lambda f: int(f.get("size") or 0))
        mtime = largest.get("mtime")
        if mtime:
            try:
                dt = datetime.fromtimestamp(int(mtime), tz=timezone.utc)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

    # 3. date field (may be year-only)
    return str(m.get("date", "")).strip()


def fetch_date_from_ia(identifier: str) -> str:
    """Fetch the IA item metadata and return the best date string."""
    metadata = fetch_item_metadata(identifier)
    if not metadata:
        return ""
    return resolve_best_date(metadata)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("fetch_video_dates.py — Build data/video_dates.json")
    print("=" * 70)

    real_idents, ck_to_ident = build_identifier_lookups()
    print(f"Real IA identifiers (from classified): {len(real_idents)}")

    ident_map = collect_qa_files(real_idents, ck_to_ident)
    all_identifiers = sorted(ident_map.keys())
    print(f"QA files found    : {sum(len(v) for v in ident_map.values())}")
    print(f"Unique identifiers: {len(all_identifiers)}")
    print()

    # Fetch all dates fresh from IA (re-running is safe and refreshes stale data)
    output: dict[str, dict] = {}
    for idx, ident in enumerate(all_identifiers, start=1):
        print(f"  [{idx}/{len(all_identifiers)}] {ident} ...", end=" ", flush=True)
        date = fetch_date_from_ia(ident)
        output[ident] = {
            "date": date,
            "source": "ia_api",
            "qa_files": ident_map[ident],
        }
        print(date if date else "(no date on IA)")
        time.sleep(0.3)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    has_date = sum(1 for v in output.values() if v["date"])
    print()
    print(f"Written: {OUTPUT_FILE}")
    print(f"Identifiers with a date : {has_date} / {len(output)}")
    print(f"Identifiers with no date: {len(output) - has_date}")


if __name__ == "__main__":
    main()
