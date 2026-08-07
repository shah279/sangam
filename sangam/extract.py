"""Stage 3: transcript (or description fallback) -> structured mentions + a
one-line summary, via Gemini 3.1 Flash-Lite with a strict JSON schema.

Rules baked into the prompt:
- Return an empty mentions list for non-financial content (promos, vlogs, warnings).
- Ignore hashtags, smallcase/book plugs, and SEBI disclaimers — those are not calls.
- Handle mixed Hindi/English/Hinglish and Devanagari.
Description-only videos (no captions) run a conservative pass and are capped at a
low confidence and tagged source='description'.
"""
from __future__ import annotations

import sys

from pydantic import BaseModel

from . import config, db, normalize

ACTIONS = ["buy", "sell", "hold", "wait_for_dip", "radar", "future_opportunity", "neutral"]
TYPES = ["stock", "mutual_fund", "sector"]


class Mention(BaseModel):
    raw_mention: str          # name exactly as referenced, e.g. "Reliance", "PSU banks"
    instrument_type: str      # stock | mutual_fund | sector
    action: str               # one of ACTIONS
    confidence: float         # 0.0 - 1.0
    evidence: str             # <=15-word quote/paraphrase justifying the action


class Extraction(BaseModel):
    summary: str              # one line; for non-financial videos, say what it is
    mentions: list[Mention]


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
- evidence must be grounded in the text, <=15 words.
- Base EVERYTHING strictly on the transcript. Prefer specific names and figures
  actually stated; never add outside knowledge or invent numbers.
- summary: a faithful, detailed digest grounded ONLY in the transcript. Write a
  2-3 sentence overview, then 3-6 bullet lines (each starting with "- ") covering:
  the specific stocks/sectors discussed and what was said about each, any concrete
  numbers actually mentioned (targets, valuations, growth %, price levels, results),
  and the speaker's overall stance/takeaway. For a non-financial video, a single
  line stating what it is is enough.
"""


def _client():
    from google import genai
    if not config.GEMINI_KEY:
        raise RuntimeError("SANGAM_GEMINI_KEY is not set in .env")
    return genai.Client(api_key=config.GEMINI_KEY)


_RESOLVED_MODEL: str | None = None


def _model_candidates() -> list[str]:
    """Configured model first, then cheap current fallbacks. Needed because the
    ListModels method is often blocked on AI Studio keys, so we can't look one up."""
    out: list[str] = []
    for m in (config.GEMINI_MODEL, "gemini-flash-lite-latest", "gemini-2.5-flash-lite",
              "gemini-3-flash", "gemini-flash-latest"):
        if m and m not in out:
            out.append(m)
    return out


def _make_config(use_thinking: bool):
    from google.genai import types
    kw = dict(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=Extraction,
        temperature=0,
    )
    if use_thinking:
        kw["thinking_config"] = types.ThinkingConfig(thinking_budget=0)  # cheap: no thinking
    return types.GenerateContentConfig(**kw)


def _generate(client, text: str) -> Extraction:
    """Call Gemini; auto-fall-back across model ids on NOT_FOUND, and drop
    thinking_config if a model rejects it. Caches the first model that works."""
    global _RESOLVED_MODEL
    from google.genai import errors
    models = [_RESOLVED_MODEL] if _RESOLVED_MODEL else _model_candidates()
    last_err = None
    for model in models:
        try:
            try:
                resp = client.models.generate_content(model=model, contents=text, config=_make_config(True))
            except errors.ClientError as e:
                if e.code == 400 and "think" in str(e).lower():
                    resp = client.models.generate_content(model=model, contents=text, config=_make_config(False))
                else:
                    raise
            if _RESOLVED_MODEL != model:
                _RESOLVED_MODEL = model
                print(f"  (using model: {model})")
            return resp.parsed
        except errors.ClientError as e:
            if e.code == 404 or getattr(e, "status", None) == "NOT_FOUND":
                last_err = e
                continue
            raise
    raise last_err


def _extract_one(client, title, transcript_status, transcript_text, description):
    """Returns (summary, mentions_list_of_dict, source) or (summary, [], None) to skip."""
    if transcript_status == "done" and transcript_text:
        text = f"TITLE: {title}\n\nTRANSCRIPT:\n{transcript_text}"
        source = "transcript"
        cap = 1.0
    elif description:
        # No captions: conservative description-only pass, low confidence.
        text = (
            f"TITLE: {title}\n\nNOTE: No transcript available — only the video "
            f"description below, which is promotional and low-trust. Extract only "
            f"instruments EXPLICITLY named as discussed; be conservative.\n\n"
            f"DESCRIPTION:\n{description}"
        )
        source = "description"
        cap = config.DESC_ONLY_MAX_CONFIDENCE
    else:
        return ("no transcript or description", [], None)

    result = _generate(client, text)
    rows = []
    for m in result.mentions:
        rows.append(
            {
                "raw_mention": m.raw_mention,
                "resolved_symbol": normalize.resolve(m.raw_mention, m.instrument_type),
                "instrument_type": m.instrument_type,
                "action": m.action,
                "confidence": min(float(m.confidence), cap),
                "evidence": m.evidence,
            }
        )
    return (result.summary, rows, source)


def run() -> int:
    client = _client()
    total = 0
    with db.connect() as conn:
        pending = db.videos_needing_extract(conn)

    for video_id, title, tstatus, ttext, desc in pending:
        try:
            summary, rows, source = _extract_one(client, title, tstatus, ttext, desc)
        except Exception as e:
            with db.connect() as conn:
                db.save_extraction(conn, video_id, None, "error")
            print(f"  extract ERROR: {title} -> {e}")
            continue
        with db.connect() as conn:
            db.delete_mentions(conn, video_id)  # idempotent: safe to re-run extraction
            if source:
                db.insert_mentions(conn, video_id, rows, source)
                db.save_extraction(conn, video_id, summary, "done")
            else:
                db.save_extraction(conn, video_id, summary, "skipped")
        total += len(rows)
        tag = source or "skipped"
        print(f"  [{tag}] {title} -> {len(rows)} mention(s) | {summary[:70]}")

    print(f"extract: {total} mention(s) across {len(pending)} video(s)")
    return total


def list_models():
    """Best-effort: print model ids your key can use. ListModels is often blocked
    on AI Studio keys — that's harmless, since extraction uses generateContent."""
    try:
        client = _client()
        for m in client.models.list():
            print(m.name)
    except Exception as e:
        print("Could not list models (ListModels is often blocked on AI Studio keys):")
        print(f"  {e}")
        print("\nThat's fine — extraction uses generateContent, not ListModels.")
        print(f"Just run:  python3 -m sangam.ingest extract   (default model: {config.GEMINI_MODEL})")
        print("If a model id is wrong, extraction auto-tries fallbacks and prints the one that works.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "models":
        list_models()
    else:
        run()
