#!/usr/bin/env python3
"""
Scan the public web feed of a Telegram channel (default: RoseSignalsPremium)
and emit new posts as JSON so Claude can process them.

No login required: uses https://t.me/s/<channel> which is the public preview.
Incremental by design — reads a history file and only returns posts newer
than the last one processed.

Usage:
    python scan_rose.py                         # new posts since last scan (history file)
    python scan_rose.py --days 3                # ignore history, last 3 days
    python scan_rose.py --history path.json     # custom history file
    python scan_rose.py --download-images DIR   # also save post images to DIR
    python scan_rose.py --commit               # after a successful scan, write the
                                               # newest message id back to history

Output (stdout): JSON  { "channel", "scanned_at", "from_id", "count", "posts": [...] }
Each post: { "id", "num", "datetime", "text", "images": [url,...], "is_reply", "views" }
Exit code 0 always (0 new posts is not an error → "nothing to do").
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
DEFAULT_CHANNEL = "RoseSignalsPremium"
DEFAULT_HISTORY = os.path.join("rose-tracker", "scan-history.json")


def fetch(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


MSG_RE = re.compile(r'<div class="tgme_widget_message[ "].*?data-post="([^"]+)"(.*?)(?=<div class="tgme_widget_message[ "]|<div class="tgme_channel_history)', re.S)
TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:<div class="tgme_widget_message_footer|<time|<a class="tgme_widget_message_date)', re.S)
TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
IMG_RE = re.compile(r"background-image:url\('([^']+)'\)")
VIEWS_RE = re.compile(r'<span class="tgme_widget_message_views">([^<]+)</span>')


def strip_tags(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</?[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_page(page_html):
    posts = []
    for m in MSG_RE.finditer(page_html):
        post_id = m.group(1)                       # "Channel/12345"
        body = m.group(2)
        try:
            num = int(post_id.split("/")[1])
        except (IndexError, ValueError):
            continue
        tm = TIME_RE.search(body)
        txt = TEXT_RE.search(body)
        imgs = [u for u in IMG_RE.findall(body) if "/img/emoji/" not in u]
        imgs = ["https:" + u if u.startswith("//") else u for u in imgs]
        posts.append({
            "id": post_id,
            "num": num,
            "datetime": tm.group(1) if tm else None,
            "text": strip_tags(txt.group(1)) if txt else "",
            "images": imgs,
            "is_reply": 'tgme_widget_message_reply' in body,
            "views": (VIEWS_RE.search(body).group(1) if VIEWS_RE.search(body) else None),
        })
    posts.sort(key=lambda p: p["num"])
    return posts


def load_history(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def collect_since(channel, last_num, max_days, hard_cap=600):
    """Walk forward from last_num using ?after=, or backward from newest with ?before= when no history."""
    base = f"https://t.me/s/{channel}"
    seen = {}
    if last_num:
        cursor = last_num
        while len(seen) < hard_cap:
            page = fetch(f"{base}?after={cursor}")
            batch = parse_page(page)
            batch = [p for p in batch if p["num"] > last_num]
            if not batch:
                break
            for p in batch:
                seen[p["num"]] = p
            new_cursor = max(p["num"] for p in batch)
            if new_cursor == cursor:
                break
            cursor = new_cursor
    else:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_days)
        page = fetch(base)
        batch = parse_page(page)
        for p in batch:
            seen[p["num"]] = p
        while len(seen) < hard_cap and batch:
            oldest = min(p["num"] for p in batch)
            odt = _pdate(seen[oldest]["datetime"])
            if odt and odt < cutoff:
                break
            page = fetch(f"{base}?before={oldest}")
            batch = parse_page(page)
            for p in batch:
                seen[p["num"]] = p
        if cutoff:
            seen = {n: p for n, p in seen.items()
                    if (_pdate(p["datetime"]) or dt.datetime.now(dt.timezone.utc)) >= cutoff}
    return [seen[n] for n in sorted(seen)]


def _pdate(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def download_images(posts, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for p in posts:
        for i, url in enumerate(p["images"]):
            ext = ".jpg"
            fn = os.path.join(out_dir, f"{p['num']}_{i}{ext}")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r, open(fn, "wb") as f:
                    f.write(r.read())
                p.setdefault("image_files", []).append(fn)
            except Exception as e:
                p.setdefault("image_errors", []).append(f"{url}: {e}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--history", default=DEFAULT_HISTORY)
    ap.add_argument("--days", type=int, default=3,
                    help="when there is no history, how far back to scan (default 3)")
    ap.add_argument("--download-images", metavar="DIR")
    ap.add_argument("--commit", action="store_true",
                    help="write newest message id + timestamp back to the history file")
    args = ap.parse_args()

    hist = load_history(args.history)
    last_num = hist.get("last_message_num")

    posts = collect_since(args.channel, last_num, args.days)

    if args.download_images and posts:
        download_images(posts, args.download_images)

    out = {
        "channel": args.channel,
        "scanned_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "from_id": last_num,
        "count": len(posts),
        "posts": posts,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.commit and posts:
        newest = max(p["num"] for p in posts)
        hist.update({
            "channel": args.channel,
            "last_message_num": newest,
            "last_message_id": f"{args.channel}/{newest}",
            "last_scanned_at": out["scanned_at"],
            "last_scan_count": len(posts),
        })
        os.makedirs(os.path.dirname(args.history) or ".", exist_ok=True)
        with open(args.history, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
        sys.stderr.write(f"history committed: last_message_num={newest}\n")


if __name__ == "__main__":
    main()
