"""Generate toolbar icons for the GuitarFrets add-in.

Pure stdlib (struct + zlib) PNG writer - run with any Python 3:
    python scripts/make_icons.py
Draws a tiny fretboard glyph: a thick nut line plus fret lines with
real 2^(-n/12)-style decreasing spacing.
"""

import os
import struct
import zlib

RESOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'GuitarFrets', 'resources')

GRAY = (90, 90, 90, 255)
BLUE = (0, 110, 200, 255)
DARK = (50, 50, 50, 255)


def write_png(path, size, pixels):
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


def draw_icon(size, fret_color, nut_color, alpha=1.0):
    def fade(color):
        return color[0], color[1], color[2], int(color[3] * alpha)

    pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
    margin = max(2, size // 10)
    top, bottom = margin, size - margin
    line_width = max(1, size // 16)

    def vline(x, width, color):
        for column in range(int(x), min(int(x) + width, size)):
            for row in range(top, bottom):
                pixels[row][column] = color

    # Nut: a thicker line at the left edge of the glyph.
    vline(margin, line_width + 1, fade(nut_color))

    # Frets: decreasing spacing, same law as the real thing (compressed),
    # normalized so the six lines span the full glyph width.
    usable = size - 2 * margin - line_width
    full = 1.0 - 2.0 ** (-6 / 4.0)
    for n in range(1, 7):
        x = margin + usable * (1.0 - 2.0 ** (-n / 4.0)) / full
        vline(x, line_width, fade(fret_color))

    return pixels


def main():
    icon_sets = {
        'create_fret_slots': GRAY,
    }
    for folder, color in icon_sets.items():
        target = os.path.join(RESOURCES, folder)
        os.makedirs(target, exist_ok=True)
        for size in (16, 32):
            write_png(os.path.join(target, '{0}x{0}.png'.format(size)),
                      size, draw_icon(size, color, DARK))
            write_png(os.path.join(target, '{0}x{0}-disabled.png'.format(size)),
                      size, draw_icon(size, color, DARK, alpha=0.4))
        print('wrote 4 icons to', target)


if __name__ == '__main__':
    main()
