import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'GuitarFrets'))

import fret_math


SCALE = 64.77  # 25.5 in expressed in cm, the Fusion internal unit


def _center(corner1, corner3):
    return ((corner1[0] + corner3[0]) / 2, (corner1[1] + corner3[1]) / 2)


def _side(a, b):
    return (b[0] - a[0], b[1] - a[1])


# --- fret distances ---------------------------------------------------------

def test_fret_12_is_half_scale():
    assert math.isclose(fret_math.fret_distance(SCALE, 12), SCALE / 2, rel_tol=1e-12)


def test_fret_24_is_three_quarter_scale():
    assert math.isclose(fret_math.fret_distance(SCALE, 24), SCALE * 0.75, rel_tol=1e-12)


def test_fret_spacing_strictly_decreasing():
    distances = fret_math.fret_distances(SCALE, 24)
    spacings = [distances[0]] + [b - a for a, b in zip(distances, distances[1:])]
    assert all(a > b for a, b in zip(spacings, spacings[1:]))
    assert all(s > 0 for s in spacings)


def test_known_25_5_positions():
    # Classic 25.5" scale reference values (StewMac fret tables), in inches.
    inch = 2.54
    assert math.isclose(fret_math.fret_distance(25.5 * inch, 1) / inch, 1.431, abs_tol=5e-4)
    assert math.isclose(fret_math.fret_distance(25.5 * inch, 5) / inch, 6.397, abs_tol=5e-4)
    assert math.isclose(fret_math.fret_distance(25.5 * inch, 12) / inch, 12.750, abs_tol=5e-4)


# --- fanned positions -------------------------------------------------------

def test_equal_scales_reduce_to_standard():
    frets, bridge = fret_math.fanned_positions(SCALE, SCALE, 22, 7)
    for n, (x_bass, x_treble) in enumerate(frets):
        expected = fret_math.fret_distance(SCALE, n)
        assert math.isclose(x_bass, expected, abs_tol=1e-12)
        assert math.isclose(x_treble, expected, abs_tol=1e-12)
    assert math.isclose(bridge[0], SCALE, abs_tol=1e-12)
    assert math.isclose(bridge[1], SCALE, abs_tol=1e-12)


def test_fanned_nut_anchored_at_rear_end_and_perp_fret_straight():
    bass, treble, perp = 68.58, 64.77, 7  # 27" / 25.5"
    frets, bridge = fret_math.fanned_positions(bass, treble, 24, perp)
    # The rearmost end of the fanned nut sits exactly at x = 0 — nothing of
    # the layout reaches behind the fret-zero reference.
    assert math.isclose(min(frets[0]), 0.0, abs_tol=1e-12)
    assert max(frets[0]) > 0
    assert min(min(pair) for pair in frets) >= 0
    # The perpendicular fret is straight.
    assert math.isclose(frets[perp][0], frets[perp][1], abs_tol=1e-12)
    # Fret midpoints follow the mean scale (up to the constant anchor shift).
    center_scale = (bass + treble) / 2
    mid0 = (frets[0][0] + frets[0][1]) / 2
    for n, (x_bass, x_treble) in enumerate(frets):
        assert math.isclose((x_bass + x_treble) / 2 - mid0,
                            fret_math.fret_distance(center_scale, n), abs_tol=1e-9)
    # Bass side is longer: its bridge sits farther and its nut farther back.
    assert bridge[0] - frets[0][0] > bridge[1] - frets[0][1]


# --- slot rectangles --------------------------------------------------------

def test_segment_rectangle_size_and_center():
    p1, p2 = (10.0, 3.0), (10.0, -3.0)
    c1, c2, c3 = fret_math.segment_rectangle(p1, p2, 0.06)
    short = _side(c1, c2)
    long = _side(c2, c3)
    assert math.isclose(math.hypot(*short), 0.06, rel_tol=1e-12)
    assert math.isclose(math.hypot(*long), 6.0, rel_tol=1e-12)
    assert math.isclose(short[0] * long[0] + short[1] * long[1], 0.0, abs_tol=1e-12)
    assert math.isclose(_center(c1, c3)[0], 10.0, abs_tol=1e-12)
    assert math.isclose(_center(c1, c3)[1], 0.0, abs_tol=1e-12)


