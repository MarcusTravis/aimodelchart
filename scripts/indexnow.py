#!/usr/bin/env python3
"""Tell IndexNow (Bing, Yandex, Seznam, Naver...) that the site's pages changed.

The key is public by design: it's served at /<key>.txt to prove ownership.
"""
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HOST = "aimodelchart.pages.dev"
KEY = "1046dfa1b1cd0c0ed83dba13861d6c94"
URLS = [f"https://{HOST}/", f"https://{HOST}/llms.txt", f"https://{HOST}/sitemap.xml"]


def main():
    assert (ROOT / f"{KEY}.txt").read_text().strip() == KEY, "key file missing or wrong"
    body = {"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": URLS}
    r = requests.post("https://api.indexnow.org/indexnow", data=json.dumps(body),
                      headers={"Content-Type": "application/json; charset=utf-8"}, timeout=30)
    print(f"[indexnow] HTTP {r.status_code} {r.text[:200]}".strip())
    return 0 if r.status_code in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
