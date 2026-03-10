from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from .config import IA_ROWS_PER_REQUEST, VIDEO_EXTENSIONS

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata"


def search_updated_identifiers(base_query: str, since_date: str) -> set[str]:
    """Return all identifiers matching *base_query* whose updatedate >= *since_date*.

    *since_date* should be an ISO date string like ``'2026-02-20'``.
    """
    query = f"({base_query}) AND updatedate:[{since_date} TO null]"
    found: set[str] = set()
    page = 1
    while True:
        ids, total = search_identifiers(query, page=page)
        found.update(ids)
        if len(found) >= total or not ids:
            break
        page += 1
        time.sleep(0.3)
    return found


def search_identifiers(query: str, page: int = 1, rows: int = IA_ROWS_PER_REQUEST) -> tuple[list[str], int]:
    params = {
        "q": query,
        "fl[]": "identifier",
        "rows": rows,
        "page": page,
        "output": "json",
        "sort[]": "publicdate desc",
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=45)
    resp.raise_for_status()
    data = resp.json()["response"]
    ids = [doc["identifier"] for doc in data.get("docs", []) if "identifier" in doc]
    return ids, int(data.get("numFound", 0))


def fetch_item_metadata(identifier: str) -> dict | None:
    url = f"{METADATA_URL}/{identifier}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(1.5)
    return None


def filter_video_files(files: list[dict]) -> list[dict]:
    out: list[dict] = []
    for f in files:
        name = str(f.get("name", ""))
        if not name:
            continue
        low = name.lower()
        if low.endswith(".torrent") or low.endswith(".jpg") or low.endswith(".gif"):
            continue
        if "storj" in low or "__ia_thumb" in low:
            continue
        base_ext = _last_extension_without_ia(low)
        if base_ext not in VIDEO_EXTENSIONS:
            continue
        out.append(f)
    return out


def _last_extension_without_ia(name: str) -> str:
    if name.endswith(".ia.mp4"):
        return ".mp4"
    idx = name.rfind(".")
    if idx == -1:
        return ""
    return name[idx:]


def build_records(identifier: str, metadata: dict) -> list[dict]:
    files = filter_video_files(metadata.get("files", []))
    media = metadata.get("metadata", {})
    records: list[dict] = []
    for f in files:
        rec = {
            "identifier": identifier,
            "filename": f.get("name", ""),
            "title": media.get("title", ""),
            "description": media.get("description", ""),
            "subject": media.get("subject", ""),
            "date_IA_scanned": datetime.now(timezone.utc).isoformat(),
            "IA_file_metadata": {
                "format": f.get("format"),
                "size": f.get("size"),
                "length": f.get("length"),
                "source": f.get("source"),
            },
        }
        records.append(rec)
    return records