def test_nut_rectangle_extends_backward_only():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06,
                                   nut_slot_width=0.35)
    xs = [corner[0] for corner in layout['nut']]
    assert math.isclose(max(xs), 0.0, abs_tol=1e-12)
    assert math.isclose(min(xs), -0.35, abs_tol=1e-12)


def test_nut_slot_span_standard_and_fanned():
    rear, front = fret_math.nut_slot_span(SCALE, SCALE, 0, 0.35)
    assert math.isclose(front, 0.0, abs_tol=1e-12)
    assert math.isclose(rear, -0.35, abs_tol=1e-12)
    # Offset moves the whole span.
    rear, front = fret_math.nut_slot_span(SCALE, SCALE, 0, 0.35, nut_offset=0.4)
    assert math.isclose(front, 0.4, abs_tol=1e-12)
    assert math.isclose(rear, 0.05, abs_tol=1e-12)
    # Fanned: the nut LINE never reaches behind the reference (rear-end
    # anchoring), so only the slot width extends behind it; the front end
    # reaches forward by the fan skew.
    rear, front = fret_math.nut_slot_span(68.58, 64.77, 7, 0.35)
    assert math.isclose(rear, -0.35, abs_tol=1e-12)
    assert front > 0


def test_slot_layout_counts_and_positions():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    assert len(layout['slots']) == 22
    assert layout['nut'] is None
    c1, _, c3 = layout['slots'][0]
    assert math.isclose(_center(c1, c3)[0],
                        fret_math.fret_distance(SCALE, 1), rel_tol=1e-12)
    # Bridge segment sits at the scale length.
    assert math.isclose(layout['bridge'][0][0], SCALE, abs_tol=1e-12)


def test_fanned_slots_are_angled():
    layout = fret_math.slot_layout(68.58, 64.77, 22, 7, 3.0, 0.06)
    (bass_x, _), (treble_x, _) = layout['fret_zero']
    assert bass_x < treble_x  # longer bass scale pushes the bass nut back
    p_bass, p_treble = layout['slots'][21][0], layout['slots'][21][2]
    assert not math.isclose(p_bass[0], p_treble[0], abs_tol=1e-6)


# --- strings ----------------------------------------------------------------

def test_string_layout_straight_case():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    strings = fret_math.string_layout(layout['fret_zero'], layout['bridge'],
                                      6, 3.5, 5.25, 15.0)
    assert len(strings) == 6
    head0, bridge0 = strings[0]
    # Bass outer string: +y side, correct spreads at both ends.
    assert math.isclose(bridge0[1], 5.25 / 2, abs_tol=1e-12)
    assert math.isclose(bridge0[0], SCALE, abs_tol=1e-9)
    # Head end is 15 beyond the nut along the string direction.
    y_nut = 3.5 / 2
    nut_pt = (0.0, y_nut)
    head_dist = math.hypot(head0[0] - nut_pt[0], head0[1] - nut_pt[1])
    assert math.isclose(head_dist, 15.0, abs_tol=1e-9)
    assert head0[0] < 0  # extends toward the headstock
    # Symmetry: last string mirrors the first.
    head5, bridge5 = strings[5]
    assert math.isclose(bridge5[1], -bridge0[1], abs_tol=1e-12)
    assert math.isclose(head5[1], -head0[1], abs_tol=1e-9)


def test_string_layout_single_string_on_center():
    layout = fret_math.slot_layout(SCALE, SCALE, 12, 0, 3.0, 0.06)
    (head, bridge), = fret_math.string_layout(layout['fret_zero'],
                                              layout['bridge'], 1, 3.5, 5.25, 10.0)
    assert math.isclose(head[1], 0.0, abs_tol=1e-12)
    assert math.isclose(bridge[1], 0.0, abs_tol=1e-12)


# --- tuners -----------------------------------------------------------------

def _nut_geometry(spread_nut=3.5, spread_bridge=5.25, count=6):
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    return fret_math.string_nut_geometry(layout['fret_zero'], layout['bridge'],
                                         count, spread_nut, spread_bridge)


