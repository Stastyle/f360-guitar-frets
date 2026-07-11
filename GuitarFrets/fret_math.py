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


def string_nut_geometry(fret_zero_segment, bridge_segment, string_count,
                        spread_nut, spread_bridge):
    """Per string: (nut_point, headward_unit, bridge_point) in the local frame.

    String 0 is the +y (bass side) outer string. Strings are spaced with equal
    center-to-center distances; spreads are outer-string center to center.
    headward_unit points from the bridge toward (and past) the nut.
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
        strings.append((nut_pt, (ux, uy), bridge_pt))
    return strings


def string_layout(fret_zero_segment, bridge_segment, string_count,
                  spread_nut, spread_bridge, head_length):
    """Per string, its (head_end, bridge_end) points in the local frame.

    String 0 is the +y (bass side) outer string. Strings are spaced with equal
    center-to-center distances; spreads are outer-string center to center.
    The head end continues the string direction past the nut by head_length
    (a single value, or one value per string), for aligning tuners.
    """
    geometry = string_nut_geometry(fret_zero_segment, bridge_segment,
                                   string_count, spread_nut, spread_bridge)
    try:
        lengths = list(head_length)
    except TypeError:
        lengths = [head_length] * string_count
    if len(lengths) != string_count:
        raise ValueError('Need one head length per string')

    strings = []
    for (nut_pt, (ux, uy), bridge_pt), length in zip(geometry, lengths):
        head_pt = (nut_pt[0] + ux * length, nut_pt[1] + uy * length)
        strings.append((head_pt, bridge_pt))
    return strings


# --- tuner layout ------------------------------------------------------------
#
# Terminology (see HARDWARE_RESEARCH.md, final v1 spec):
#   station — along-neck (plan-view) distance of a post behind its string's
#             own nut point; always positive, headstock-ward.
#   side    — which headstock row holds the post's button: +1 bass (+y row),
#             -1 treble. For straight-pull the post sits ON the string line;
#             side only matters for guide/readout purposes and split bookkeeping.
#   The nut datum is each string's own nut-line intersection (fret 0 for
#   single-scale), NOT the nut slot edge — toggling the nut slot never moves
#   tuner holes.


def tuner_assign_stations(string_count, bass_count, reversed_=False):
    """Per-string (station_index, side) for straight-pull layouts.

    Station indices 0..N-1 are GLOBAL and distinct — naive symmetric per-side
    sequences physically overlap the inner posts, because string plan lines
    converge past the nut. Assignment alternates sides outer-to-inner starting
    with the bass row (E, e, A, B, D, G for 3+3), so per side the outer string
    gets the nearest post. Inline (bass_count 0 or N) is the monotonic
    outer-to-outer special case. reversed_ mirrors the whole headstock:
    sides flip and the nearest post moves to the opposite outer string.
    """
    if not 0 <= bass_count <= string_count:
        raise ValueError('Bass-side count must be between 0 and the string count')
    if reversed_:
        # A reversed headstock is the mirror image: string i takes the role of
        # string N-1-i and every side flips (this also mirrors an asymmetric
        # split — reversed 4+2 is 2+4). Same bass_count here: the swap falls
        # out of the index mirror + side negation.
        mirrored = tuner_assign_stations(string_count, bass_count)
        return [(k, -side) for k, side in reversed(mirrored)]

    bass = list(range(bass_count))                        # outer-to-inner
    treble = list(range(string_count - 1, bass_count - 1, -1))
    order = []
    for pair in zip(bass, treble):
        order.extend(pair)
    longer = bass[len(treble):] if len(bass) > len(treble) else treble[len(bass):]
    order.extend(longer)

    assignment = [None] * string_count
    for station_index, string_index in enumerate(order):
        side = 1 if string_index < bass_count else -1
        assignment[string_index] = (station_index, side)
    return assignment


def tuner_straight_pull_posts(nut_geometry, bass_count, first, spacing,
                              reversed_=False, station_overrides=None):
    """Straight-pull post plan positions: one per string, ON its extended line.

    nut_geometry comes from string_nut_geometry. Station k (from
    tuner_assign_stations) sits first + k*spacing along the neck behind the
    string's own nut point; station_overrides (per-string distances, None
    entries keep the sequence value) feeds the manual table. Returns a list of
    (post_point, station, side) per string; post_point is in the local frame.
    Raises ValueError when a string runs (nearly) across the neck.
    """
    count = len(nut_geometry)
    assignment = tuner_assign_stations(count, bass_count, reversed_)
    posts = []
    for i, (nut_pt, (ux, uy), _bridge) in enumerate(nut_geometry):
        station_index, side = assignment[i]
        station = first + station_index * spacing
        if station_overrides is not None and station_overrides[i] is not None:
            station = station_overrides[i]
        if station <= 0:
            raise ValueError('Tuner stations must be positive')
        if ux >= -1e-9:
            raise ValueError('String direction does not head past the nut')
        t = station / -ux           # along-neck depth -> distance along string
        post = (nut_pt[0] + ux * t, nut_pt[1] + uy * t)
        posts.append((post, station, side))
    return posts


def tuner_pattern_posts(string_count, bass_count, first, pitch, row_offset,
                        reversed_=False, row_slant=0.0):
    """Pattern (grid-first) posts: fixed rows relative to the center line.

    The bass row starts at +row_offset, the treble row at -row_offset; per
    side, posts sit at first + k*pitch behind the datum, outer string nearest
    (the classic Gibson 3+3 when pitch = 35 mm and row_slant = 0). row_slant
    steps each row toward the center line per station — 0.281" per 0.919"
    axial step reproduces Fender's 17-degree inline row. Inline splits put
    the single row on the occupied side. Grid x values are datum-relative
    plan stations for a flat headstock, or FACE-true distances when drawn on
    an angled face — the caller decides (grids are dimensioned on the face,
    per the spec). reversed_ mirrors the grid and the string assignment about
    the center line (a geometric no-op for symmetric splits, but the
    assignment flips). Returns a list of (post_point, station, side) per
    string, where post_point = (-station, row_y).
    """
    if reversed_:
        # Mirror image, same as tuner_assign_stations: index mirror + side
        # negation (same bass_count — the split swap falls out of it).
        mirrored = tuner_pattern_posts(string_count, bass_count,
                                       first, pitch, row_offset,
                                       row_slant=row_slant)
        return [((post[0], -post[1]), station, -side)
                for post, station, side in reversed(mirrored)]

    if not 0 <= bass_count <= string_count:
        raise ValueError('Bass-side count must be between 0 and the string count')
    if first <= 0 or pitch <= 0:
        raise ValueError('Pattern first distance and pitch must be positive')

    posts = []
    for i in range(string_count):
        if i < bass_count:
            rank, side = i, 1                             # bass row, outer first
        else:
            rank, side = string_count - 1 - i, -1         # treble row, outer first
        station = first + rank * pitch
        row_y = (row_offset - rank * row_slant) * side
        posts.append(((-station, row_y), station, side))
    return posts


def plan_to_face_distance(plan_behind_datum, break_offset, angle):
    """Along-face distance from the hinge line for a plan station.

    The headstock face tilts by `angle` (radians) about a hinge line
    break_offset behind the datum: plan = break_offset + face*cos(angle).
    Distances before the hinge are still on the flat part — raise, the post
    belongs on the face.
    """
    if plan_behind_datum < break_offset - 1e-9:
        raise ValueError('Post lands before the headstock break line')
    return (plan_behind_datum - break_offset) / math.cos(angle)


def face_to_plan_distance(face_from_hinge, break_offset, angle):
    """Inverse of plan_to_face_distance (face distances measured from the
    hinge line along the tilted face)."""
    if face_from_hinge < 0:
        raise ValueError('Face distances are measured headstock-ward from the hinge')
    return break_offset + face_from_hinge * math.cos(angle)


def side_pull_angles(nut_geometry, posts):
    """Per string, the PLAN-view angle (degrees) between the string direction
    and the nut->post line — how far the nut slot must flare toward its post.
    0 for straight-pull posts. The true 3D pull (side + break angle) is
    larger; treat these as the plan component only.
    """
    angles = []
    for (nut_pt, (ux, uy), _bridge), (post, _station, _side) in zip(nut_geometry, posts):
        vx, vy = post[0] - nut_pt[0], post[1] - nut_pt[1]
        length = math.hypot(vx, vy)
        if length < 1e-12:
            raise ValueError('Post coincides with the nut point')
        cross = ux * vy - uy * vx
        dot = ux * vx + uy * vy
        angles.append(math.degrees(math.atan2(abs(cross), dot)))
    return angles


def post_clearance_violations(points, min_distance):
    """Pairs of posts closer (center-to-center) than min_distance.

    Pass FACE coordinates for angled headstocks — plan distances understate
    true spacing. Returns [(i, j, distance), ...], nearest pair first.
    """
    violations = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            d = math.hypot(points[j][0] - points[i][0],
                           points[j][1] - points[i][1])
            if d < min_distance:
                violations.append((i, j, d))
    return sorted(violations, key=lambda v: v[2])


def tuner_reference(layout, string_count, spread_nut, spread_bridge,
                    mode, bass_count, reversed_, hole_diameter,
                    clearance_margin, angle, break_offset,
                    first=None, spacing=None,
                    pattern_first=None, pattern_pitch=None,
                    pattern_row_offset=None, pattern_row_slant=0.0,
                    head_margin=0.8):
    """Complete tuner-post reference geometry for one layout.

    layout comes from slot_layout. mode is 'straight' or 'pattern'; angle is
    the headstock tilt in radians (0 = flat). Straight-pull distances (first,
    spacing) are PLAN values along the neck behind each string's own nut
    point; pattern distances (pattern_first, pattern_pitch) are measured from
    the datum along the WOOD SURFACE — flat until the break line, then along
    the tilted face — so a printed template matches them 1:1.

    Returns a dict:
      'plan_posts'  — per-string (x, y) in the plan local frame (x negative)
      'draw_posts'  — where circles go: plan coordinates at angle 0, else
                      FACE coordinates (f, y), f headstock-ward from the hinge
      'stations'    — per-string spec distance (see above per mode)
      'sides'       — +1 bass row / -1 treble row
      'head_lengths'— per-string string-line extension reaching its post
      'side_angles' — plan-view nut->post side-pull angle per string, degrees
      'violations'  — post pairs closer than hole diameter + clearance margin
      'nut_points'  — per-string nut point in the plan local frame
      'tilted'      — whether an angled headstock plane is in play
    Raises ValueError on degenerate geometry.
    """
    geometry = string_nut_geometry(layout['fret_zero'], layout['bridge'],
                                   string_count, spread_nut, spread_bridge)
    tilted = angle > 1e-9
    if not tilted:
        break_offset = 0.0

    if mode == 'straight':
        posts = tuner_straight_pull_posts(geometry, bass_count, first,
                                          spacing, reversed_)
        plan_posts = [post for post, _station, _side in posts]
        stations = [station for _post, station, _side in posts]
        sides = [side for _post, _station, side in posts]
        if tilted:
            draw_posts = [(plan_to_face_distance(station, break_offset, angle),
                           post[1])
                          for post, station, _side in posts]
        else:
            draw_posts = list(plan_posts)
    else:
        posts = tuner_pattern_posts(string_count, bass_count, pattern_first,
                                    pattern_pitch, pattern_row_offset,
                                    reversed_, pattern_row_slant)
        stations = [station for _post, station, _side in posts]
        sides = [side for _post, _station, side in posts]
        if tilted:
            draw_posts = []
            plan_posts = []
            for post, station, _side in posts:
                face = station - break_offset
                if face <= 0:
                    raise ValueError('Post lands before the headstock break line')
                draw_posts.append((face, post[1]))
                plan_posts.append(
                    (-face_to_plan_distance(face, break_offset, angle),
                     post[1]))
        else:
            plan_posts = [post for post, _station, _side in posts]
            draw_posts = list(plan_posts)

    plan_tuples = list(zip(plan_posts, stations, sides))
    return {
        'plan_posts': plan_posts,
        'draw_posts': draw_posts,
        'stations': stations,
        'sides': sides,
        'head_lengths': head_lengths_to_posts(geometry, plan_tuples,
                                              margin=head_margin),
        'side_angles': side_pull_angles(geometry, plan_tuples),
        'violations': post_clearance_violations(
            draw_posts, hole_diameter + (clearance_margin or 0.0)),
        'nut_points': [nut_pt for nut_pt, _direction, _bridge in geometry],
        'tilted': tilted,
    }


def head_lengths_to_posts(nut_geometry, posts, margin=0.0):
    """Per-string head-extension length so each string line reaches its post's
    along-neck station (plus margin). For straight-pull the extension ends on
    the post itself; for pattern grids it ends level with the post.
    """
    lengths = []
    for (nut_pt, (ux, uy), _bridge), (post, _station, _side) in zip(nut_geometry, posts):
        if ux >= -1e-9:
            raise ValueError('String direction does not head past the nut')
        depth = nut_pt[0] - post[0]   # along-neck drop from nut to post
        if depth <= 0:
            raise ValueError('Post is not behind the nut')
        lengths.append(depth / -ux + margin)
    return lengths


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
