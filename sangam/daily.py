"""Generate a daily consensus brief and an optional vertical MP4.

The Markdown, JSON, narration, and SRT artifacts require only Python. If ffmpeg is
available, the same command also renders a silent text-first 1080x1920 MP4.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

from . import config, consensus, db


DISCLAIMER = "Creator commentary summary — not investment advice. Verify independently."


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _leading_action(item: dict) -> str:
    counts = item.get("action_counts") or {}
    return max(counts, key=counts.get) if counts else "neutral"


def build_brief(
    rows: list[dict], *, now: datetime, hours: int, max_items: int,
    min_creators: int = 2,
) -> dict:
    cutoff = now - timedelta(hours=hours)
    recent = [
        row for row in rows
        if (_parse_time((row.get("video") or {}).get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    ]
    ranked = [
        item for item in consensus.build(recent, config.CONSENSUS_MIN_CONFIDENCE)
        if item["resolved"]
    ]
    items = [item for item in ranked if item["creator_count"] >= min_creators][:max_items]
    observations = [
        item for item in ranked if item["creator_count"] < min_creators
    ][:max(0, max_items - len(items))]
    return {
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "source_mentions": len(recent),
        "items": items,
        "observations": observations,
        "disclaimer": DISCLAIMER,
    }


def _markdown(brief: dict) -> str:
    day = brief["generated_at"][:10]
    lines = [f"# Sangam Daily Brief — {day}", "", DISCLAIMER, ""]
    if not brief["items"]:
        lines.extend(["No cross-creator consensus in this window.", ""])
    for index, item in enumerate(brief["items"], 1):
        actions = ", ".join(f"{key}: {value}" for key, value in item["action_counts"].items())
        lines.extend([
            f"## {index}. {item['name']}", "",
            f"- Creators: {item['creator_count']} ({', '.join(item['creators'])})",
            f"- Creator-weighted conviction: {item['avg_conviction']}/5",
            f"- Views: {actions or 'neutral'}",
            f"- Latest note: {item.get('sample_note') or 'No short note available.'}", "",
        ])
    if brief["observations"]:
        lines.extend(["## Single-creator observations (not consensus)", ""])
        for item in brief["observations"]:
            lines.append(
                f"- **{item['name']}** — {_leading_action(item).replace('_', ' ')}; "
                f"{item.get('sample_note') or 'no short note'}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _narration(brief: dict) -> str:
    lines = []
    if brief["items"]:
        lines.append("Here is today's Sangam cross-creator consensus.")
    else:
        lines.append("No cross-creator consensus was found today.")
    for item in brief["items"]:
        action = _leading_action(item).replace("_", " ")
        lines.append(
            f"{item['name']}: {item['creator_count']} creator voices, mainly {action}, "
            f"with average conviction {item['avg_conviction']} out of 5."
        )
    if brief["observations"]:
        lines.append("A few single-creator observations, which are not consensus.")
        for item in brief["observations"]:
            lines.append(
                f"{item['name']}: {_leading_action(item).replace('_', ' ')}, "
                f"conviction {item['avg_conviction']} out of 5."
            )
    lines.append(DISCLAIMER)
    return "\n".join(lines) + "\n"


def _srt(brief: dict, seconds_per_slide: int = 5) -> str:
    slides = ["Sangam Daily Market Brief"] + [
        f"{item['name']}\n{item['creator_count']} creators · {_leading_action(item).replace('_', ' ')} · {item['avg_conviction']}/5"
        for item in brief["items"]
    ] + [
        f"Single-source observation\n{item['name']} · {_leading_action(item).replace('_', ' ')} · {item['avg_conviction']}/5"
        for item in brief["observations"]
    ] + [DISCLAIMER]
    blocks = []
    for index, text in enumerate(slides, 1):
        start = (index - 1) * seconds_per_slide
        end = index * seconds_per_slide
        stamp = lambda value: f"00:{value // 60:02d}:{value % 60:02d},000"
        blocks.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{text}\n")
    return "\n".join(blocks)


def _font_path() -> Path | None:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    )
    return next((path for path in candidates if path.exists()), None)


def render_video(brief: dict, directory: Path) -> Path | None:
    ffmpeg = shutil.which(config.FFMPEG_BIN)
    font = _font_path()
    if not ffmpeg or not font:
        return None
    slides = ["SANGAM\nDAILY MARKET BRIEF"]
    slides.extend(
        f"{item['name']}\n\n{item['creator_count']} creator voices\n"
        f"{_leading_action(item).replace('_', ' ').upper()} · {item['avg_conviction']}/5\n\n"
        f"{item.get('sample_note') or ''}"
        for item in brief["items"]
    )
    slides.extend(
        f"SINGLE-CREATOR OBSERVATION\n\n{item['name']}\n\n"
        f"{_leading_action(item).replace('_', ' ').upper()} · {item['avg_conviction']}/5\n\n"
        f"{item.get('sample_note') or ''}"
        for item in brief["observations"]
    )
    slides.append(DISCLAIMER)
    filters = []
    for index, slide in enumerate(slides):
        wrapped = "\n".join(
            line for paragraph in slide.splitlines()
            for line in (textwrap.wrap(paragraph, width=28) or [""])
        )
        text_path = directory / f"slide-{index:02d}.txt"
        text_path.write_text(wrapped, encoding="utf-8")
        start, end = index * 5, (index + 1) * 5
        escaped_text = str(text_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        escaped_font = str(font).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filters.append(
            "drawtext="
            f"fontfile='{escaped_font}':textfile='{escaped_text}':"
            "fontcolor=white:fontsize=58:line_spacing=20:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"enable='between(t,{start},{end})'"
        )
    output = directory / "brief.mp4"
    duration = len(slides) * 5
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        f"color=c=0x081426:s=1080x1920:r=30:d={duration}",
        "-vf", ",".join(filters), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True)
    return output


def generate(
    *, out_root: Path, hours: int, max_items: int, now: datetime | None = None,
    video: bool = True, min_creators: int = 2,
) -> tuple[Path, Path | None]:
    now = now or datetime.now(timezone.utc)
    brief = build_brief(
        db.recent_mentions_for_report(), now=now, hours=hours, max_items=max_items,
        min_creators=min_creators,
    )
    directory = out_root / now.strftime("%Y-%m-%d")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "brief.json").write_text(
        json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "brief.md").write_text(_markdown(brief), encoding="utf-8")
    (directory / "narration.txt").write_text(_narration(brief), encoding="utf-8")
    (directory / "captions.srt").write_text(_srt(brief), encoding="utf-8")
    rendered = render_video(brief, directory) if video else None
    return directory, rendered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=config.REPORT_DIR)
    parser.add_argument("--hours", type=int, default=config.DAILY_REPORT_HOURS)
    parser.add_argument("--max-items", type=int, default=config.DAILY_MAX_ITEMS)
    parser.add_argument("--min-creators", type=int, default=config.DAILY_MIN_CREATORS)
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()
    directory, video = generate(
        out_root=args.out, hours=args.hours, max_items=args.max_items,
        video=not args.no_video, min_creators=args.min_creators,
    )
    print(f"daily: report package written to {directory}")
    if video:
        print(f"daily: vertical video written to {video}")
    elif not args.no_video:
        print("daily: ffmpeg/font unavailable; JSON, Markdown, narration and SRT are ready")


if __name__ == "__main__":
    main()