def test_assign_inline_monotonic_and_reversed():
    normal = fret_math.tuner_assign_stations(6, 6)
    assert [k for k, _ in normal] == [0, 1, 2, 3, 4, 5]
    assert all(side == 1 for _, side in normal)
    # Reversed inline (Hendrix Strat): posts on the treble row, low E farthest.
    rev = fret_math.tuner_assign_stations(6, 6, reversed_=True)
    assert [k for k, _ in rev] == [5, 4, 3, 2, 1, 0]
    assert all(side == -1 for _, side in rev)


def test_assign_3_3_interleaves_globally():
    # Spec order E, e, A, B, D, G — six DISTINCT stations, outer strings nearest.
    assignment = fret_math.tuner_assign_stations(6, 3)
    assert [k for k, _ in assignment] == [0, 2, 4, 5, 3, 1]
    assert [side for _, side in assignment] == [1, 1, 1, -1, -1, -1]
    assert sorted(k for k, _ in assignment) == list(range(6))


def test_assign_3_3_reversed_starts_treble():
    assignment = fret_math.tuner_assign_stations(6, 3, reversed_=True)
    # Mirror: e nearest on the treble row, then E, B, A, G, D.
    assert [k for k, _ in assignment] == [1, 3, 5, 4, 2, 0]
    assert [side for _, side in assignment] == [1, 1, 1, -1, -1, -1]


def test_assign_4_2_reversed_mirrors_split():
    rev = fret_math.tuner_assign_stations(6, 4, reversed_=True)
    # Reversed 4+2 becomes 2+4: two bass-row posts, four treble-row posts.
    assert sum(1 for _, side in rev if side == 1) == 2
    assert sum(1 for _, side in rev if side == -1) == 4
    assert rev[5][0] == 0    # high e nearest


def test_straight_pull_posts_on_string_lines():
    geometry = _nut_geometry()
    posts = fret_math.tuner_straight_pull_posts(geometry, 6, 4.19, 2.33)
    for (nut_pt, (ux, uy), _b), (post, station, _side) in zip(geometry, posts):
        # Post is behind the nut by exactly its station, along the neck.
        assert math.isclose(nut_pt[0] - post[0], station, abs_tol=1e-9)
        # And it lies on the string's extended line.
        t = (post[0] - nut_pt[0]) / ux
        assert math.isclose(nut_pt[1] + uy * t, post[1], abs_tol=1e-9)
        assert t > 0
    # Inline: strictly increasing stations from bass outer to treble outer.
    stations = [s for _, s, _ in posts]
    assert stations == sorted(stations)
    assert math.isclose(stations[0], 4.19, abs_tol=1e-12)


def test_straight_pull_override_table():
    geometry = _nut_geometry()
    overrides = [None, 7.0, None, None, None, None]
    posts = fret_math.tuner_straight_pull_posts(geometry, 6, 4.19, 2.33,
                                                station_overrides=overrides)
    assert math.isclose(posts[1][1], 7.0, abs_tol=1e-12)
    assert math.isclose(posts[0][1], 4.19, abs_tol=1e-12)


def test_straight_pull_3_3_no_symmetric_collision():
    # The reviewed failure mode: naive symmetric per-side stations put the two
    # inner posts ~7 mm apart. The global sequence must keep ALL posts at
    # least a hole diameter apart for the default spacing.
    geometry = _nut_geometry()
    posts = fret_math.tuner_straight_pull_posts(geometry, 3, 4.19, 2.33)
    points = [p for p, _, _ in posts]
    assert fret_math.post_clearance_violations(points, 1.0) == []


def test_pattern_3_3_gibson_grid():
    posts = fret_math.tuner_pattern_posts(6, 3, 3.8, 3.5, 1.2)
    # Bass row at +1.2, treble row at -1.2, outer strings nearest.
    assert [side for _, _, side in posts] == [1, 1, 1, -1, -1, -1]
    assert all(math.isclose(abs(p[1]), 1.2, abs_tol=1e-12) for p, _, _ in posts)
    assert math.isclose(posts[0][1], 3.8, abs_tol=1e-12)      # E nearest
    assert math.isclose(posts[2][1], 3.8 + 2 * 3.5, abs_tol=1e-12)  # D farthest
    assert math.isclose(posts[5][1], 3.8, abs_tol=1e-12)      # e nearest
    # Reversed on a symmetric grid is a FULL no-op (geometry and assignment):
    # each string still reaches the nearest hole on its own side.
    rev = fret_math.tuner_pattern_posts(6, 3, 3.8, 3.5, 1.2, reversed_=True)
    assert rev == posts


