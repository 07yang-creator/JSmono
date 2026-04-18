#!/usr/bin/env python3
"""
Build-time font download script.
Fetches Noto Sans JP Regular + Bold into the fonts/ directory.
Runs during `vercel build` so the files are bundled into the serverless function.
"""
import os, sys, urllib.request, pathlib

FONTS_DIR = pathlib.Path(__file__).parent.parent / "fonts"
FONTS_DIR.mkdir(exist_ok=True)

TARGETS = [
    (
        "NotoSansJP-Regular.ttf",
        [
            "https://github.com/google/fonts/raw/main/ofl/notosansjp/static/NotoSansJP-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/static/NotoSansJP-Regular.ttf",
        ],
    ),
    (
        "NotoSansJP-Bold.ttf",
        [
            "https://github.com/google/fonts/raw/main/ofl/notosansjp/static/NotoSansJP-Bold.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/static/NotoSansJP-Bold.ttf",
        ],
    ),
]

for filename, urls in TARGETS:
    dest = FONTS_DIR / filename
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"[fonts] {filename} already present — skip")
        continue
    downloaded = False
    for url in urls:
        try:
            print(f"[fonts] Downloading {filename} from {url} …")
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) < 100_000:
                print(f"[fonts]   Too small ({len(data)} bytes) — skipping")
                continue
            dest.write_bytes(data)
            print(f"[fonts]   Saved {len(data):,} bytes → {dest}")
            downloaded = True
            break
        except Exception as e:
            print(f"[fonts]   Failed: {e}")
    if not downloaded:
        print(f"[fonts] WARNING: Could not download {filename} — will fall back to DroidSansFallback")

print("[fonts] Done.")
