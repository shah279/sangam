"""Sangam configuration. Secrets come from the environment (.env); the channel
list lives here. Talks to Supabase + Gemini over HTTP (no compiled deps)."""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

# --- Supabase (REST / PostgREST) ---
SUPABASE_URL = os.environ.get("SANGAM_SUPABASE_URL", "").rstrip("/")   # https://<ref>.supabase.co
SUPABASE_KEY = os.environ.get("SANGAM_SUPABASE_KEY")                    # service_role key

# --- Gemini (REST) ---
GEMINI_KEY = os.environ.get("SANGAM_GEMINI_KEY")
GEMINI_MODEL = os.environ.get("SANGAM_GEMINI_MODEL", "gemini-3.1-flash-lite")

# --- Optional caption proxy (not needed on a residential IP like a phone) ---
PROXY_URL = os.environ.get("SANGAM_PROXY_URL")

# --- Settings ---
LOOKBACK_HOURS = int(os.environ.get("SANGAM_LOOKBACK_HOURS", "24"))
RSS = "https://www.youtube.com/feeds/videos.xml?playlist_id={}"
CAPTION_LANGS = ["hi", "en", "en-IN"]
DESC_ONLY_MAX_CONFIDENCE = 0.4

CHANNELS = [
    {"name": "Sahil Bhadviya",                 "channel_id": "UCdc6ObxhdQ8eZIFquU2xolA", "handle": "sahilbhadviya",      "source_type": "opinion",  "is_sebi_registered": False},
    {"name": "SOIC",                           "channel_id": "UCB7GnQlJPIL6rBBqEoX87vA", "handle": "SOICfinance",        "source_type": "research", "is_sebi_registered": False},
    {"name": "Invest Yadnya",                  "channel_id": "UCPohbSYq4IXhv0yxiy-sT4g", "handle": "InvestYadnya",       "source_type": "educator", "is_sebi_registered": True},
    {"name": "Basant Maheshwari - Equity Desk","channel_id": "UCqvuLvdIkUjAtSFrKw5LhXg", "handle": "bmtheequitydesk",    "source_type": "research", "is_sebi_registered": True},
    {"name": "Raghav Kumar",                   "channel_id": "UCKkFcZ_xE1Pho9-MUJnI01g", "handle": "RaghavKumarGarg",    "source_type": "research", "is_sebi_registered": True},
    {"name": "Sovrenn",                        "channel_id": "UC9dx7yLXduHg9XeQyqf4WWQ", "handle": "SovrennOfficial",    "source_type": "research", "is_sebi_registered": False},
    {"name": "Vishal Khandelwal - Safal Niveshak","channel_id": "UCDpRrAXMYlxFz3a5-z8pE7w","handle": "khandelwal.vishal","source_type": "educator", "is_sebi_registered": False},
    {"name": "Akshat Shrivastava",             "channel_id": "UCqW8jxh4tH1Z1sWPbkGWL4g", "handle": "AkshatZayn",         "source_type": "opinion",  "is_sebi_registered": False},
    {"name": "Pranjal Kamra",                  "channel_id": "UCwAdQUuPT6laN-AQR17fe1g", "handle": "pranjalkamra",       "source_type": "educator", "is_sebi_registered": False},
    {"name": "Stock Market Ka Commando",       "channel_id": "UChneGqGy_lmvfcR1v_avL6g", "handle": "stockmarketcommando","source_type": "educator", "is_sebi_registered": False},
    {"name": "Rahul Jain",                     "channel_id": "UC2MU9phoTYy5sigZCkrvwiw", "handle": "torahulj",           "source_type": "research", "is_sebi_registered": True},
    {"name": "Stock 4 Retail by Umesh",        "channel_id": "UChcQR_Z7YmqRQMZ6lxjD8JA", "handle": "Stock4RetailbyUmesh","source_type": "educator", "is_sebi_registered": False},
]


def feeds_for(channel_id: str) -> list[tuple[str, bool]]:
    base = channel_id[2:]
    return [(RSS.format("UULF" + base), False), (RSS.format("UUSH" + base), True)]
