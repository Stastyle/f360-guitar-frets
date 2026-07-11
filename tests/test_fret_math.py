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