def test_pattern_inline_reversed_flips_row():
    posts = fret_math.tuner_pattern_posts(6, 6, 4.19, 2.33, 1.0, reversed_=True)
    assert all(side == -1 for _, _, side in posts)
    assert math.isclose(posts[0][1], 4.19 + 5 * 2.33, abs_tol=1e-12)  # E farthest


def test_plan_face_mapping_with_break_offset():
    # Spec-mandated case: theta = 17 deg, break offset 25 mm (2.5 cm).
    theta = math.radians(17.0)
    plan = 4.19
    face = fret_math.plan_to_face_distance(plan, 2.5, theta)
    assert math.isclose(face, (4.19 - 2.5) / math.cos(theta), rel_tol=1e-12)
    assert face > plan - 2.5   # face distances are longer past the hinge
    # Round trip.
    assert math.isclose(fret_math.face_to_plan_distance(face, 2.5, theta),
                        plan, rel_tol=1e-12)
    # Naive mapping (no hinge) would be wrong by ~1.1 mm here.
    naive = plan / math.cos(theta)
    assert abs((naive - 2.5 / math.cos(theta) + 2.5) - plan) > 0.05
    # Before the hinge is an error.
    try:
        fret_math.plan_to_face_distance(1.0, 2.5, theta)
    except ValueError:
        pass
    else:
        raise AssertionError('post before the break line must raise')


def test_side_pull_angles_zero_for_straight_pull():
    geometry = _nut_geometry()
    posts = fret_math.tuner_straight_pull_posts(geometry, 6, 4.19, 2.33)
    for angle in fret_math.side_pull_angles(geometry, posts):
        assert abs(angle) < 1e-9


def test_side_pull_angles_nonzero_for_pattern():
    geometry = _nut_geometry()
    posts = fret_math.tuner_pattern_posts(6, 3, 3.8, 3.5, 1.2)
    angles = fret_math.side_pull_angles(geometry, posts)
    assert all(a >= 0 for a in angles)
    assert max(angles) > 3.0   # inner strings kink visibly on a 3+3 grid


def test_post_clearance_detects_close_pair():
    violations = fret_math.post_clearance_violations(
        [(0.0, 0.0), (0.5, 0.0), (5.0, 5.0)], 1.0)
    assert violations == [(0, 1, 0.5)]


def test_head_lengths_reach_posts():
    geometry = _nut_geometry()
    posts = fret_math.tuner_pattern_posts(6, 3, 3.8, 3.5, 1.2)
    lengths = fret_math.head_lengths_to_posts(geometry, posts, margin=0.5)
    strings = fret_math.string_layout(
        *_string_layout_args(), head_length=lengths)
    for (head, _bridge), (post, _s, _side) in zip(strings, posts):
        # Head end reaches at least the post's along-neck station.
        assert head[0] <= post[0] + 1e-9


def _string_layout_args():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    return (layout['fret_zero'], layout['bridge'], 6, 3.5, 5.25)


def test_string_layout_accepts_per_string_lengths():
    args = _string_layout_args()
    strings = fret_math.string_layout(*args, head_length=[1, 2, 3, 4, 5, 6])
    geometry = fret_math.string_nut_geometry(*args)
    for (head, _bridge), (nut_pt, _dir, _b), expected in zip(
            strings, geometry, [1, 2, 3, 4, 5, 6]):
        d = math.hypot(head[0] - nut_pt[0], head[1] - nut_pt[1])
        assert math.isclose(d, expected, abs_tol=1e-9)
    try:
        fret_math.string_layout(*args, head_length=[1, 2])
    except ValueError:
        pass
    else:
        raise AssertionError('length-count mismatch must raise')


def test_tuner_reference_straight_flat():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'straight', 6, False,
        hole_diameter=1.0, clearance_margin=0.8, angle=0.0, break_offset=0.0,
        first=4.19, spacing=2.33)
    assert not ref['tilted']
    assert ref['draw_posts'] == ref['plan_posts']
    assert ref['violations'] == []
    assert all(abs(a) < 1e-9 for a in ref['side_angles'])
    # Head extensions reach past each post (0.8 margin).
    for length, station in zip(ref['head_lengths'], ref['stations']):
        assert length > station


