#!/usr/bin/env python3
"""
Build the Dispo Deal Console into one self-contained HTML file.

    python build.py

Reads  index.src.html  and replaces every  __ASSET:name__  placeholder with a
base64 data: URI for  assets/name.  Writes  dist/index.html.

Self-contained matters: the page is served as a static file by Caddy on the
n8n box with no CDN access, and the whole point of owning the source is that a
deploy is one file copy.
"""

import base64
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "index.src.html")
ASSETS = os.path.join(HERE, "assets")
OUT_DIR = os.path.join(HERE, "dist")
OUT = os.path.join(OUT_DIR, "index.html")

MIME = {".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml"}


def data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return "data:%s;base64,%s" % (mime, b64)


def main():
    with open(SRC, encoding="utf-8") as fh:
        html = fh.read()

    missing = []
    used = []

    def sub(match):
        name = match.group(1)
        path = os.path.join(ASSETS, name)
        if not os.path.exists(path):
            missing.append(name)
            return match.group(0)
        used.append((name, os.path.getsize(path)))
        return data_uri(path)

    html = re.sub(r"__ASSET:([A-Za-z0-9._-]+)__", sub, html)

    if missing:
        sys.stderr.write("missing assets: %s\n" % ", ".join(sorted(set(missing))))
        return 1

    # A leftover placeholder means a typo in the source; fail rather than ship
    # a page with a broken font or logo.
    leftover = re.findall(r"__ASSET:[^_]*__", html)
    if leftover:
        sys.stderr.write("unresolved placeholders: %s\n" % leftover)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)

    for name, size in used:
        print("  inlined %-18s %8d bytes" % (name, size))
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
