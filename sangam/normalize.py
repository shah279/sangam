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
    "HDFCBANK": ("HDFC Bank",),
    "HEROMOTOCO": ("Hero MotoCorp", "Hero Motocorp"),
    "HFCL": ("HFCL",),
    "HINDCOPPER": ("Hindustan Copper",),
    "HYUNDAI": ("Hyundai Motor India", "Hyundai"),
    "ICICIBANK": ("ICICI Bank",),
    "IDEA": ("Vodafone Idea", "Vi"),
    "INDIGO": ("InterGlobe Aviation", "IndiGo"),
    "INFY": ("Infosys",),
    "IRCTC": ("IRCTC",),
    "ITC": ("ITC", "ITC Ltd"),
    "JIOFIN": ("Jio Financial", "Jio Finance", "Jio Financial Services"),
    "KALYANKJIL": ("Kalyan Jewellers",),
    "LAURUSLABS": ("Laurus Labs",),
    "LICI": ("LIC", "Life Insurance Corporation of India"),
    "LT": ("L&T", "L and T", "Larsen and Toubro"),
    "MANAPPURAM": ("Manappuram Finance", "Manappuram"),
    "MARUTI": ("Maruti", "Maruti Suzuki"),
    "MTARTECH": ("MTAR Technologies", "MTAR Tech"),
    "NAUKRI": ("Info Edge", "Info Edge India"),
    "NEULANDLAB": ("Neuland Labs", "Neuland Laboratories"),
    "NMDC": ("NMDC",),
    "ONGC": ("ONGC", "Oil and Natural Gas Corporation"),
    "ONE97": ("Paytm", "One97 Communications"),
    "PIIND": ("PI Industries",),
    "POLICYBZR": ("PB Fintech", "Policybazaar"),
    "POWERINDIA": ("Hitachi Energy", "Hitachi Energy India"),
    "RELIANCE": ("Reliance", "Reliance Industries", "RIL"),
    "RVNL": ("RVNL", "Rail Vikas Nigam"),
    "SANSERA": ("Sansera Engineering", "Sansera"),
    "SBIN": ("SBI", "State Bank of India"),
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
    "WIPRO": ("Wipro",),
    "YESBANK": ("Yes Bank",),
    "ZEEL": ("Zee Entertainment", "Zee Entertainment Enterprises"),
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
    "active etfs", "banking and psu fund", "corporate bond fund", "etf", "etfs",
    "global etfs", "index fund", "low duration fund", "money market fund",
    "mutual fund", "mutual funds", "passive funds", "sif", "sip", "stock market",
}


def key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
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


def _broker_lookup() -> dict[str, Resolution]:
    """Lazily build a name/symbol -> Resolution index from the separate
    project's NSE/BSE instrument master, caching it for the process lifetime.
    Falls back to an empty index (no broker-backed resolutions) on any error,
    so a misconfigured or unreachable second project degrades gracefully
    instead of failing normalization for everyone.
    """
    global _broker_lookup_cache
    if _broker_lookup_cache is not None:
        return _broker_lookup_cache
    from . import db

    try:
        rows = db.fetch_broker_instruments()
    except Exception as e:
        print(f"normalize: broker instrument master unavailable, skipping ({e})")
        rows = []

    lookup: dict[str, Resolution] = {}
    # NSE sorted first so it wins ties with BSE on the same normalized name.
    for row in sorted(rows, key=lambda r: r.get("exchange") != "NSE"):
        if row.get("instrument_type") != "EQ":
            continue  # indices/derivatives aren't priceable via prices.py yet
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        resolution = Resolution(symbol, "stock", method="broker_master")
        aliases = (row.get("name"), symbol, _strip_series_suffix(row.get("trading_symbol")))
        for alias in filter(None, aliases):
            lookup.setdefault(key(alias), resolution)

    if rows:
        print(f"normalize: broker instrument master loaded ({len(lookup)} alias(es))")
    _broker_lookup_cache = lookup
    return lookup


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
        return _broker_lookup().get(normalized)
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


if __name__ == "__main__":
    raise SystemExit(0 if run().ok else 1)
