#!/usr/bin/env python3
"""Generate apple-touch-icon.png and og-image.png (dependency-free)."""
import struct, sys, zlib
from pathlib import Path

def png(path, w, h, px):
    raw = b"".join(b"\x00" + bytes(c for x in range(w) for c in px(x, y)) for y in range(h))
    def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))

def bars(w, h, bg, fg, rects):
    def px(x, y):
        for (a, b, c, d) in rects:
            if a <= x < c and b <= y < d: return fg
        return bg
    return px

root = Path(__file__).resolve().parent.parent
s = 180
png(root / "apple-touch-icon.png", s, s, bars(s, s, (0, 102, 204), (255, 255, 255),
    [(34, 96, 62, 144), (76, 62, 104, 144), (118, 34, 146, 144)]))
W, H = 1200, 630
png(root / "og-image.png", W, H, bars(W, H, (245, 245, 247), (0, 102, 204),
    [(300, 330, 420, 480), (480, 250, 600, 480), (660, 170, 780, 480), (840, 100, 960, 480)]))
