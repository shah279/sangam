"""Stage 2 (MVP): pull captions via youtube-transcript-api (1.x instance API).

Mixed-language channels: we prefer a manually-created transcript, then any
auto-generated one, in whatever language exists. If the AWS IP gets blocked,
set SANGAM_PROXY_URL in .env — no code change needed."""
from __future__ import annotations
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from . import config, db


def _api() -> YouTubeTranscriptApi:
    if config.PROXY_URL:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=config.PROXY_URL, https_url=config.PROXY_URL)
        )
    return YouTubeTranscriptApi()


def fetch_caption(api: YouTubeTranscriptApi, video_id: str) -> str | None:
    try:
        tlist = api.list(video_id)
    except Exception:
        return None
    # Prefer manual over generated; language-agnostic (we want the words).
    chosen = None
    for t in tlist:
        if chosen is None:
            chosen = t
        if not t.is_generated:      # a human-made transcript beats auto
            chosen = t
            break
    if chosen is None:
        return None
    try:
        raw = chosen.fetch().to_raw_data()   # list of {'text','start','duration'}
        text = " ".join(d["text"] for d in raw).strip()
        return text or None
    except Exception:
        return None


def run() -> int:
    api = _api()
    done = 0
    with db.connect() as conn:
        pending = db.videos_needing_captions(conn)

    for video_id, title in pending:
        try:
            text = fetch_caption(api, video_id)
            with db.connect() as conn:
                if text:
                    db.save_transcript(conn, video_id, text, "captions", "done")
                    done += 1
                    print(f"  captions: {title}  ({len(text)} chars)")
                else:
                    db.save_transcript(conn, video_id, None, None, "none")
                    print(f"  no captions: {title}")
        except Exception as e:
            print(f"  ! caption step failed for {title}: {e}")
            continue

    print(f"captions: {done}/{len(pending)} transcribed")
    return done


if __name__ == "__main__":
    run()
