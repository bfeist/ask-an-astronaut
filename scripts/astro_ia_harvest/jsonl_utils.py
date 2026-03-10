from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def append_jsonl(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def remove_identifiers_from_jsonl(path: Path, identifiers: set[str]) -> int:
    """Rewrite *path* dropping every record whose 'identifier' is in *identifiers*.

    Returns the number of records removed.
    """
    if not path.exists() or not identifiers:
        return 0
    kept: list[str] = []
    removed = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if rec.get("identifier") in identifiers:
                removed += 1
            else:
                kept.append(line if line.endswith("\n") else line + "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)
    return removed
