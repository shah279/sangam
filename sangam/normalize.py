"""Conservative canonicalization for Indian-market instrument mentions.

Only exact, reviewed aliases are merged. Unknown names deliberately stay unresolved
instead of being fuzzy-matched to the wrong security. The catalog focuses on names
seen in Sangam's extraction output and can be expanded without changing callers.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .outcome import StageResult


@dataclass(frozen=True)
class Resolution:
    symbol: str
    instrument_type: str
    method: str = "alias"


# Canonical NSE/foreign symbols. Ambiguous group names ("Tata", "Bajaj", etc.)
# are intentionally omitted.
STOCK_ALIASES: dict[str, tuple[str, ...]] = {
    "ADANIENT": ("Adani Enterprises",),
    # Registered as "Affle 3i Limited"; "Affle India" is a common older/informal name.
    "AFFLE": ("Affle India",),
    # Registered name is "Apollo Hospitals" (plural); this covers the singular mishearing.
    "APOLLOHOSP": ("Apollo Hospital",),
    "ATHERENERG": ("Ather Energy", "Ather"),
    "AUBANK": ("AU Small Finance Bank", "AU Bank"),
    "AXISBANK": ("Axis Bank",),
    "BAJAJ-AUTO": ("Bajaj Auto",),
    "BEML": ("BEML",),
    "BHARTIARTL": ("Bharti Airtel", "Airtel"),
    "BSE": ("BSE Ltd", "Bombay Stock Exchange"),
    "CGPOWER": ("CG Power", "CG Power and Industrial Solutions"),
    "DIXON": ("Dixon", "Dixon Technologies"),
    "ETERNAL": ("Zomato", "Eternal", "Eternal Ltd"),
    "GLAND": ("Gland Pharma",),
    "GMRINFRA": ("GMR Airports", "GMR Infrastructure", "GMR"),
    "HAL": ("HAL", "Hindustan Aeronautics"),
    # Not a prefix match: "HCL Infosystems" is a separate, differently-listed company.
    "HCLTECH": ("HCL Tech",),
    "HDFCBANK": ("HDFC Bank",),
    "HEROMOTOCO": ("Hero MotoCorp", "Hero Motocorp"),
    "HFCL": ("HFCL",),
    "HINDCOPPER": ("Hindustan Copper",),
    "HYUNDAI": ("Hyundai Motor India", "Hyundai", "Hyundai Motors"),
    "ICICIBANK": ("ICICI Bank",),
    "IDEA": ("Vodafone Idea", "Vi"),
    "INDIGO": ("InterGlobe Aviation", "IndiGo"),
    "INFY": ("Infosys",),
    "IRCTC": ("IRCTC",),
    "ITC": ("ITC", "ITC Ltd"),
    "JIOFIN": ("Jio Financial", "Jio Finance", "Jio Financial Services", "JFS"),
    "KALYANKJIL": ("Kalyan Jewellers",),
    "LAURUSLABS": ("Laurus Labs",),
    "LICI": ("LIC", "Life Insurance Corporation of India"),
    "LT": ("L&T", "L and T", "Larsen and Toubro"),
    "MANAPPURAM": ("Manappuram Finance", "Manappuram"),
    "MARKSANS": ("Marksans Pharma",),
    "MAZDOCK": ("Mazagon Dock", "Mazagon Dock Shipbuilders"),
    "MARUTI": ("Maruti", "Maruti Suzuki"),
    # "MTR technologies" is a recurring transcript mishearing of "MTAR".
    "MTARTECH": ("MTAR Technologies", "MTAR Tech", "MTAR", "MTR Technologies"),
    "NAUKRI": ("Info Edge", "Info Edge India"),
    "NEULANDLAB": ("Neuland Labs", "Neuland Laboratories"),
    "NMDC": ("NMDC",),
    "ONGC": ("ONGC", "Oil and Natural Gas Corporation"),
    "ONE97": ("Paytm", "One97 Communications"),
    "PIIND": ("PI Industries",),
    "POLICYBZR": ("PB Fintech", "Policybazaar"),
    "POWERINDIA": ("Hitachi Energy", "Hitachi Energy India"),
    "RELIANCE": ("Reliance", "Reliance Industries", "RIL"),
    # Registered as "R R Kabel" (spaced); "RR Kabel" is the common written form.
    "RRKABEL": ("RR Kabel",),
    "RVNL": ("RVNL", "Rail Vikas Nigam"),
    "SANSERA": ("Sansera Engineering", "Sansera"),
    "SBIN": ("SBI", "State Bank of India"),
    # "Shipa" is a recurring transcript mishearing of "Shilpa" for this stock.
    "SHILPAMED": ("Shilpa Medicare", "Shipa Medicare"),
    "SONACOMS": ("Sona BLW", "Sona Comstar", "Sona BLW Precision Forgings"),
    "STLTECH": ("Sterlite Technologies", "STL Tech"),
    "SUZLON": ("Suzlon", "Suzlon Energy"),
    "SWIGGY": ("Swiggy",),
    "TATAMOTORS": ("Tata Motors",),
    "TATAPOWER": ("Tata Power",),
    "TCS": ("TCS", "Tata Consultancy Services"),
    "TIINDIA": ("Tube Investments", "Tube Investments of India"),
    "TRENT": ("Trent", "Trent Ltd"),
    "TVSMOTOR": ("TVS Motor", "TVS Motor Company"),
    "VEDL": ("Vedanta", "Vedanta Ltd"),
    # Registered name is "Waaree Renewable Technologies"; distinct from Waaree Energies.
    "WAAREERTL": ("Waaree Renewables",),
    "WIPRO": ("Wipro",),
    "YESBANK": ("Yes Bank",),
    "ZEEL": ("Zee Entertainment", "Zee Entertainment Enterprises"),
    # "Zen Tech" is a common abbreviation of the registered "Zen Technologies".
    "ZENTEC": ("Zen Tech",),
    "NASDAQ:NVDA": ("Nvidia", "NVIDIA"),
    "NYSE:WMT": ("Walmart",),
}

SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "COMMODITY:GOLD": ("Gold", "सोना", "Gold ETFs"),
    "COMMODITY:SILVER": ("Silver", "चांदी"),
    "COMMODITY:CRUDE_OIL": ("Crude oil", "Oil prices"),
    "GROUP:ADANI": ("Adani Group", "Adani stocks"),
    "GROUP:TATA": ("Tata Group", "Tata stocks"),
    "INDEX:BSE_SENSEX": ("Sensex", "BSE Sensex", "BSC Sensex"),
    "INDEX:NIFTY_50": ("Nifty", "Nifty 50", "NIFTY50"),
    "INDEX:NIFTY_CAPITAL_MARKETS": ("Nifty Capital Markets Index",),
    "INDEX:NIFTY_ENERGY": ("Nifty Energy", "Nifty Energy Index"),
    "SECTOR:AUTO": ("Auto", "Auto sector", "Automobile sector"),
    "SECTOR:BANKING": ("Banks", "Banking", "Banking sector", "Bank stocks"),
    "SECTOR:CAPITAL_MARKETS": ("Capital Market", "Capital markets"),
    "SECTOR:CHEMICALS": ("Chemicals", "Chemical sector"),
    "SECTOR:DEFENCE": ("Defense", "Defence", "Defense sector", "Defence sector"),
    "SECTOR:ENERGY": ("Energy", "Energy sector", "Power sector"),
    "SECTOR:EV": ("EV", "Electric vehicle", "Electric Vehicle sector"),
    "SECTOR:FMCG": ("FMCG", "FMCG sector"),
    "SECTOR:HEALTHCARE": ("Healthcare", "Hospital", "Hospital theme", "Diagnostics Sector"),
    "SECTOR:INFRASTRUCTURE": ("Infrastructure", "Infrastructure sector"),
    "SECTOR:IT": ("IT", "IT sector", "Information technology sector"),
    "SECTOR:REAL_ESTATE": ("Real estate", "Indian real estate", "Realty sector"),
    "SECTOR:SEMICONDUCTORS": ("Semiconductor", "Semiconductors"),
    "SECTOR:SOLAR": ("Solar", "Solar power", "Solar stocks"),
    "SECTOR:SUGAR": ("Sugar", "Sugar stocks"),
    "SECTOR:TELECOM": ("Telecom", "Telecom sector"),
}

FUND_ALIASES: dict[str, tuple[str, ...]] = {
    "MF:AXIS_NIFTY_ENERGY_INDEX": ("Axis Nifty Energy Index Fund",),
    "MF:HDFC_FLEXI_CAP": ("HDFC Flexi Cap", "HDFC Flexi-cap Fund", "HDFC Flexi Cap Fund"),
    "MF:HDFC_MID_CAP": ("HDFC Midcap", "HDFC Mid-Cap Opportunities Fund"),
    "MF:ICICI_PRU_LARGE_CAP": ("ICICI Prudential Large Cap", "ICICI Prudential Large Cap Fund"),
    "MF:NIPPON_INDIA_SMALL_CAP": ("Nippon India Small Cap", "Nippon India Small Cap Fund"),
    "MF:PARAG_PARIKH_FLEXI_CAP": (
        "Parag Parikh Flexi Cap", "Parag Parikh Flexi-cap Fund",
        "Parag Parikh Flexi Cap Fund", "PPFAS Flexi Cap",
    ),
    "MF:QUANT_FLEXI_CAP": ("Quant Flexi Cap", "Quant Flexi-cap Fund", "Quant Flexi Cap Fund"),
}

GENERIC_MENTIONS = {
    "active etfs", "banking and psu fund", "corporate bond fund", "direct stocks", "etf",
    "etfs", "global etfs", "index fund", "low duration fund", "money market fund",
    "mutual fund", "mutual funds", "nse", "passive funds", "sif", "sip", "stock market",
    "us stocks",
}


# Pure corporate-form words that a registered company name carries but a
# spoken/transcript mention almost never does ("Marksans Pharma" vs. the
# broker master's "Marksans Pharma Limited"). None of these disambiguate one
# company from another, so stripping them is safe everywhere key() is used.
_CORP_SUFFIXES = re.compile(r"\b(ltd|limited|pvt|private)\b")


def key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = _CORP_SUFFIXES.sub(" ", value)
    return " ".join(value.split())


def _lookup(catalog: dict[str, tuple[str, ...]], kind: str) -> dict[str, Resolution]:
    out: dict[str, Resolution] = {}
    for symbol, aliases in catalog.items():
        for alias in (*aliases, symbol):
            out[key(alias)] = Resolution(symbol, kind)
    return out


_LOOKUPS = {
    "stock": _lookup(STOCK_ALIASES, "stock"),
    "sector": _lookup(SECTOR_ALIASES, "sector"),
    "mutual_fund": _lookup(FUND_ALIASES, "mutual_fund"),
}

_broker_lookup_cache: dict[str, Resolution] | None = None


def _strip_series_suffix(trading_symbol: str | None) -> str | None:
    """AngelOne-style trading symbols carry a series suffix ("RELIANCE-EQ")."""
    if not trading_symbol:
        return None
    return trading_symbol.rsplit("-", 1)[0] if "-" in trading_symbol else trading_symbol


# A company-name index for prefix matching: first word -> [(all words, Resolution)].
# Only ever built from descriptive names, never bare tickers/trading symbols —
# prefix-matching a ticker code isn't meaningful the way it is for a name.
PrefixIndex = dict[str, list[tuple[tuple[str, ...], "Resolution"]]]


def _index_name(prefix_index: PrefixIndex, name: str | None, resolution: Resolution) -> None:
    if not name:
        return
    words = tuple(key(name).split())
    if len(words) >= 2:  # single-word names are too ambiguous to prefix-match
        prefix_index.setdefault(words[0], []).append((words, resolution))


_broker_prefix_cache: PrefixIndex | None = None


def _broker_lookup() -> dict[str, Resolution]:
    """Lazily build a name/symbol -> Resolution index from the separate
    project's NSE/BSE instrument master, caching it for the process lifetime.
    Falls back to an empty index (no broker-backed resolutions) on any error,
    so a misconfigured or unreachable second project degrades gracefully
    instead of failing normalization for everyone.
    """
    global _broker_lookup_cache, _broker_prefix_cache
    if _broker_lookup_cache is not None:
        return _broker_lookup_cache
    from . import db

    try:
        rows = db.fetch_broker_instruments()
    except Exception as e:
        print(f"normalize: broker instrument master unavailable, skipping ({e})")
        rows = []

    lookup: dict[str, Resolution] = {}
    prefix_index: PrefixIndex = {}
    # NSE sorted first so it wins ties with BSE on the same normalized name.
    for row in sorted(rows, key=lambda r: r.get("exchange") != "NSE"):
        if row.get("instrument_type") != "EQ":
            continue  # indices/derivatives aren't priceable via prices.py yet
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        resolution = Resolution(symbol, "stock", method="broker_master")
        name = row.get("name")
        aliases = (name, symbol, _strip_series_suffix(row.get("trading_symbol")))
        for alias in filter(None, aliases):
            lookup.setdefault(key(alias), resolution)
        _index_name(prefix_index, name, resolution)

    if rows:
        print(f"normalize: broker instrument master loaded ({len(lookup)} alias(es))")
    _broker_lookup_cache = lookup
    _broker_prefix_cache = prefix_index
    return lookup


_nse_lookup_cache: dict[str, Resolution] | None = None
_nse_prefix_cache: PrefixIndex | None = None


def _nse_company_lookup() -> dict[str, Resolution]:
    """Lazily build a company-name -> Resolution index from NSE's own public
    equity list, caching for the process lifetime. This is the broadest of
    the three resolution sources: unlike the broker instrument master (whose
    `name` field turned out to just repeat the ticker for this data), NSE's
    list carries real registered company names, so it catches mentions like
    "Marksans Pharma" that only match a ticker-only source when the raw
    mention happens to equal the ticker itself. It only covers NSE-listed
    equities, though, so the broker master (which also has BSE) is checked
    first. Degrades to an empty index on any failure — this is an
    unauthenticated third-party scrape with no SLA, not a service Sangam
    controls, so it must never be able to fail the pipeline.
    """
    global _nse_lookup_cache, _nse_prefix_cache
    if _nse_lookup_cache is not None:
        return _nse_lookup_cache
    from . import db

    try:
        rows = db.fetch_nse_equity_list()
    except Exception as e:
        print(f"normalize: NSE equity list unavailable, skipping ({e})")
        rows = []

    lookup: dict[str, Resolution] = {}
    prefix_index: PrefixIndex = {}
    for row in rows:
        symbol, name = row.get("symbol") or "", row.get("name") or ""
        if not symbol or not name:
            continue
        resolution = Resolution(symbol, "stock", method="nse_master")
        for alias in (name, symbol):
            lookup.setdefault(key(alias), resolution)
        _index_name(prefix_index, name, resolution)

    if rows:
        print(f"normalize: NSE equity list loaded ({len(lookup)} alias(es))")
    _nse_lookup_cache = lookup
    _nse_prefix_cache = prefix_index
    return lookup


def _prefix_resolve(normalized: str) -> Resolution | None:
    """Resolve a mention that's a strict word-prefix of exactly one candidate
    company name — the shortened spoken form ("Happiest Minds") of a longer
    registered name ("Happiest Minds Technologies Limited"). This only ever
    fills in a dropped trailing word; it never confuses two different
    companies, and refuses outright if the prefix matches more than one.
    Single-word mentions never reach here productively (see _index_name) —
    a common one-word truncation ("Adani", "HDFC") could prefix dozens of
    unrelated group companies, which is exactly the ambiguity this whole
    module exists to avoid guessing through.
    """
    words = tuple(normalized.split())
    if len(words) < 2:
        return None
    # Broker lookup first (checked before this function even runs, same as
    # the exact-match order), then NSE — first unambiguous hit wins.
    for prefix_index in (_broker_prefix_cache or {}, _nse_prefix_cache or {}):
        candidates = prefix_index.get(words[0], [])
        matches = {
            resolution.symbol: resolution
            for candidate_words, resolution in candidates
            if len(candidate_words) > len(words) and candidate_words[: len(words)] == words
        }
        if len(matches) == 1:
            return next(iter(matches.values()))
    return None


def is_generic(raw_mention: str) -> bool:
    return key(raw_mention) in GENERIC_MENTIONS


def resolve_record(raw_mention: str, instrument_type: str | None = None) -> Resolution | None:
    normalized = key(raw_mention)
    if not normalized or normalized in GENERIC_MENTIONS:
        return None
    declared = _LOOKUPS.get(instrument_type or "", {}).get(normalized)
    if declared:
        return declared
    matches = {lookup[normalized] for lookup in _LOOKUPS.values() if normalized in lookup}
    if len(matches) == 1:
        return next(iter(matches))
    if matches:
        return None  # ambiguous across curated catalogs; stay conservative
    if instrument_type in (None, "", "stock"):
        exact = _broker_lookup().get(normalized) or _nse_company_lookup().get(normalized)
        return exact or _prefix_resolve(normalized)
    return None


def resolve(raw_mention: str, instrument_type: str | None = None) -> str | None:
    resolution = resolve_record(raw_mention, instrument_type)
    return resolution.symbol if resolution else None


def run() -> StageResult:
    """Backfill canonical symbols/types for existing mention rows."""
    from . import db

    rows = db.mentions_for_normalization()
    updates: dict[int, tuple[str, str]] = {}
    resolvable = 0
    for row in rows:
        resolution = resolve_record(row.get("raw_mention") or "", row.get("instrument_type"))
        if not resolution:
            continue
        resolvable += 1
        if (row.get("resolved_symbol"), row.get("instrument_type")) != (
            resolution.symbol, resolution.instrument_type
        ):
            updates[int(row["id"])] = (resolution.symbol, resolution.instrument_type)

    with db.connect() as conn:
        changed = db.set_mention_normalizations(conn, updates)
    print(f"normalize: {changed} row(s) updated; {resolvable}/{len(rows)} mention(s) resolved")
    return StageResult("normalize", changed, len(rows))


def unresolved_report(rows: list[dict], min_count: int = 2) -> list[dict]:
    """Group still-unresolved stock mentions by normalized text, most frequent
    first — the safety net for names this module deliberately declines to
    guess (mishearings, incomplete names not caught by any source). One-off
    counts are omitted by default: a single occurrence is usually noise (an
    ASR fluke, a rare small-cap) rather than something worth a curated alias.
    """
    groups: dict[str, dict] = {}
    for row in rows:
        if row.get("resolved_symbol") or row.get("instrument_type") != "stock":
            continue
        raw = (row.get("raw_mention") or "").strip()
        if not raw or is_generic(raw):
            continue
        entry = groups.setdefault(key(raw), {"raw_mention": raw, "count": 0})
        entry["count"] += 1
    return sorted(
        (g for g in groups.values() if g["count"] >= min_count),
        key=lambda g: g["count"],
        reverse=True,
    )


def run_unresolved_report(min_count: int = 2) -> StageResult:
    """CLI entry point: print unresolved stock mentions worth a look."""
    from . import db

    rows = db.mentions_for_normalization()
    report = unresolved_report(rows, min_count=min_count)
    if not report:
        print(f"normalize: no unresolved stock mention has {min_count}+ occurrence(s)")
    else:
        print(f"normalize: {len(report)} unresolved stock name(s) with {min_count}+ occurrence(s):")
        for item in report:
            print(f"  {item['count']:>3}x  {item['raw_mention']}")
    return StageResult("unresolved", len(report), len(rows))


def sync_instrument_names() -> StageResult:
    """Refresh the app-facing symbol -> company name lookup (instrument_names)
    from NSE's public equity list and a locally-bundled BSE list, so Radar
    and similar screens can show a name alongside a bare ticker instead of
    just the code. BSE rows are keyed with the same "BSE:" prefix the app
    uses for BSE-only watchlist entries — so a ticker that happens to exist
    on both exchanges with different underlying companies can never show the
    wrong one's name.
    """
    from . import db

    nse_rows = db.fetch_nse_equity_list()
    bse_rows = db.fetch_bse_equity_list()

    pairs = [
        {"symbol": (row.get("symbol") or "").strip(), "name": (row.get("name") or "").strip()}
        for row in nse_rows
        if row.get("symbol") and row.get("name")
    ]
    pairs += [
        {"symbol": f"BSE:{row['symbol'].strip()}", "name": row["name"].strip()}
        for row in bse_rows
        if row.get("symbol") and row.get("name") and row.get("status", "Active") == "Active"
    ]

    with db.connect() as conn:
        updated = db.upsert_instrument_names(conn, pairs)
    print(
        f"instrument_names: {updated} name(s) synced "
        f"({len(nse_rows)} NSE, {len(bse_rows)} BSE row(s) read)"
    )
    return StageResult("instrument_names", updated, len(nse_rows) + len(bse_rows))


if __name__ == "__main__":
    raise SystemExit(0 if run().ok else 1)
