"""Stage 3: transcript (or description fallback) -> structured mentions + a
grounded digest, via the Gemini REST API with httpx (no SDK, no compiled deps).
"""
from __future__ import annotations
import json
import sys

import httpx

from . import config, db, normalize
from .outcome import StageResult

ACTIONS = ["buy", "sell", "hold", "wait_for_dip", "radar", "future_opportunity", "neutral"]
TYPES = ["stock", "mutual_fund", "sector"]

# JSON schema handed to Gemini so it returns exactly this shape (no pydantic needed).
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_mention": {"type": "string"},
                    "instrument_type": {"type": "string", "enum": TYPES},
                    "action": {"type": "string", "enum": ACTIONS},
                    "conviction": {"type": "integer"},
                    "note": {"type": "string"},
                    "long_note": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["raw_mention", "instrument_type", "action", "conviction", "note", "long_note", "confidence", "evidence"],
            },
        },
    },
    "required": ["summary", "mentions"],
}

SYSTEM = f"""You analyze transcripts of Indian finance YouTube videos. Language is \
often mixed Hindi/English (Hinglish) and may be in Devanagari; names are sometimes \
transliterated (e.g. "Reliance ka target", "PSU banks", "Bajaj twins").

Extract EVERY specific stock, mutual fund, or sector the speaker discusses, with the \
speaker's implied view.

instrument_type: one of {TYPES}.
action: one of {ACTIONS}.
  - radar = watchlist / keep an eye on
  - wait_for_dip = wants in, but at a lower price
  - future_opportunity = bullish long-term, not an immediate call
  - neutral = mentioned with no directional view

Hard rules:
- If the video has no real financial content (course promo, vlog, warning, motivation), \
return an EMPTY mentions list and say so in the summary.
- NEVER treat hashtags (#nifty), smallcase/course/book plugs, channel names, or SEBI \
disclaimers as mentions. Only count instruments the speaker actually discusses.
- note: ONE short line (<=15 words) — the headline of what the speaker said about THIS instrument.
- long_note: a fuller 2-5 sentence summary of everything the speaker said about THIS instrument \
(reasoning, targets, price levels, concerns, results), grounded strictly in the transcript. If it \
was only a passing mention, keep it brief — do not pad or invent.
- conviction: integer 1-5 for how strongly the speaker pushes this view — 1 = passing/neutral \
mention, 3 = a clear stated view, 5 = an emphatic high-conviction call. Neutral mentions are 1-2.
- evidence must be grounded in the text, <=15 words.
- Base EVERYTHING strictly on the transcript. Prefer specific names and figures actually \
stated; never add outside knowledge or invent numbers.
- summary: a faithful, detailed digest grounded ONLY in the transcript. Write a 2-3 \
sentence overview, then 3-6 bullet lines (each starting with "- ") covering the specific \
stocks/sectors discussed and what was said about each, any concrete numbers actually \
mentioned (targets, valuations, growth %, price levels, results), and the speaker's \
overall stance. For a non-financial video, a single line stating what it is is enough.
"""

_RESOLVED_MODEL: str | None = None
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _model_candidates() -> list[str]:
    out: list[str] = []
    for m in (config.GEMINI_MODEL, "gemini-flash-lite-latest", "gemini-2.5-flash-lite",
              "gemini-3-flash", "gemini-flash-latest"):
        if m and m not in out:
            out.append(m)
    return out


def _body(text: str, use_thinking: bool) -> dict:
    gen = {
        "temperature": 0,
        "responseMimeType": "application/json",
        "responseSchema": RESPONSE_SCHEMA,
    }
    if use_thinking:
        gen["thinkingConfig"] = {"thinkingBudget": 0}   # cheap: no thinking
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": gen,
    }


def _post(model: str, text: str, use_thinking: bool) -> httpx.Response:
    return db._do(
        "POST", GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": config.GEMINI_KEY, "Content-Type": "application/json"},
        json=_body(text, use_thinking), timeout=120,
    )


