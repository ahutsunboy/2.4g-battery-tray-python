import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import struct
import sys
import zlib

import wsgui


def write_png(path, w, h, rgb_rows):
    raw = b"".join(bytes([0]) + bytes(v for px in row for v in px) for row in rgb_rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


def main():
    bg = (32, 33, 36)
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    combos = [(100, False), (75, False), (46, False), (15, False), (46, True)]
    canvas = [[bg for _ in range(size * len(combos))] for _ in range(size)]
    for k, (p, c) in enumerate(combos):
        b = wsgui.render_battery_icon(size, p, c)
        for y in range(size):
            for x in range(size):
                i = (y * size + x) * 4
                pb, pg, pr, pa = b[i], b[i + 1], b[i + 2], b[i + 3]
                a = pa / 255.0
                canvas[y][k * size + x] = (int(pr * a + bg[0] * (1 - a)),
                                            int(pg * a + bg[1] * (1 - a)),
                                            int(pb * a + bg[2] * (1 - a)))
    write_png("preview_icon.png", size * len(combos), size, canvas)
    print("wrote preview_icon.png")


if __name__ == "__main__":
    main()
