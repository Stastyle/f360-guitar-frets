# Pure-python fret/neck layout math. No adsk imports so it can be unit-tested
# with plain pytest outside Fusion 360.
#
# All lengths are in whatever unit the caller uses consistently (the add-in
# passes Fusion internal units, cm).
#
# Local layout frame: x runs along the neck from the nut (fret 0 center) toward
# the bridge, y runs across the neck. +y is the LEFT side of the neck when
# looking from the nut toward the bridge (the add-in calls that the bass side).
# Points are 2D tuples; use place() to map them into sketch coordinates.

import math


def fret_distance(scale, n):
    """Distance from the nut (fret 0) to fret n, 12-tone equal temperament."""
    return scale * (1.0 - 2.0 ** (-n / 12.0))


def fret_distances(scale, count):
    return [fret_distance(scale, n) for n in range(1, count + 1)]


def normalize(x, y):
    length = math.hypot(x, y)
    if length < 1e-12:
        raise ValueError('Cannot normalize a zero-length direction')
    return x / length, y / length


def place(point, x0, y0, dx, dy):
    """Map a local (along, across) point into sketch coordinates.

    (x0, y0) is fret 0 in sketch space and (dx, dy) the unit neck direction;
    the across axis is the left-hand perpendicular (-dy, dx).
    """
    lx, ly = point
    return (x0 + dx * lx - dy * ly, y0 + dy * lx + dx * ly)


def line_intersection(p, u, q, v):
    """Intersection of the 2D lines p + t*u and q + s*v.

    Raises ValueError when the lines are (nearly) parallel.
    """
    denominator = u[0] * v[1] - u[1] * v[0]
    if abs(denominator) < 1e-12:
        raise ValueError('Lines are parallel')
    t = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / denominator
    return (p[0] + t * u[0], p[1] + t * u[1])


def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def closest_point_parameter(point1, direction1, point2, direction2):
    """Parameter t so that point1 + t*direction1 is the point on line 1
    closest to line 2. Points/directions are 3-tuples; directions need not be
    unit length. Raises ValueError when the lines are (nearly) parallel.

    Used to drop fret 0 onto the center line when the user marks the nut
    position with a sketch line instead of a face.
    """
    a = _dot3(direction1, direction1)
    b = _dot3(direction1, direction2)
    c = _dot3(direction2, direction2)
    if a < 1e-24 or c < 1e-24:
        raise ValueError('Degenerate line direction')
    w0 = (point1[0] - point2[0], point1[1] - point2[1], point1[2] - point2[2])
    d = _dot3(direction1, w0)
    e = _dot3(direction2, w0)
    denominator = a * c - b * b
    if denominator <= 1e-9 * a * c:
        raise ValueError('Lines are parallel')
    return (b * e - c * d) / denominator


def fanned_positions(bass_scale, treble_scale, fret_count, perpendicular_fret):
    """x position along the neck of each fret end, bass and treble side.

    Returns (frets, bridge): frets[n] = (x_bass, x_treble) for n = 0..count
    (n = 0 is the nut); bridge is the (x_bass, x_treble) of the saddle line.
    Anchored so the REARMOST end of the (possibly fanned) nut line sits at
    x = 0: nothing of the layout reaches behind the fret-zero reference, so a
    fanned nut lands fully on the board and can actually be manufactured.
    The chosen perpendicular fret comes out straight. With
    bass_scale == treble_scale this reduces to the standard layout.
    """
    center_scale = (bass_scale + treble_scale) / 2.0
    anchor = fret_distance(center_scale, perpendicular_fret)
    bass_perp = fret_distance(bass_scale, perpendicular_fret)
    treble_perp = fret_distance(treble_scale, perpendicular_fret)

    def pair(bass_d, treble_d):
        return (anchor + bass_d - bass_perp, anchor + treble_d - treble_perp)

    frets = [pair(fret_distance(bass_scale, n), fret_distance(treble_scale, n))
             for n in range(0, fret_count + 1)]
    bridge = pair(bass_scale, treble_scale)

    shift = -min(frets[0])
    if shift:
        frets = [(b + shift, t + shift) for b, t in frets]
        bridge = (bridge[0] + shift, bridge[1] + shift)
    return frets, bridge


def _pair_segment(pair, half_span):
    """Segment across the neck for an (x_bass, x_treble) pair: bass end on +y."""
    return ((pair[0], half_span), (pair[1], -half_span))


def segment_rectangle(p1, p2, width, shift_backward=False):
    """Three corners (for addThreePointRectangle) of a rectangle of the given
    width centered on the segment p1 -> p2.

    With shift_backward the rectangle is shifted half a width along its own
    normal toward -x, so its front edge lies exactly on the segment — used for
    the nut slot, which sits behind fret 0.
    """
    ux, uy = normalize(p2[0] - p1[0], p2[1] - p1[1])
    nx, ny = -uy, ux
    half = width / 2.0

    ox = oy = 0.0
    if shift_backward:
        bx, by = (nx, ny) if nx < 0 else (-nx, -ny)
        ox, oy = bx * half, by * half

    corner1 = (p1[0] - nx * half + ox, p1[1] - ny * half + oy)
    corner2 = (p1[0] + nx * half + ox, p1[1] + ny * half + oy)
    corner3 = (p2[0] + nx * half + ox, p2[1] + ny * half + oy)
    return corner1, corner2, corner3