def _generate(text: str) -> dict:
    """Call Gemini REST; fall back across model ids on 404, and drop thinkingConfig
    if a model rejects it. Caches the first model that works. Returns a dict."""
    global _RESOLVED_MODEL
    if not config.GEMINI_KEY:
        raise RuntimeError("SANGAM_GEMINI_KEY not set in .env")
    models = [_RESOLVED_MODEL] if _RESOLVED_MODEL else _model_candidates()
    last = None
    for model in models:
        resp = _post(model, text, True)
        if resp.status_code == 400 and "think" in resp.text.lower():
            resp = _post(model, text, False)      # this model won't take thinkingConfig
        if resp.status_code == 404:
            last = resp                           # wrong model id -> try next candidate
            continue
        resp.raise_for_status()
        if _RESOLVED_MODEL != model:
            _RESOLVED_MODEL = model
            print(f"  (using model: {model})")
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        raw = "".join(p["text"] for p in parts if "text" in p)   # skip thought parts
        return json.loads(raw)
    if last is not None:
        last.raise_for_status()
    raise RuntimeError("no model succeeded")


def _extract_one(title, transcript_status, transcript_text, description):
    if transcript_status == "done" and transcript_text:
        text = f"TITLE: {title}\n\nTRANSCRIPT:\n{transcript_text}"
        source, cap = "transcript", 1.0
    elif description:
        text = (f"TITLE: {title}\n\nNOTE: No transcript available — only the promotional, "
                f"low-trust description below. Extract only instruments EXPLICITLY named as "
                f"discussed; be conservative.\n\nDESCRIPTION:\n{description}")
        source, cap = "description", config.DESC_ONLY_MAX_CONFIDENCE
    else:
        return ("no transcript or description", [], None)

    result = _generate(text)
    rows = []
    seen = set()
    for m in result.get("mentions", []):
        raw_mention = str(m.get("raw_mention") or "").strip()
        instrument_type = m.get("instrument_type")
        action = m.get("action")
        if not raw_mention or instrument_type not in TYPES or action not in ACTIONS:
            continue
        key = (raw_mention.casefold(), instrument_type)
        if key in seen:
            continue
        seen.add(key)
        conviction = max(1, min(5, int(m.get("conviction") or 1)))
        confidence = max(0.0, min(float(m.get("confidence") or 0), cap, 1.0))
        rows.append({
            "raw_mention": raw_mention,
            "resolved_symbol": normalize.resolve(raw_mention, instrument_type),
            "instrument_type": instrument_type,
            "action": action,
            "conviction": conviction,
            "note": m.get("note"),
            "long_note": m.get("long_note"),
            "confidence": confidence,
            "evidence": m.get("evidence"),
        })
    return (str(result.get("summary") or "").strip(), rows, source)


def run() -> StageResult:
    total = 0
    processed = 0
    errors: list[str] = []
    with db.connect() as conn:
        pending = db.videos_needing_extract(conn)

    for video_id, title, tstatus, ttext, desc, previous_attempts in pending:
        attempt = previous_attempts + 1
        try:
            summary, rows, source = _extract_one(title, tstatus, ttext, desc)
            with db.connect() as conn:
                if source:
                    db.replace_extraction(conn, video_id, summary, rows, source, attempt)
                else:
                    db.save_extraction(conn, video_id, summary, "skipped", attempts=attempt)
        except Exception as e:
            terminal = attempt >= config.MAX_STAGE_ATTEMPTS
            status = "error" if terminal else "retry"
            next_retry = None if terminal else db.retry_at(attempt)
            message = f"extract failed for {title} (attempt {attempt}): {e}"
            errors.append(message)
            try:
                with db.connect() as conn:
                    db.save_extraction(conn, video_id, None, status, attempts=attempt,
                                       error=str(e), next_retry_at=next_retry)
            except Exception as save_error:
                errors.append(f"could not persist extraction failure for {title}: {save_error}")
            print(f"  ! {message}; status={status}")
            processed += 1
            continue
        total += len(rows)
        processed += 1
        print(f"  [{source or 'skipped'}] {title} -> {len(rows)} mention(s) | {summary[:70]}")

    print(f"extract: {total} mention(s) across {len(pending)} video(s); {len(errors)} error(s)")
    return StageResult("extract", total, processed, errors)


def list_models():
    """Best-effort model list (often blocked on AI Studio keys — harmless)."""
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                      headers={"x-goog-api-key": config.GEMINI_KEY}, timeout=30)
        r.raise_for_status()
        for m in r.json().get("models", []):
            print(m.get("name"))
    except Exception as e:
        print(f"Could not list models (often blocked; harmless): {e}")
        print(f"Just run extraction; it auto-falls-back. Default model: {config.GEMINI_MODEL}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "models":
        list_models()
    else:
        raise SystemExit(0 if run().ok else 1)
