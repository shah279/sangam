"""Symbol normalization — STUBBED for now.

We deliberately leave resolved_symbol NULL until we've seen a batch of raw
extractions and can build master.csv from the NSE equity list + AMFI scheme file.
Once that exists, this is where fuzzy matching (rapidfuzz) will map
raw_mention -> canonical symbol. For now every mention keeps its raw text and
resolved_symbol stays None, so aggregation groups on raw_mention meanwhile."""
from __future__ import annotations


def resolve(raw_mention: str, instrument_type: str | None = None) -> str | None:
    return None  # TODO: fuzzy-match against master.csv once built