def slot_layout(bass_scale, treble_scale, fret_count, perpendicular_fret,
                half_span, slot_width, nut_slot_width=None):
    """Local-frame geometry of the whole slot layout.

    Returns a dict:
      'slots'     — list of corner triples, one rectangle per fret 1..count
      'nut'       — corner triple of the nut slot (None when not requested);
                    sits behind the fret-0 line
      'fret_zero' — the fret-0 segment across the neck
      'last'      — the last fret's segment
      'bridge'    — the saddle line segment (theoretical scale length)
    """
    frets, bridge = fanned_positions(bass_scale, treble_scale, fret_count,
                                     perpendicular_fret)
    slots = []
    for n in range(1, fret_count + 1):
        p1, p2 = _pair_segment(frets[n], half_span)
        slots.append(segment_rectangle(p1, p2, slot_width))

    nut = None
    if nut_slot_width and nut_slot_width > 0:
        p1, p2 = _pair_segment(frets[0], half_span)
        nut = segment_rectangle(p1, p2, nut_slot_width, shift_backward=True)

    return {
        'slots': slots,
        'nut': nut,
        'fret_zero': _pair_segment(frets[0], half_span),
        'last': _pair_segment(frets[fret_count], half_span),
        'bridge': _pair_segment(bridge, half_span),
    }


def nut_slot_span(bass_scale, treble_scale, perpendicular_fret,
                  nut_slot_width, nut_offset=0.0):
    """(rearmost x, foremost x) reach of the nut slot, measured from the
    selected fret-zero reference (nut_offset shifts the whole layout).

    Accounts for the fan skew of the nut line in multi-scale layouts, so the
    user can check that the physical board actually covers the whole seat.
    """
    frets, _ = fanned_positions(bass_scale, treble_scale, 0, perpendicular_fret)
    x_bass, x_treble = frets[0]
    front = max(x_bass, x_treble) + nut_offset
    rear = min(x_bass, x_treble) + nut_offset - nut_slot_width
    return rear, front


def _x_on_segment_line(segment, y):
    """x of the infinite line through the segment's endpoints at lateral y."""
    (x1, y1), (x2, y2) = segment
    if abs(y1 - y2) < 1e-12:
        raise ValueError('Segment does not cross the neck')
    t = (y - y2) / (y1 - y2)
    return x2 + (x1 - x2) * t


def string_layout(fret_zero_segment, bridge_segment, string_count,
                  spread_nut, spread_bridge, head_length):
    """Per string, its (head_end, bridge_end) points in the local frame.

    String 0 is the +y (bass side) outer string. Strings are spaced with equal
    center-to-center distances; spreads are outer-string center to center.
    The head end continues the string direction past the nut by head_length,
    for aligning tuners.
    """
    strings = []
    for i in range(string_count):
        if string_count > 1:
            fraction = 0.5 - i / (string_count - 1.0)
        else:
            fraction = 0.0
        y_nut = spread_nut * fraction
        y_bridge = spread_bridge * fraction

        nut_pt = (_x_on_segment_line(fret_zero_segment, y_nut), y_nut)
        bridge_pt = (_x_on_segment_line(bridge_segment, y_bridge), y_bridge)

        ux, uy = normalize(nut_pt[0] - bridge_pt[0], nut_pt[1] - bridge_pt[1])
        head_pt = (nut_pt[0] + ux * head_length, nut_pt[1] + uy * head_length)
        strings.append((head_pt, bridge_pt))
    return strings


def taper_outline(fret_zero_segment, bridge_segment, last_fret_segment,
                  spread_nut, spread_bridge, nut_width, overhang):
    """Four corners of the tapered fretboard outline (a closed polygon).

    The side edges follow the outer strings, offset outward by a constant
    margin of (nut_width - spread_nut) / 2. The board runs from the fret-0
    line to the last fret plus overhang. Corner order:
    [front-bass, end-bass, end-treble, front-treble].
    Raises ValueError when the nut width does not exceed the nut spread.
    """
    margin = (nut_width - spread_nut) / 2.0
    if margin <= 0:
        raise ValueError('Nut width must be larger than the string spread at the nut')

    edges = []
    for side in (1.0, -1.0):
        y_nut = spread_nut / 2.0 * side
        y_bridge = spread_bridge / 2.0 * side
        p_nut = (_x_on_segment_line(fret_zero_segment, y_nut), y_nut)
        p_bridge = (_x_on_segment_line(bridge_segment, y_bridge), y_bridge)
        ux, uy = normalize(p_bridge[0] - p_nut[0], p_bridge[1] - p_nut[1])
        nx, ny = -uy, ux
        if ny * side < 0:
            nx, ny = -nx, -ny
        edges.append(((p_nut[0] + nx * margin, p_nut[1] + ny * margin), (ux, uy)))

    def line_of(segment):
        (x1, y1), (x2, y2) = segment
        return (x1, y1), normalize(x2 - x1, y2 - y1)

    front_point, front_direction = line_of(fret_zero_segment)
    last_point, last_direction = line_of(last_fret_segment)
    nx, ny = -last_direction[1], last_direction[0]
    if nx < 0:
        nx, ny = -nx, -ny
    end_point = (last_point[0] + nx * overhang, last_point[1] + ny * overhang)

    bass_edge, treble_edge = edges
    return [
        line_intersection(bass_edge[0], bass_edge[1], front_point, front_direction),
        line_intersection(bass_edge[0], bass_edge[1], end_point, last_direction),
        line_intersection(treble_edge[0], treble_edge[1], end_point, last_direction),
        line_intersection(treble_edge[0], treble_edge[1], front_point, front_direction),
    ]
