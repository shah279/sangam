"""Pure creator-weighted consensus shared by reports and tests."""
from __future__ import annotations

from . import normalize


def _published(row: dict) -> str:
    return ((row.get("video") or {}).get("published_at") or "")


def _creator_key(row: dict) -> str:
    video = row.get("video") or {}
    return video.get("channel_id") or f"video:{row.get('video_id', row.get('id'))}"


def _eligible(row: dict, min_confidence: float) -> bool:
    raw = str(row.get("raw_mention") or "").strip()
    if not raw or normalize.is_generic(raw) or row.get("source") == "description":
        return False
    confidence = row.get("confidence")
    return confidence is None or float(confidence) >= min_confidence


def build(rows: list[dict], min_confidence: float = 0.55) -> list[dict]:
    """Group mentions and weight each instrument once per creator.

    Total mention count stays visible, while conviction/action consensus uses the
    highest-confidence/latest representative mention from each creator.
    """
    groups: dict[tuple[str, str, bool], list[dict]] = {}
    for row in rows:
        if not _eligible(row, min_confidence):
            continue
        raw = str(row.get("raw_mention") or "").strip()
        declared_type = row.get("instrument_type") or ""
        resolution = normalize.resolve_record(raw, declared_type)
        symbol = row.get("resolved_symbol") or (resolution.symbol if resolution else None)
        kind = resolution.instrument_type if resolution else declared_type
        name = symbol or raw
        groups.setdefault((name, kind, bool(symbol)), []).append(row)

    output: list[dict] = []
    for (name, kind, resolved), mentions in groups.items():
        by_creator: dict[str, list[dict]] = {}
        for mention in mentions:
            by_creator.setdefault(_creator_key(mention), []).append(mention)
        representatives = [
            max(
                creator_mentions,
                key=lambda row: (
                    float(row.get("confidence") or 0),
                    int(row.get("conviction") or 0),
                    _published(row),
                ),
            )
            for creator_mentions in by_creator.values()
        ]
        convictions = [int(row.get("conviction") or 0) for row in representatives]
        actions: dict[str, int] = {}
        for row in representatives:
            action = row.get("action")
            if action:
                actions[action] = actions.get(action, 0) + 1
        latest = max((_published(row) for row in mentions), default="") or None
        sample = max(representatives, key=lambda row: _published(row), default={})
        creator_names = sorted({
            (((row.get("video") or {}).get("channel") or {}).get("name") or _creator_key(row))
            for row in representatives
        })
        output.append({
            "name": name,
            "resolved": resolved,
            "instrument_type": kind,
            "creator_count": len(representatives),
            "mention_count": len(mentions),
            "avg_conviction": round(sum(convictions) / max(1, len(convictions)), 2),
            "top_conviction": max(convictions, default=0),
            "action_counts": actions,
            "sample_note": sample.get("note"),
            "latest_at": latest,
            "creators": creator_names,
        })
    return sorted(
        output,
        key=lambda item: (
            item["creator_count"], item["avg_conviction"], item["latest_at"] or ""
        ),
        reverse=True,
    )
