#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCQGR5xfUNaqu8v4RYmOywHw"
START_MARKER = "<!-- YOUTUBE_CARDS_START -->"
END_MARKER = "<!-- YOUTUBE_CARDS_END -->"


def normalize_title(raw: str) -> str:
    base = raw.split("#", 1)[0].strip()
    return base or raw.strip()


def fetch_entries(limit: int) -> list[dict[str, str]]:
    request = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
    except (ssl.SSLCertVerificationError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(exc, urllib.error.URLError) and not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        # Fallback for environments with incomplete local CA bundles.
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=20, context=insecure_ctx) as response:
            data = response.read()

    root = ET.fromstring(data)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }

    entries: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        video_id = (entry.findtext("yt:videoId", default="", namespaces=ns) or "").strip()
        title = normalize_title((entry.findtext("atom:title", default="", namespaces=ns) or "").strip())
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
        watch_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("rel") == "alternate":
                watch_url = link.attrib.get("href", "").strip()
                break

        if not video_id or not title or not published:
            continue

        date = dt.datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(
            dt.timezone(dt.timedelta(hours=9))
        )
        date_label = f"{date.year}年{date.month}月{date.day}日"

        entries.append(
            {
                "video_id": video_id,
                "title": title,
                "date_label": date_label,
                "watch_url": watch_url or f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    return entries


def build_cards(entries: list[dict[str, str]], indent: str) -> str:
    cards: list[str] = []
    for idx, e in enumerate(entries, start=1):
        cards.append(
            "\n".join(
                [
                    f"{indent}<article class=\"youtube-card reveal\">",
                    f"{indent}    <div class=\"youtube-embed\">",
                    f"{indent}        <iframe",
                    f"{indent}            src=\"https://www.youtube-nocookie.com/embed/{html.escape(e['video_id'])}\"",
                    f"{indent}            title=\"公式YouTube 最新動画{idx}\"",
                    f"{indent}            loading=\"lazy\"",
                    f"{indent}            allow=\"accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share\"",
                    f"{indent}            allowfullscreen></iframe>",
                    f"{indent}    </div>",
                    f"{indent}    <div class=\"youtube-body\">",
                    f"{indent}        <h3>{html.escape(e['title'])}</h3>",
                    f"{indent}        <p class=\"youtube-meta\">公開日: {e['date_label']}</p>",
                    f"{indent}        <a class=\"youtube-watch\" href=\"{html.escape(e['watch_url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">YouTubeで見る</a>",
                    f"{indent}    </div>",
                    f"{indent}</article>",
                ]
            )
        )
    return "\n".join(cards)


def update_index(index_path: Path, entries: list[dict[str, str]]) -> bool:
    original = index_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^(?P<indent>[ \t]*){re.escape(START_MARKER)}\n(?P<body>.*?)(?P=indent){re.escape(END_MARKER)}",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(original)
    if not match:
        raise RuntimeError(f"Markers not found in {index_path}")

    indent = match.group("indent")
    cards = build_cards(entries, indent + "    ")
    replacement = f"{indent}{START_MARKER}\n{cards}\n{indent}{END_MARKER}"
    updated = original[: match.start()] + replacement + original[match.end() :]

    if updated == original:
        return False

    index_path.write_text(updated, encoding="utf-8")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update YouTube cards in index.html")
    parser.add_argument("--index", default="index.html", help="Path to index.html")
    parser.add_argument("--limit", type=int, default=3, help="Number of latest videos")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    index_path = Path(args.index)
    entries = fetch_entries(args.limit)
    if len(entries) < args.limit:
        raise RuntimeError(f"Expected {args.limit} videos, got {len(entries)}")
    changed = update_index(index_path, entries)
    print("updated" if changed else "no changes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