def test_tuner_reference_tilted_pattern_surface_distances():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    theta = math.radians(17.0)
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'pattern', 3, False,
        hole_diameter=1.0, clearance_margin=0.0, angle=theta, break_offset=0.35,
        pattern_first=4.0, pattern_pitch=3.5, pattern_row_offset=1.2)
    assert ref['tilted']
    # Face distance = surface station minus the flat run to the break line.
    f0, y0 = ref['draw_posts'][0]
    assert math.isclose(f0, 4.0 - 0.35, abs_tol=1e-12)
    assert math.isclose(abs(y0), 1.2, abs_tol=1e-12)
    # Plan projection is foreshortened past the hinge.
    x0, _ = ref['plan_posts'][0]
    assert math.isclose(-x0, 0.35 + (4.0 - 0.35) * math.cos(theta), abs_tol=1e-12)
    assert -x0 < 4.0
    # A post before the break line raises.
    try:
        fret_math.tuner_reference(
            layout, 6, 3.5, 5.25, 'pattern', 3, False,
            hole_diameter=1.0, clearance_margin=0.0, angle=theta,
            break_offset=4.5, pattern_first=4.0, pattern_pitch=3.5,
            pattern_row_offset=1.2)
    except ValueError:
        pass
    else:
        raise AssertionError('post before the break line must raise')


def test_tuner_reference_straight_tilted():
    # Spec A.3 case: straight pull on a 17 deg headstock, hinge 3.5 mm back.
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    theta = math.radians(17.0)
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'straight', 6, False,
        hole_diameter=1.0, clearance_margin=0.8, angle=theta, break_offset=0.35,
        first=4.19, spacing=2.33)
    assert ref['tilted']
    for (f, y_face), (x_plan, y_plan), station in zip(
            ref['draw_posts'], ref['plan_posts'], ref['stations']):
        # Longitudinal: station is PLAN; face distance stretches past the hinge.
        assert math.isclose(f, (station - 0.35) / math.cos(theta), rel_tol=1e-12)
        # Lateral is unchanged by the tilt.
        assert math.isclose(y_face, y_plan, abs_tol=1e-12)
    # A first post before the hinge raises.
    try:
        fret_math.tuner_reference(
            layout, 6, 3.5, 5.25, 'straight', 6, False,
            hole_diameter=1.0, clearance_margin=0.8, angle=theta,
            break_offset=4.5, first=4.19, spacing=2.33)
    except ValueError:
        pass
    else:
        raise AssertionError('first post before the break line must raise')


def test_tuner_reference_straight_multiscale_per_string_datum():
    # Fanned layout: each station is measured behind that string's OWN nut
    # point ("multi-scale safe by construction").
    layout = fret_math.slot_layout(68.58, 64.77, 22, 7, 3.0, 0.06)
    geometry = fret_math.string_nut_geometry(layout['fret_zero'],
                                             layout['bridge'], 6, 3.5, 5.25)
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'straight', 6, False,
        hole_diameter=1.0, clearance_margin=0.8, angle=0.0, break_offset=0.0,
        first=4.19, spacing=2.33)
    for (nut_pt, _u, _b), (x_post, _y), station in zip(
            geometry, ref['plan_posts'], ref['stations']):
        assert math.isclose(nut_pt[0] - x_post, station, abs_tol=1e-9)


def test_tuner_reference_reversed_stays_per_string_aligned():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'straight', 6, True,
        hole_diameter=1.0, clearance_margin=0.8, angle=0.0, break_offset=0.0,
        first=4.19, spacing=2.33)
    # Reversed inline: low E (string 0) farthest, on the treble row.
    assert math.isclose(ref['stations'][0], 4.19 + 5 * 2.33, abs_tol=1e-12)
    assert ref['sides'][0] == -1
    assert math.isclose(ref['stations'][5], 4.19, abs_tol=1e-12)
    # Outputs stay index-aligned per string: string 0's head extension is the
    # longest (its post is farthest), and every post is on its own line.
    assert ref['head_lengths'][0] == max(ref['head_lengths'])
    assert all(abs(a) < 1e-9 for a in ref['side_angles'])


