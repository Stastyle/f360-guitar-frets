#!/usr/bin/env python3
"""Generate Fusion 360 toolbar icons with the standard library only.

Fusion wants, per command, a resources folder holding 16x16.png and
32x32.png (plus optional -disabled variants). Add-ins run on Fusion's own
Python without pip packages, and in a cloud session PIL may be missing too,
so this writes PNGs with struct + zlib and draws the glyph from a 16x16
ASCII-art pattern ('#' = ink, '.' or ' ' = transparent).

Usage:
    python make_icons.py OUT_DIR                       # default glyph
    python make_icons.py OUT_DIR --glyph glyph.txt     # your own 16 lines of 16 chars
    python make_icons.py OUT_DIR --color 0,110,200     # ink colour (RGB)

OUT_DIR is the command's resources folder (e.g. MyAddin/resources/my_cmd).
Importable too: make_icon_set(out_dir, glyph=None, color=(90, 90, 90)).
"""

import argparse
import os
import struct
import zlib

DEFAULT_GLYPH = """\
................
.##############.
.#............#.
.#..##....##..#.
.#..##....##..#.
.#............#.
.#............#.
.#....####....#.
.#....####....#.
.#............#.
.#............#.
.#..##....##..#.
.#..##....##..#.
.#............#.
.##############.
................
"""


def write_png(path, size, pixels):
    """pixels: size rows of size (r, g, b, a) tuples."""
    raw = b''.join(
        b'\x00' + b''.join(struct.pack('4B', *pixels[y][x]) for x in range(size))
        for y in range(size))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    with open(path, 'wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', header)
                     + chunk(b'IDAT', zlib.compress(raw))
                     + chunk(b'IEND', b''))


def parse_glyph(text):
    rows = [line.rstrip('\n') for line in text.splitlines() if line.strip('\n') != '']
    rows = rows[:16] + ['.' * 16] * max(0, 16 - len(rows))
    return [(row + '.' * 16)[:16] for row in rows]


def render(glyph_rows, size, color, alpha=1.0):
    ink = (color[0], color[1], color[2], int(255 * alpha))
    clear = (0, 0, 0, 0)
    scale = size // 16
    pixels = [[clear] * size for _ in range(size)]
    for gy, row in enumerate(glyph_rows):
        for gx, cell in enumerate(row):
            if cell == '#':
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[gy * scale + dy][gx * scale + dx] = ink
    return pixels


def make_icon_set(out_dir, glyph=None, color=(90, 90, 90)):
    rows = parse_glyph(glyph or DEFAULT_GLYPH)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for size in (16, 32):
        for suffix, alpha in (('', 1.0), ('-disabled', 0.4)):
            path = os.path.join(out_dir, '{0}x{0}{1}.png'.format(size, suffix))
            write_png(path, size, render(rows, size, color, alpha))
            written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('out_dir', help='resources folder of the command')
    parser.add_argument('--glyph', help='text file with 16 lines of 16 chars (# = ink)')
    parser.add_argument('--color', default='90,90,90', help='ink colour as R,G,B')
    args = parser.parse_args()
    glyph = None
    if args.glyph:
        with open(args.glyph) as handle:
            glyph = handle.read()
    color = tuple(int(part) for part in args.color.split(','))
    for path in make_icon_set(args.out_dir, glyph, color):
        print('wrote', path)


if __name__ == '__main__':
    main()