def test_pattern_row_slant_fender_inline():
    # Fender-style slanted inline row: 0.281" lateral per 0.919" axial.
    axial, lateral = 2.33, 0.714
    posts = fret_math.tuner_pattern_posts(6, 6, 4.19, axial, 0.7,
                                          row_slant=lateral)
    ys = [post[1] for post, _s, _side in posts]
    for k in range(6):
        assert math.isclose(ys[k], 0.7 - k * lateral, abs_tol=1e-12)
    # The row marches toward (and across) the treble side at ~17 degrees.
    angle = math.degrees(math.atan2(lateral, axial))
    assert 16.5 < angle < 17.5


def test_tuner_reference_flags_collisions():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    # Naive-tight spacing on a 3+3 straight pull: inner strings converge, so
    # a tiny global spacing must trip the clearance check.
    ref = fret_math.tuner_reference(
        layout, 6, 3.5, 5.25, 'straight', 3, False,
        hole_diameter=1.0, clearance_margin=0.8, angle=0.0, break_offset=0.0,
        first=4.19, spacing=0.2)
    assert ref['violations']


# --- taper ------------------------------------------------------------------

def test_taper_outline_straight_case():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    corners = fret_math.taper_outline(layout['fret_zero'], layout['bridge'],
                                      layout['last'], 3.5, 5.25, 4.3, 0.5)
    front_bass, end_bass, end_treble, front_treble = corners
    # Front edge on the nut line, board width there = nut width.
    assert math.isclose(front_bass[0], 0.0, abs_tol=1e-9)
    assert math.isclose(front_treble[0], 0.0, abs_tol=1e-9)
    assert math.isclose(front_bass[1] - front_treble[1], 4.3, abs_tol=2e-3)
    # End edge past the last fret by the overhang.
    end_x = fret_math.fret_distance(SCALE, 22) + 0.5
    assert math.isclose(end_bass[0], end_x, abs_tol=1e-9)
    # Board widens toward the bridge.
    assert end_bass[1] - end_treble[1] > front_bass[1] - front_treble[1]
    # Symmetric about the center line.
    assert math.isclose(front_bass[1] + front_treble[1], 0.0, abs_tol=1e-9)


def test_taper_requires_margin():
    layout = fret_math.slot_layout(SCALE, SCALE, 22, 0, 3.0, 0.06)
    try:
        fret_math.taper_outline(layout['fret_zero'], layout['bridge'],
                                layout['last'], 3.5, 5.25, 3.5, 0.5)
    except ValueError:
        pass
    else:
        raise AssertionError('nut width == spread must raise')


# --- helpers ----------------------------------------------------------------

def test_place_maps_local_frame():
    # Neck along +y in sketch space, fret 0 at (2, 1): local (3, 0) -> (2, 4);
    # local +y (across) points left of travel = -x.
    x, y = fret_math.place((3.0, 0.0), 2.0, 1.0, 0.0, 1.0)
    assert math.isclose(x, 2.0, abs_tol=1e-12)
    assert math.isclose(y, 4.0, abs_tol=1e-12)
    x, y = fret_math.place((0.0, 1.0), 2.0, 1.0, 0.0, 1.0)
    assert math.isclose(x, 1.0, abs_tol=1e-12)
    assert math.isclose(y, 1.0, abs_tol=1e-12)


def test_line_intersection():
    point = fret_math.line_intersection((0, 0), (1, 0), (5, -2), (0, 1))
    assert math.isclose(point[0], 5.0, abs_tol=1e-12)
    assert math.isclose(point[1], 0.0, abs_tol=1e-12)


def test_closest_point_parameter_skew_lines():
    t = fret_math.closest_point_parameter(
        (0, 0, 0), (1, 0, 0), (3, 1, -1), (0, 0, 1))
    assert math.isclose(t, 3.0, abs_tol=1e-12)


def test_closest_point_parameter_crossing_lines():
    t = fret_math.closest_point_parameter(
        (0, 0, 0), (2, 0, 0), (5, -2, 0), (0, 1, 0))
    assert math.isclose(t, 2.5, abs_tol=1e-12)


def test_closest_point_parameter_parallel_raises():
    try:
        fret_math.closest_point_parameter(
            (0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0))
    except ValueError:
        pass
    else:
        raise AssertionError('parallel lines must raise ValueError')
