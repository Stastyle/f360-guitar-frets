# "Create Fretboard" command: creates a complete fretboard from scratch as a
# new component — the tapered board body itself, fret slots (standard or
# multi-scale/fanned) as sketch or cut, an optional nut slot, a bridge mark,
# string guide lines, an optional single/compound radius cut, and a tuner
# post layout. Nothing has to exist beforehand: fret 0 sits at the component
# origin, the neck runs along +X, and the board top lies on the XY plane.
# An existing layout can be picked from the Edit dropdown and rebuilt in place.

import json
import math
import os
import traceback

import adsk.core
import adsk.fusion

from . import fret_math
from .constants import ATTRIBUTE_GROUP, ATTRIBUTE_NAME
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')

DEFAULTS = {
    'scale_length_expr': '25.5 in',
    'fret_count': 22,
    'slot_width_expr': '0.6 mm',
    'slot_length_expr': '60 mm',
    'create_nut_slot': False,
    'nut_slot_width_expr': '3.5 mm',
    'nut_slot_depth_expr': '1.5 mm',
    'cut_slots': True,
    'slot_depth_expr': '2.5 mm',
    'mark_bridge': True,
    'draw_strings': True,
    'string_count': 6,
    'string_spread_nut_expr': '35 mm',
    'string_spread_bridge_expr': '52.5 mm',
    'headstock_length_expr': '150 mm',
    'board_thickness_expr': '6 mm',
    'board_setback_expr': '0 mm',
    'nut_width_expr': '43 mm',
    'board_overhang_expr': '5 mm',
    'multiscale': False,
    'bass_scale_expr': '26.5 in',
    'treble_scale_expr': '25.5 in',
    'perpendicular_fret': 7,
    'radius_mode': 'No radius',
    'radius_start_expr': '9.5 in',
    'radius_end_expr': '16 in',
    'place_tuners': False,
    'tuner_mode': 'Straight pull',
    'tuner_bass_count': 6,
    'tuner_reversed': False,
    'headstock_angle_expr': '0 deg',
    'face_drop_expr': '6 mm',
    'break_offset_expr': '3.5 mm',
    'tuner_first_expr': '41.9 mm',
    'tuner_spacing_expr': '23.3 mm',
    'pattern_first_expr': '40 mm',
    'pattern_pitch_expr': '35 mm',
    'pattern_row_offset_expr': '12 mm',
    'pattern_row_slant_expr': '0 mm',
    'tuner_hole_preset': '10 mm (modern sealed)',
    'tuner_hole_expr': '10 mm',
    'tuner_clearance_expr': '8 mm',
    'buttons_promoted': False,
}

# Settings key -> dialog input id. Used in both directions: to refill the
# dialog from a settings dict (_apply_settings) and to store the dialog back
# into settings.json (on_destroy). Keep in sync with the inputs on_create adds.
EXPRESSION_INPUTS = (
    ('scale_length_expr', 'scale_length'),
    ('slot_width_expr', 'slot_width'),
    ('slot_length_expr', 'slot_length'),
    ('nut_slot_width_expr', 'nut_slot_width'),
    ('nut_slot_depth_expr', 'nut_slot_depth'),
    ('slot_depth_expr', 'slot_depth'),
    ('string_spread_nut_expr', 'string_spread_nut'),
    ('string_spread_bridge_expr', 'string_spread_bridge'),
    ('headstock_length_expr', 'headstock_length'),
    ('board_thickness_expr', 'board_thickness'),
    ('board_setback_expr', 'board_setback'),
    ('nut_width_expr', 'nut_width'),
    ('board_overhang_expr', 'board_overhang'),
    ('bass_scale_expr', 'bass_scale'),
    ('treble_scale_expr', 'treble_scale'),
    ('radius_start_expr', 'radius_start'),
    ('radius_end_expr', 'radius_end'),
    ('headstock_angle_expr', 'headstock_angle'),
    ('face_drop_expr', 'face_drop'),
    ('break_offset_expr', 'break_offset'),
    ('tuner_first_expr', 'tuner_first'),
    ('tuner_spacing_expr', 'tuner_spacing'),
    ('pattern_first_expr', 'pattern_first'),
    ('pattern_pitch_expr', 'pattern_pitch'),
    ('pattern_row_offset_expr', 'pattern_row_offset'),
    ('pattern_row_slant_expr', 'pattern_row_slant'),
    ('tuner_hole_expr', 'tuner_hole_custom'),
    ('tuner_clearance_expr', 'tuner_clearance'),
)
# (settings key, input id, minimum, maximum) — the range is the spinner's own,
# a stored value outside it is ignored rather than clamped.
SPINNER_INPUTS = (
    ('fret_count', 'fret_count', 1, 36),
    ('string_count', 'string_count', 1, 12),
    ('perpendicular_fret', 'perpendicular_fret', 0, 36),
    ('tuner_bass_count', 'tuner_bass_count', 0, 12),
)
CHECKBOX_INPUTS = (
    ('create_nut_slot', 'create_nut_slot'),
    ('cut_slots', 'cut_slots'),
    ('mark_bridge', 'mark_bridge'),
    ('draw_strings', 'draw_strings'),
    ('multiscale', 'multiscale'),
    ('place_tuners', 'place_tuners'),
    ('tuner_reversed', 'tuner_reversed'),
)
DROPDOWN_INPUTS = (
    ('radius_mode', 'radius_mode'),
    ('tuner_mode', 'tuner_mode'),
    ('tuner_hole_preset', 'tuner_hole_preset'),
)
# (group input id, settings key that decides whether it starts expanded)
GROUP_EXPANDERS = (
    ('grp_multiscale', 'multiscale'),
    ('grp_strings', 'draw_strings'),
    ('grp_radius', 'radius_mode'),
    ('grp_hardware', 'place_tuners'),
)

# The first two entries of the Start-from dropdown create a new fretboard;
# everything after them is an existing layout to edit (_edit_sketch_from_inputs
# maps a selection back to self._edit_sketches by this offset).
CREATE_NEW_LABEL = 'New fretboard (last used values)'
CREATE_DEFAULT_LABEL = 'New fretboard (default values)'
NEW_LAYOUT_LABELS = (CREATE_NEW_LABEL, CREATE_DEFAULT_LABEL)

RADIUS_MODES = ('No radius', 'Single radius', 'Compound radius')
TUNER_MODES = ('Straight pull', 'Pattern (two rows)')
# Peghead hole diameters in cm (Fusion internal units); see HARDWARE_RESEARCH.md.
HOLE_PRESETS = (
    ('10 mm (modern sealed)', 1.0),
    ('11/32 in (vintage Kluson)', 0.873125),
    ('Custom', None),
)
MAX_HEADSTOCK_ANGLE = math.radians(25.0)

# sin(15 deg): sanity limit for the sketch-frame mapping (see _sketch_frame).
OUT_OF_PLANE_SIN_LIMIT = 0.2588

# Layouts of metadata version >= 7 own their board (created-board flow);
# older sketches cut a pre-existing board via selections the dialog no
# longer has, so they cannot be rebuilt and are hidden from Edit.
MIN_EDITABLE_METADATA_VERSION = 7


class FretSlotsError(Exception):
    """Expected geometric problem, reported to the user without a traceback."""


class _Params(object):
    pass


def load_settings():
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, 'r') as handle:
            stored = json.load(handle)
        for key in DEFAULTS:
            if key in stored and isinstance(stored[key], type(DEFAULTS[key])):
                settings[key] = stored[key]
        # Settings from the cut-a-board era stored a nut offset (the layout
        # shifted into the board); the created-board equivalent is starting
        # the board that far behind the nut.
        if 'board_setback_expr' not in stored and isinstance(
                stored.get('nut_slot_offset_expr'), str):
            settings['board_setback_expr'] = stored['nut_slot_offset_expr']
    except Exception:
        pass
    if settings['radius_mode'] not in RADIUS_MODES:
        settings['radius_mode'] = DEFAULTS['radius_mode']
    if settings['tuner_mode'] not in TUNER_MODES:
        settings['tuner_mode'] = DEFAULTS['tuner_mode']
    if settings['tuner_hole_preset'] not in [name for name, _ in HOLE_PRESETS]:
        settings['tuner_hole_preset'] = DEFAULTS['tuner_hole_preset']
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as handle:
            json.dump(settings, handle, indent=2)
    except Exception:
        pass


def _entity_token(entity):
    try:
        return entity.entityToken
    except Exception:
        return ''


def _sketch_metadata(sketch):
    try:
        attribute = sketch.attributes.itemByName(ATTRIBUTE_GROUP, ATTRIBUTE_NAME)
        if attribute and attribute.value:
            return json.loads(attribute.value)
    except Exception:
        pass
    return {}


def _find_fret_sketches(design):
    """Every sketch this add-in tagged as a rebuildable fret layout."""
    sketches = []
    for attribute in design.findAttributes(ATTRIBUTE_GROUP, ATTRIBUTE_NAME):
        parent = attribute.parent
        if not parent:  # the sketch was deleted; attributes can outlive entities
            continue
        sketch = adsk.fusion.Sketch.cast(parent)
        if not (sketch and sketch.isValid):
            continue
        version = _sketch_metadata(sketch).get('version', 0)
        if isinstance(version, int) and version >= MIN_EDITABLE_METADATA_VERSION:
            sketches.append(sketch)
    return sketches


def _read_values(inputs):
    problems = {}
    values = {}

    def read_length(input_id, label, target=None):
        value_input = inputs.itemById(input_id)
        if not value_input or not value_input.isValidExpression:
            problems[input_id] = '{}: enter a valid length.'.format(label)
            return None
        value = value_input.value
        if value <= 0:
            problems[input_id] = '{}: must be greater than zero.'.format(label)
            return None
        if target is not None:
            values[target] = value
        return value

    tuners_checkbox = inputs.itemById('place_tuners')
    place_tuners_on = bool(tuners_checkbox.value) if tuners_checkbox else False

    for input_id, label in (
        ('slot_width', 'Fret slot width'),
        ('slot_length', 'Fret slot length'),
        ('board_thickness', 'Board thickness'),
        ('string_spread_nut', 'String spread at nut'),
        ('string_spread_bridge', 'String spread at bridge'),
        ('nut_width', 'Nut width'),
        ('board_overhang', 'Board end past last fret'),
    ):
        read_length(input_id, label, input_id)

    if place_tuners_on:
        # The manual head-line length is unused (and hidden) while the tuner
        # feature computes per-string extensions — read it leniently so a
        # stale value never blocks the build, but keep it for the metadata.
        head_input = inputs.itemById('headstock_length')
        values['headstock_length'] = (
            head_input.value
            if head_input and head_input.isValidExpression
            and head_input.value > 0 else None)
    else:
        read_length('headstock_length', 'Headstock line length',
                    'headstock_length')

    spinner = inputs.itemById('fret_count')
    values['fret_count'] = int(spinner.value) if spinner else DEFAULTS['fret_count']
    string_spinner = inputs.itemById('string_count')
    values['string_count'] = int(string_spinner.value) if string_spinner else 6

    multiscale_checkbox = inputs.itemById('multiscale')
    values['multiscale'] = bool(multiscale_checkbox.value) if multiscale_checkbox else False
    if values['multiscale']:
        values['bass_scale'] = read_length('bass_scale', 'Bass side scale')
        values['treble_scale'] = read_length('treble_scale', 'Treble side scale')
        perp_spinner = inputs.itemById('perpendicular_fret')
        values['perpendicular_fret'] = int(perp_spinner.value) if perp_spinner else 7
    else:
        values['bass_scale'] = values['treble_scale'] = read_length(
            'scale_length', 'Scale length')
        values['perpendicular_fret'] = 0

    cut_checkbox = inputs.itemById('cut_slots')
    cut_enabled = bool(cut_checkbox.value) if cut_checkbox else False

    checkbox = inputs.itemById('create_nut_slot')
    values['nut_slot_width'] = None
    values['nut_slot_depth'] = None
    if checkbox and checkbox.value:
        values['nut_slot_width'] = read_length('nut_slot_width', 'Nut slot width')
        if cut_enabled:
            values['nut_slot_depth'] = read_length('nut_slot_depth', 'Nut slot depth')

    values['cut_depth'] = None
    if cut_enabled:
        values['cut_depth'] = read_length('slot_depth', 'Slot depth')

    values['radius_mode'] = None
    dropdown = inputs.itemById('radius_mode')
    if dropdown and dropdown.selectedItem:
        mode = dropdown.selectedItem.name
        if mode == 'Single radius':
            values['radius_mode'] = 'single'
        elif mode == 'Compound radius':
            values['radius_mode'] = 'compound'
    values['radius_start'] = values['radius_end'] = None
    if values['radius_mode']:
        values['radius_start'] = read_length('radius_start', 'Radius at nut')
        if values['radius_mode'] == 'compound':
            values['radius_end'] = read_length('radius_end', 'Radius at board end')
        else:
            values['radius_end'] = values['radius_start']

    for key, input_id in (('mark_bridge', 'mark_bridge'),
                          ('draw_strings', 'draw_strings')):
        checkbox = inputs.itemById(input_id)
        values[key] = bool(checkbox.value) if checkbox else False

    def read_nonnegative(input_id, label, maximum=None):
        # Zero is a legitimate value here (unlike read_length).
        value_input = inputs.itemById(input_id)
        if not value_input or not value_input.isValidExpression:
            problems[input_id] = '{}: enter a valid value (0 allowed).'.format(label)
            return None
        value = value_input.value
        if value < 0:
            problems[input_id] = '{}: must not be negative.'.format(label)
            return None
        if maximum is not None and value > maximum:
            problems[input_id] = '{}: too large.'.format(label)
            return None
        return value

    values['board_setback'] = read_nonnegative(
        'board_setback', 'Board start behind nut') or 0.0

    values['place_tuners'] = place_tuners_on
    values['tuner_mode'] = None
    values['headstock_angle'] = 0.0
    if values['place_tuners']:
        dropdown = inputs.itemById('tuner_mode')
        mode_name = dropdown.selectedItem.name if dropdown and dropdown.selectedItem \
            else TUNER_MODES[0]
        values['tuner_mode'] = ('pattern' if mode_name == 'Pattern (two rows)'
                                else 'straight')
        spinner = inputs.itemById('tuner_bass_count')
        values['tuner_bass_count'] = int(spinner.value) if spinner else 6
        checkbox = inputs.itemById('tuner_reversed')
        values['tuner_reversed'] = bool(checkbox.value) if checkbox else False

        # The angle input uses degree units; .value is radians. 0 is valid.
        angle = read_nonnegative('headstock_angle', 'Headstock angle',
                                 maximum=MAX_HEADSTOCK_ANGLE * 1.001)
        values['headstock_angle'] = angle if angle is not None else 0.0
        # Read these even at angle 0, so the metadata keeps what the dialog
        # shows — otherwise a later edit that raises the angle would silently
        # run with face_drop/break_offset zeroed by the prefill.
        values['face_drop'] = read_nonnegative('face_drop', 'Face drop') or 0.0
        values['break_offset'] = read_nonnegative('break_offset',
                                                  'Break line offset') or 0.0

        if values['tuner_mode'] == 'straight':
            values['tuner_first'] = read_length('tuner_first',
                                                'First post distance')
            values['tuner_spacing'] = read_length('tuner_spacing', 'Post spacing')
        else:
            values['pattern_first'] = read_length('pattern_first',
                                                  'First post distance')
            values['pattern_pitch'] = read_length('pattern_pitch', 'Post pitch')
            values['pattern_row_offset'] = read_nonnegative(
                'pattern_row_offset', 'Row offset from center')
            values['pattern_row_slant'] = read_nonnegative(
                'pattern_row_slant', 'Row slant per station')

        hole_dropdown = inputs.itemById('tuner_hole_preset')
        hole_name = (hole_dropdown.selectedItem.name
                     if hole_dropdown and hole_dropdown.selectedItem
                     else HOLE_PRESETS[0][0])
        values['tuner_hole'] = None
        for name, diameter in HOLE_PRESETS:
            if name == hole_name and diameter is not None:
                values['tuner_hole'] = diameter
        if values['tuner_hole'] is None:
            values['tuner_hole'] = read_length('tuner_hole_custom',
                                               'Post hole diameter')
        values['tuner_clearance'] = read_nonnegative('tuner_clearance',
                                                     'Housing clearance margin')

    return values, list(problems.values())


def validate_and_compute(inputs, edit_sketch=None):
    """Validate all inputs. Returns (ok, message, params)."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return False, 'Open a design in the Design workspace first.', None

    values, problems = _read_values(inputs)
    if problems:
        return False, '\n'.join(problems), None

    fret_count = values['fret_count']
    slot_width = values['slot_width']
    half_span = values['slot_length'] / 2.0

    if values['multiscale'] and values['perpendicular_fret'] > fret_count:
        return False, ('The perpendicular fret must not exceed the number of '
                       'frets.'), None

    for scale in (values['bass_scale'], values['treble_scale']):
        last_spacing = (fret_math.fret_distance(scale, fret_count)
                        - fret_math.fret_distance(scale, fret_count - 1))
        if slot_width >= last_spacing:
            return False, ('The fret slot width is larger than the spacing between '
                           'the last two frets, so slots would overlap. Reduce the '
                           'slot width or the number of frets.'), None

    if values['nut_width'] <= values['string_spread_nut']:
        return False, ('Nut width must be larger than the string spread at the '
                       'nut, so the board has an edge margin.'), None

    for depth, label in ((values['cut_depth'], 'Slot depth'),
                         (values['nut_slot_depth'], 'Nut slot depth')):
        if depth and depth >= values['board_thickness']:
            return False, ('{} must be smaller than the board thickness — the '
                           'cut would go clean through the board.'.format(label)), None

    if values['nut_slot_width'] and values['cut_depth']:
        # The nut seat extends behind the nut line and the board front edge
        # runs parallel to that line (fanned or not), so without a board
        # setback there is no material under the seat to cut — the fan skew
        # contributes nothing.
        if values['board_setback'] <= 1e-9:
            return False, ('The nut slot lies entirely behind the board front '
                           'edge, so there is nothing to cut it into. Raise '
                           '"Board start behind nut" (the nut slot width '
                           'covers the whole seat).'), None

    if values['place_tuners']:
        if values['tuner_bass_count'] > values['string_count']:
            return False, ('Bass-side tuner count must not exceed the number '
                           'of strings.'), None
        if values['multiscale'] and values['tuner_mode'] == 'pattern':
            return False, ('Pattern tuner layouts need a single-scale layout — '
                           'a fanned nut breaks the fixed-grid assumptions. '
                           'Use Straight pull, or disable Multi-scale.'), None
        if values['multiscale'] and values['headstock_angle'] > 1e-9:
            return False, ('A tilted headstock plane is not supported for '
                           'multi-scale layouts yet — set the headstock angle '
                           'to 0 (the plan-view posts stay correct).'), None
        if values['headstock_angle'] > 1e-9:
            first = (values.get('tuner_first')
                     if values['tuner_mode'] == 'straight'
                     else values.get('pattern_first'))
            if first is not None and first <= values['break_offset']:
                return False, ('The first tuner post must sit beyond the '
                               'headstock break line (increase the first post '
                               'distance or reduce the break offset).'), None

    radius_span = half_span
    if values['radius_mode']:
        # The radius cut must cover the board at its widest point, or the
        # loft leaves flat shoulders along the edges near the board end.
        try:
            probe = fret_math.slot_layout(
                values['bass_scale'], values['treble_scale'], fret_count,
                values['perpendicular_fret'], half_span, slot_width)
            corners = fret_math.taper_outline(
                probe['fret_zero'], probe['bridge'], probe['last'],
                values['string_spread_nut'], values['string_spread_bridge'],
                values['nut_width'], values['board_overhang'],
                setback=values['board_setback'])
            radius_span = max(half_span,
                              max(abs(corner[1]) for corner in corners) * 1.02)
        except ValueError:
            pass
        for radius in (values['radius_start'], values['radius_end']):
            if radius <= radius_span * 1.02:
                return False, ('The fretboard radius must be larger than half '
                               'the board width at its widest point (and half '
                               'the fret slot length).'), None
        min_radius = min(values['radius_start'], values['radius_end'])
        drop = min_radius - math.sqrt(max(0.0, min_radius ** 2
                                          - radius_span ** 2))
        if drop >= values['board_thickness']:
            return False, ('The radius cut would remove the full board '
                           'thickness at the edges — use a larger radius, a '
                           'shorter fret slot length, or a thicker '
                           'board.'), None

    params = _Params()
    for key, value in values.items():
        setattr(params, key, value)
    params.half_span = half_span
    params.radius_span = radius_span
    params.edit_sketch = edit_sketch

    return True, _success_message(design.unitsManager, params), params


def _tuner_layout_geometry(params, layout):
    """Adapter: full tuner-post geometry via fret_math.tuner_reference (pure
    python, unit-tested there). Raises ValueError on degenerate geometry —
    reported as a FretSlotsError by the callers."""
    return fret_math.tuner_reference(
        layout, params.string_count, params.string_spread_nut,
        params.string_spread_bridge, params.tuner_mode,
        params.tuner_bass_count, params.tuner_reversed, params.tuner_hole,
        params.tuner_clearance, params.headstock_angle, params.break_offset,
        first=getattr(params, 'tuner_first', None),
        spacing=getattr(params, 'tuner_spacing', None),
        pattern_first=getattr(params, 'pattern_first', None),
        pattern_pitch=getattr(params, 'pattern_pitch', None),
        pattern_row_offset=getattr(params, 'pattern_row_offset', None),
        pattern_row_slant=getattr(params, 'pattern_row_slant', 0.0) or 0.0)


def _success_message(units_manager, params):
    units = units_manager.defaultLengthUnits

    def fmt(value):
        return units_manager.formatInternalValue(value, units, True)

    center_scale = (params.bass_scale + params.treble_scale) / 2.0
    lines = []
    if params.edit_sketch:
        lines.append('Editing "{}" — OK replaces its geometry.'.format(params.edit_sketch.name))
    if params.multiscale:
        lines.append('Multi-scale {} / {}, straight at fret {}. Bass side is on '
                     'the LEFT looking from nut to bridge — swap the scales if '
                     'the fan leans the wrong way.'
                     .format(fmt(params.bass_scale), fmt(params.treble_scale),
                             params.perpendicular_fret))
    if params.fret_count >= 12:
        lines.append('Fret 12 (center): {} from the nut (= scale / 2).'
                     .format(fmt(fret_math.fret_distance(center_scale, 12))))
    lines.append('Fret {} (last, center): {} from the nut.'
                 .format(params.fret_count,
                         fmt(fret_math.fret_distance(center_scale, params.fret_count))))
    if params.mark_bridge:
        lines.append('Bridge mark: {} from the nut (theoretical saddle point; '
                     'add compensation).'.format(fmt(center_scale)))
    if params.nut_slot_width:
        rear, front = fret_math.nut_slot_span(
            params.bass_scale, params.treble_scale, params.perpendicular_fret,
            params.nut_slot_width)
        lines.append('Nut slot spans {} to {} around fret 0 (negative = '
                     'behind it, toward the headstock).'
                     .format(fmt(rear), fmt(front)))
        # Coverage is perpendicular to the (possibly fanned) nut line, which
        # the board front edge parallels — the fan skew covers nothing.
        required = fret_math.nut_seat_setback_required(
            params.bass_scale, params.treble_scale, params.perpendicular_fret,
            params.half_span, params.nut_slot_width)
        if params.board_setback + 1e-9 < required:
            lines.append('WARNING: the board starts only {} behind fret 0, so '
                         'part of the nut seat hangs off the board front — '
                         'raise "Board start behind nut" to {} to cover it.'
                         .format(fmt(params.board_setback), fmt(required)))
    if params.place_tuners:
        try:
            probe = fret_math.slot_layout(
                params.bass_scale, params.treble_scale, params.fret_count,
                params.perpendicular_fret, params.half_span, params.slot_width)
            tuner_geo = _tuner_layout_geometry(params, probe)
        except ValueError as error:
            lines.append('Tuner layout problem: {}.'.format(error))
        else:
            geometry = fret_math.string_nut_geometry(
                probe['fret_zero'], probe['bridge'], params.string_count,
                params.string_spread_nut, params.string_spread_bridge)
            farthest = max(nut_pt[0] - post[0] for (nut_pt, _u, _b), post in
                           zip(geometry, tuner_geo['plan_posts']))
            lines.append('Tuner posts: farthest {} behind the nut (plan view).'
                         .format(fmt(farthest)))
            if tuner_geo['tilted']:
                lines.append('Posts are drawn on the tilted headstock plane in '
                             'TRUE face distances — drill perpendicular to '
                             'that face.')
                if (params.nut_slot_width
                        and params.break_offset < params.nut_slot_width):
                    lines.append('WARNING: the headstock face starts tilting '
                                 '{} behind fret 0, INSIDE the nut seat ({} '
                                 'wide) — raise "Break line behind nut" to at '
                                 'least the nut slot width.'
                                 .format(fmt(params.break_offset),
                                         fmt(params.nut_slot_width)))
            worst = max(tuner_geo['side_angles'])
            if worst > 0.5:
                lines.append('Max side pull at the nut: {:.1f} deg (plan view; '
                             'flare each nut slot toward its post — the true '
                             '3D pull is slightly larger).'.format(worst))
            for i, j, distance in tuner_geo['violations'][:2]:
                lines.append('WARNING: posts of strings {} and {} are only {} '
                             'apart — tuner housings will collide. Increase '
                             'the spacing/pitch or change the split.'
                             .format(i + 1, j + 1, fmt(distance)))

    board_length = (params.board_setback
                    + fret_math.fret_distance(center_scale, params.fret_count)
                    + params.board_overhang)
    lines.append('Board: about {} long, {} wide at the nut, {} thick.'
                 .format(fmt(board_length), fmt(params.nut_width),
                         fmt(params.board_thickness)))

    slot_count = params.fret_count + (1 if params.nut_slot_width else 0)
    summary = '{} slots'.format(slot_count)
    if params.draw_strings:
        summary += ', {} string lines'.format(params.string_count)
    lines.append(summary + '. The board is built in its own component: '
                 'fret 0 at the origin, neck along +X, top face on the XY '
                 'plane — move or joint the component to place it.')
    if params.cut_depth:
        lines.append('Slots will be cut {} deep.'.format(fmt(params.cut_depth)))
    if params.radius_mode:
        drop = params.radius_start - math.sqrt(
            max(0.0, params.radius_start ** 2 - params.half_span ** 2))
        lines.append('Radius drop at the slot ends: {} — edge slots end up that '
                     'much shallower.'.format(fmt(drop)))
    return '\n'.join(lines)


def _fix_all_curves(sketch):
    """Lock every curve so the sketch is fully defined and undraggable."""
    try:
        curves = [sketch.sketchCurves.item(i)
                  for i in range(sketch.sketchCurves.count)]
    except Exception:
        return
    for curve in curves:
        try:
            curve.isFixed = True
        except Exception:
            pass


def _clear_sketch_curves(sketch):
    curves = [sketch.sketchCurves.item(i) for i in range(sketch.sketchCurves.count)]
    for curve in curves:
        try:
            if curve.isValid:
                curve.deleteMe()
        except Exception:
            pass


def _create_sketch(component):
    """New sketch on the component's XY construction plane (the board top).

    Everything is drawn in the fretboard component's own space, so no
    occurrence/proxy mapping is needed — the canonical frame puts fret 0 at
    the origin with the neck along +x.
    """
    return component.sketches.add(component.xYConstructionPlane)


def _sketch_frame(mapping_sketch, fret_zero, direction):
    """Fret 0 and the neck direction expressed in a sketch's 2D space."""
    sketch_zero = mapping_sketch.modelToSketchSpace(fret_zero.copy())
    step_point = fret_zero.copy()
    step_point.translateBy(direction)  # one internal unit along the neck
    sketch_step = mapping_sketch.modelToSketchSpace(step_point)

    if abs(sketch_step.z - sketch_zero.z) > OUT_OF_PLANE_SIN_LIMIT:
        raise FretSlotsError('The center line runs more than 15 degrees out '
                             'of the fretboard plane.')
    dx, dy = fret_math.normalize(sketch_step.x - sketch_zero.x,
                                 sketch_step.y - sketch_zero.y)
    return sketch_zero, dx, dy


def _place_point(local_point, frame):
    sketch_zero, dx, dy = frame
    x, y = fret_math.place(local_point, sketch_zero.x, sketch_zero.y, dx, dy)
    return adsk.core.Point3D.create(x, y, 0.0)


def _sketch_name(params, prefix):
    try:
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
        units_manager = design.unitsManager
        units = units_manager.defaultLengthUnits
        if params.multiscale:
            scale_text = '{}-{}'.format(
                units_manager.formatInternalValue(params.treble_scale, units, True),
                units_manager.formatInternalValue(params.bass_scale, units, True))
        else:
            scale_text = units_manager.formatInternalValue(
                params.bass_scale, units, True)
    except Exception:
        scale_text = ''
    if scale_text:
        return '{} ({}, {} frets)'.format(prefix, scale_text, params.fret_count)
    return '{} ({} frets)'.format(prefix, params.fret_count)


def _delete_tracked(design, metadata):
    """Remove everything a previous run of this add-in created for a layout
    (except the slot sketch itself). Order matters: features first, then the
    sketches and planes they consume."""
    groups = (
        ('nut_cut_token', adsk.fusion.ExtrudeFeature),
        ('cut_token', adsk.fusion.ExtrudeFeature),
        ('radius_feature_token', adsk.fusion.LoftFeature),
        ('radius_sketch_tokens', adsk.fusion.Sketch),
        ('radius_plane_tokens', adsk.fusion.ConstructionPlane),
        # Tuner chain in consumed-last order: the sketch lives on the angled
        # plane, whose hinge line lives in the hinge sketch, which may live
        # on the offset plane.
        ('tuners_token', adsk.fusion.Sketch),
        ('tuner_angled_plane_token', adsk.fusion.ConstructionPlane),
        ('tuner_hinge_token', adsk.fusion.Sketch),
        ('tuner_offset_plane_token', adsk.fusion.ConstructionPlane),
        ('bridge_token', adsk.fusion.Sketch),
        ('strings_token', adsk.fusion.Sketch),
        # The board extrude consumes the outline sketch — feature first.
        ('board_token', adsk.fusion.ExtrudeFeature),
        ('taper_token', adsk.fusion.Sketch),
    )
    for key, cls in groups:
        tokens = metadata.get(key) or []
        if isinstance(tokens, str):
            tokens = [tokens] if tokens else []
        for token in tokens:
            try:
                for entity in design.findEntityByToken(token):
                    obj = cls.cast(entity)
                    if obj and obj.isValid:
                        obj.deleteMe()
            except Exception:
                pass


def _cut_profiles(sketch, profiles, depth, participant_body, what):
    """Extrude-cut the given profiles 'depth' into the board."""
    if profiles.count == 0:
        raise FretSlotsError('No {} profiles found to cut.'.format(what))
    features = sketch.parentComponent.features.extrudeFeatures

    # The sketch normal usually points out of the board, so cutting into it
    # means a negative distance — but the orientation is not guaranteed, so
    # fall back to the other direction when the first cut removes nothing.
    for signed_depth in (-depth, depth):
        try:
            cut_input = features.createInput(
                profiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
            cut_input.setDistanceExtent(
                False, adsk.core.ValueInput.createByReal(signed_depth))
            if participant_body:
                cut_input.participantBodies = [participant_body]
            return features.add(cut_input)
        except Exception:
            continue
    raise FretSlotsError('Could not cut the {} — check that the depth '
                         'reaches into the board. Uncheck "Cut slots" to '
                         'create the sketch only.'.format(what))


def _extrude_board(taper_sketch, thickness):
    """Extrude the outline sketch into the fretboard body.

    The board hangs BELOW the sketch plane — the top face stays on the XY
    plane at z = 0, where all the layout sketches live and where the slot
    cuts measure their depth from. The extent sign convention is not
    trusted: a body that ends up above the plane is deleted and redone the
    other way.
    """
    if taper_sketch.profiles.count == 0:
        raise FretSlotsError('The fretboard outline did not form a closed '
                             'profile to extrude.')
    profiles = adsk.core.ObjectCollection.create()
    for profile in taper_sketch.profiles:
        profiles.add(profile)
    features = taper_sketch.parentComponent.features.extrudeFeatures
    for signed_thickness in (-thickness, thickness):
        try:
            extrude_input = features.createInput(
                profiles, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            extrude_input.setDistanceExtent(
                False, adsk.core.ValueInput.createByReal(signed_thickness))
            feature = features.add(extrude_input)
        except Exception:
            continue
        if feature.bodies.count > 0:
            box = feature.bodies.item(0).boundingBox
            if box and box.maxPoint.z <= 1e-4:
                return feature
        try:
            feature.deleteMe()
        except Exception:
            pass
    raise FretSlotsError('Could not extrude the fretboard body from the '
                         'outline.')


def _partition_slot_profiles(sketch, fret_area, nut_area):
    """Split the sketch's profiles into (fret slots, nut slot) by area.

    Area is a scalar, so this is immune to sketch/model coordinate-space
    ambiguity. Returns (fret_profiles, nut_profiles) ObjectCollections;
    call only when the two expected areas are clearly distinguishable.
    """
    threshold = (fret_area + nut_area) / 2.0
    fret_profiles = adsk.core.ObjectCollection.create()
    nut_profiles = adsk.core.ObjectCollection.create()
    for profile in sketch.profiles:
        try:
            area = profile.areaProperties().area
        except Exception:
            area = 0.0
        if area >= threshold:
            nut_profiles.add(profile)
        else:
            fret_profiles.add(profile)
    return fret_profiles, nut_profiles


def _apply_radius(params, component, layout, board):
    """Loft-cut a single or compound radius onto the board top.

    Two arc profiles are sketched on transverse planes just behind the board
    front and just past the board end, then lofted as a cut restricted to
    the board body. Returns (loft_feature, sketches, planes) for edit-mode
    tracking. Raises FretSlotsError with a hint when the geometry cannot be
    built.
    """
    up = adsk.core.Vector3D.create(0.0, 0.0, 1.0)

    # Stations along the neck (local x): behind the (possibly fanned) board
    # front and past the board end, so the loft covers the whole board with
    # margin.
    nut_skew = abs(layout['fret_zero'][0][0] - layout['fret_zero'][1][0])
    back_x = -(2.0 + nut_skew + params.board_setback)
    end_x = max(layout['last'][0][0], layout['last'][1][0]) + params.board_overhang
    front_x = end_x + 1.0

    def radius_at(x):
        r1, r2 = params.radius_start, params.radius_end
        if end_x <= 1e-9:
            return r1
        radius = r1 + (r2 - r1) * (x / end_x)
        return max(radius, params.radius_span * 1.02)

    planes = component.constructionPlanes
    created_planes = []
    created_sketches = []

    def cleanup_and_raise(message):
        for sk in created_sketches:
            try:
                sk.deleteMe()
            except Exception:
                pass
        for plane in created_planes:
            try:
                plane.deleteMe()
            except Exception:
                pass
        raise FretSlotsError(message)

    def station_plane_and_sketch(station_x):
        """Transverse plane at local x = station_x plus a sketch on it.

        The component's yZ plane is exactly perpendicular to the neck (+x),
        for fanned layouts too. The offset sign convention is not trusted:
        each candidate plane gets a sketch, and the station's crown point
        must map into it at z ≈ 0, else the other sign is tried.
        """
        crown3d = adsk.core.Point3D.create(station_x, 0.0, 0.0)
        for sign in (1.0, -1.0):
            try:
                plane_input = planes.createInput()
                plane_input.setByOffset(
                    component.yZConstructionPlane,
                    adsk.core.ValueInput.createByReal(station_x * sign))
                plane = planes.add(plane_input)
            except Exception:
                continue
            profile_sketch = component.sketches.add(plane)
            if abs(profile_sketch.modelToSketchSpace(crown3d.copy()).z) < 1e-3:
                return plane, profile_sketch, crown3d
            try:
                profile_sketch.deleteMe()
                plane.deleteMe()
            except Exception:
                pass
        cleanup_and_raise('Could not place the transverse radius planes.')

    profiles = []
    for station_x in (back_x, front_x):
        radius = radius_at(station_x)
        try:
            plane, profile_sketch, crown3d = station_plane_and_sketch(station_x)
            created_planes.append(plane)
            created_sketches.append(profile_sketch)
            profile_sketch.name = 'Radius Profile'

            up_point = crown3d.copy()
            up_point.translateBy(up)
            crown2 = profile_sketch.modelToSketchSpace(crown3d.copy())
            up2 = profile_sketch.modelToSketchSpace(up_point)
            ux, uy = fret_math.normalize(up2.x - crown2.x, up2.y - crown2.y)

            theta = math.asin(min(0.999, params.radius_span / radius))
            alpha = math.atan2(uy, ux)
            center = (crown2.x - ux * radius, crown2.y - uy * radius)
            end1 = (center[0] + radius * math.cos(alpha - theta),
                    center[1] + radius * math.sin(alpha - theta))
            end2 = (center[0] + radius * math.cos(alpha + theta),
                    center[1] + radius * math.sin(alpha + theta))

            def pt(p, lift=0.0):
                return adsk.core.Point3D.create(p[0] + ux * lift,
                                                p[1] + uy * lift, 0.0)

            cap = params.radius_span
            arcs = profile_sketch.sketchCurves.sketchArcs
            lines = profile_sketch.sketchCurves.sketchLines
            arcs.addByCenterStartSweep(pt(center), pt(end1), 2.0 * theta)
            lines.addByTwoPoints(pt(end1), pt(end1, cap))
            lines.addByTwoPoints(pt(end1, cap), pt(end2, cap))
            lines.addByTwoPoints(pt(end2, cap), pt(end2))

            if profile_sketch.profiles.count == 0:
                raise Exception('no radius profile')
            profiles.append(profile_sketch.profiles.item(0))
        except FretSlotsError:
            raise
        except Exception:
            cleanup_and_raise('Could not build the radius profile sketches:\n'
                              '{}'.format(traceback.format_exc().splitlines()[-1]))

    try:
        lofts = component.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.CutFeatureOperation)
        loft_input.loftSections.add(profiles[0])
        loft_input.loftSections.add(profiles[1])
        try:
            loft_input.participantBodies = [board]
        except Exception:
            pass
        feature = lofts.add(loft_input)
    except Exception:
        cleanup_and_raise('The radius cut failed — check that the radius is '
                          'larger than half the board width and that the board '
                          'top is still flat.')

    return feature, created_sketches, created_planes


def _draw_polyline_sketch(component, fret_zero, direction, name, point_pairs,
                          close_loop=False, construction=False):
    """Create an extra sketch on the board top plane and draw the given
    local-frame lines into it. point_pairs is a list of (start, end) local
    points, or a list of corner points when close_loop is True."""
    sketch = _create_sketch(component)
    try:
        frame = _sketch_frame(sketch, fret_zero, direction)
        sketch.isComputeDeferred = True
        try:
            lines = sketch.sketchCurves.sketchLines
            if close_loop:
                corners = [_place_point(p, frame) for p in point_pairs]
                for i in range(len(corners)):
                    line = lines.addByTwoPoints(corners[i],
                                                corners[(i + 1) % len(corners)])
                    line.isConstruction = construction
            else:
                for start, end in point_pairs:
                    line = lines.addByTwoPoints(_place_point(start, frame),
                                                _place_point(end, frame))
                    line.isConstruction = construction
        finally:
            sketch.isComputeDeferred = False
        sketch.name = name
    except Exception:
        try:
            sketch.deleteMe()
        except Exception:
            pass
        raise
    return sketch


def _draw_tuner_plan_sketch(component, params, fret_zero, direction, tuner_geo):
    """Flat-headstock (angle 0) tuner sketch on the board top plane:
    a hole circle + center point per post, and nut->post guide lines for
    pattern grids (straight-pull guides would coincide with the string
    extensions)."""
    sketch = _create_sketch(component)
    try:
        frame = _sketch_frame(sketch, fret_zero, direction)
        sketch.isComputeDeferred = True
        try:
            circles = sketch.sketchCurves.sketchCircles
            lines = sketch.sketchCurves.sketchLines
            radius = params.tuner_hole / 2.0
            for (x, y), nut_pt in zip(tuner_geo['plan_posts'],
                                      tuner_geo['nut_points']):
                center = _place_point((x, y), frame)
                circles.addByCenterRadius(center, radius)
                sketch.sketchPoints.add(center)
                if params.tuner_mode == 'pattern':
                    guide = lines.addByTwoPoints(_place_point(nut_pt, frame),
                                                 center)
                    guide.isConstruction = True
        finally:
            sketch.isComputeDeferred = False
        sketch.name = 'Tuner Layout ({} posts)'.format(params.string_count)
    except Exception:
        try:
            sketch.deleteMe()
        except Exception:
            pass
        raise
    return sketch


def _apply_tuner_plane(params, component, tuner_geo):
    """Tilted-headstock tuner geometry: offset plane face_drop below the top,
    a hinge line break_offset behind the nut datum, an angled plane hinged on
    it, and the tuner sketch drawn ON that plane in true face coordinates.

    All points live in the fretboard component's canonical frame (fret 0 at
    the origin, neck along +x, up +z). Every plane direction is verified
    with a probe point (mapped through a sketch on the candidate plane)
    instead of trusting offset/angle sign conventions — on failure this
    raises FretSlotsError rather than drawing a silently-flipped reference.
    Returns (tuner_sketch, angled_plane, hinge_sketch, offset_plane);
    offset_plane is None when face_drop is 0.
    """
    theta = params.headstock_angle
    planes = component.constructionPlanes

    created = []

    def cleanup_and_raise(message):
        for obj in reversed(created):
            try:
                obj.deleteMe()
            except Exception:
                pass
        raise FretSlotsError(message)

    # Hinge center: on the center line, break_offset behind fret 0, dropped
    # face_drop below the board top.
    hinge_center = adsk.core.Point3D.create(-params.break_offset, 0.0,
                                            -params.face_drop)

    # --- base for the hinge line: offset plane, or the top plane at drop 0.
    offset_plane = None
    hinge_sketch = None
    if params.face_drop > 1e-9:
        for sign in (-1.0, 1.0):
            try:
                plane_input = planes.createInput()
                plane_input.setByOffset(
                    component.xYConstructionPlane,
                    adsk.core.ValueInput.createByReal(params.face_drop * sign))
                candidate = planes.add(plane_input)
            except Exception:
                continue
            probe_sketch = component.sketches.add(candidate)
            if abs(probe_sketch.modelToSketchSpace(hinge_center.copy()).z) < 1e-3:
                offset_plane = candidate
                hinge_sketch = probe_sketch
                created.extend([candidate, probe_sketch])
                break
            try:
                probe_sketch.deleteMe()
                candidate.deleteMe()
            except Exception:
                pass
        if offset_plane is None:
            cleanup_and_raise('Could not place the headstock face plane '
                              'below the board top.')
    else:
        hinge_sketch = _create_sketch(component)
        created.append(hinge_sketch)

    try:
        def hinge_point(y):
            mapped = hinge_sketch.modelToSketchSpace(
                adsk.core.Point3D.create(-params.break_offset, y,
                                         -params.face_drop))
            return adsk.core.Point3D.create(mapped.x, mapped.y, 0.0)

        hinge_line = hinge_sketch.sketchCurves.sketchLines.addByTwoPoints(
            hinge_point(-params.half_span), hinge_point(params.half_span))
        hinge_line.isConstruction = True
        hinge_sketch.name = 'Headstock Hinge'
    except Exception:
        cleanup_and_raise('Could not draw the headstock hinge line:\n{}'
                          .format(traceback.format_exc().splitlines()[-1]))

    # --- angled plane hinged on that line, verified against a probe point
    # 2 cm down the face (headward and below the hinge by sin(theta)).
    face_probe = adsk.core.Point3D.create(
        -params.break_offset - math.cos(theta) * 2.0,
        0.0,
        -params.face_drop - math.sin(theta) * 2.0)

    angled_plane = None
    tuner_sketch = None
    reference_planes = ([component.xYConstructionPlane, offset_plane]
                        if offset_plane else [component.xYConstructionPlane])
    for reference in reference_planes:
        for sign in (1.0, -1.0):
            try:
                plane_input = planes.createInput()
                plane_input.setByAngle(
                    hinge_line,
                    adsk.core.ValueInput.createByReal(theta * sign),
                    reference)
                candidate = planes.add(plane_input)
            except Exception:
                continue
            probe_sketch = component.sketches.add(candidate)
            if abs(probe_sketch.modelToSketchSpace(face_probe.copy()).z) < 1e-3:
                angled_plane = candidate
                tuner_sketch = probe_sketch
                created.extend([candidate, probe_sketch])
                break
            try:
                probe_sketch.deleteMe()
                candidate.deleteMe()
            except Exception:
                pass
        if angled_plane:
            break
    if angled_plane is None:
        cleanup_and_raise('Could not tilt the headstock plane about the hinge '
                          'line — see DEV_NOTES.md (setByAngle assumptions).')

    # --- face frame inside the tuner sketch: origin at the hinge center,
    # x down the face (headward), y lateral toward the bass side. Both axes
    # are measured from mapped probe points, not assumed.
    try:
        # The lateral probe must sit ON the hinge plane (dropped like the
        # hinge center) — projecting a top-plane point onto the tilted face
        # would smear face_drop*sin(theta) into the longitudinal axis.
        lateral_probe = adsk.core.Point3D.create(-params.break_offset, 1.0,
                                                 -params.face_drop)
        origin2 = tuner_sketch.modelToSketchSpace(hinge_center.copy())
        fx2 = tuner_sketch.modelToSketchSpace(face_probe.copy())
        fy2 = tuner_sketch.modelToSketchSpace(lateral_probe)
        ex = ((fx2.x - origin2.x) / 2.0, (fx2.y - origin2.y) / 2.0)
        ey = (fy2.x - origin2.x, fy2.y - origin2.y)

        def face_point(f, y):
            return adsk.core.Point3D.create(
                origin2.x + ex[0] * f + ey[0] * y,
                origin2.y + ex[1] * f + ey[1] * y, 0.0)

        tuner_sketch.isComputeDeferred = True
        try:
            circles = tuner_sketch.sketchCurves.sketchCircles
            lines = tuner_sketch.sketchCurves.sketchLines
            radius = params.tuner_hole / 2.0
            for f, y in tuner_geo['draw_posts']:
                center = face_point(f, y)
                circles.addByCenterRadius(center, radius)
                tuner_sketch.sketchPoints.add(center)
            # Hinge reference line at f = 0, for orienting the template.
            span = max(abs(y) for _f, y in tuner_geo['draw_posts']) + 2.0
            hinge_mark = lines.addByTwoPoints(face_point(0.0, -span),
                                              face_point(0.0, span))
            hinge_mark.isConstruction = True
        finally:
            tuner_sketch.isComputeDeferred = False
        tuner_sketch.name = 'Tuner Layout ({} posts, tilted)'.format(
            params.string_count)
    except Exception:
        cleanup_and_raise('Could not draw the tuner posts on the headstock '
                          'plane:\n{}'
                          .format(traceback.format_exc().splitlines()[-1]))

    return tuner_sketch, angled_plane, hinge_sketch, offset_plane


def build_slots(params):
    """Create or rebuild the whole fretboard.

    A new layout creates a fresh component under the active component, at
    its origin: fret 0 at the origin, the neck along +x, the board top on
    the XY plane. The tapered outline is extruded into the board body, and
    the slots/nut/radius are cut into it.

    In edit mode (params.edit_sketch set) the slot sketch's curves are
    replaced in place — keeping the sketch object alive so downstream features
    (e.g. a manual Press Pull cut) can recompute — and every other object the
    add-in created for the layout (board body, cuts, radius, string/taper
    sketches, tuner chain) is recreated inside the same component.
    Raises FretSlotsError on geometric problems.
    """
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)

    # The canonical layout frame in the fretboard component's own space.
    fret_zero = adsk.core.Point3D.create(0.0, 0.0, 0.0)
    direction = adsk.core.Vector3D.create(1.0, 0.0, 0.0)

    created_new = params.edit_sketch is None
    occurrence = None
    extra_sketches = []
    board_feature = None
    radius_feature = None
    radius_sketches = []
    radius_planes = []
    tuner_sketch = None
    tuner_tooling = []   # hinge sketch (tilted headstock only)
    tuner_planes = []    # [angled plane, offset plane] — cleanup order
    cut_feature = None
    nut_cut_feature = None
    try:
        timeline_start = design.timeline.markerPosition
    except Exception:
        timeline_start = None
    if created_new:
        try:
            occurrence = design.activeComponent.occurrences.addNewComponent(
                adsk.core.Matrix3D.create())
            component = occurrence.component
        except Exception:
            raise FretSlotsError('Could not create the fretboard component:\n'
                                 '{}'.format(
                                     traceback.format_exc().splitlines()[-1]))
        sketch = _create_sketch(component)
    else:
        sketch = params.edit_sketch
        component = sketch.parentComponent
        old_metadata = _sketch_metadata(sketch)
        # Remove everything the previous run created before touching the
        # curves those features consume; all of it is recreated below.
        _delete_tracked(design, old_metadata)
        _clear_sketch_curves(sketch)

    try:
        frame = _sketch_frame(sketch, fret_zero, direction)

        layout = fret_math.slot_layout(
            params.bass_scale, params.treble_scale, params.fret_count,
            params.perpendicular_fret, params.half_span, params.slot_width,
            params.nut_slot_width)

        # The board body first: outline sketch -> extrude. Everything else
        # cuts into (or references) it.
        try:
            corners = fret_math.taper_outline(
                layout['fret_zero'], layout['bridge'], layout['last'],
                params.string_spread_nut, params.string_spread_bridge,
                params.nut_width, params.board_overhang,
                setback=params.board_setback)
        except ValueError as error:
            raise FretSlotsError(str(error))
        taper_sketch = _draw_polyline_sketch(
            component, fret_zero, direction, 'Fretboard Outline', corners,
            close_loop=True)
        extra_sketches.append(taper_sketch)
        board_feature = _extrude_board(taper_sketch, params.board_thickness)
        board = board_feature.bodies.item(0)
        try:
            board.name = 'Fretboard'
        except Exception:
            pass

        sketch.isComputeDeferred = True
        try:
            lines = sketch.sketchCurves.sketchLines
            rectangles = list(layout['slots'])
            if layout['nut']:
                rectangles.append(layout['nut'])
            for corner1, corner2, corner3 in rectangles:
                lines.addThreePointRectangle(_place_point(corner1, frame),
                                             _place_point(corner2, frame),
                                             _place_point(corner3, frame))
        finally:
            sketch.isComputeDeferred = False
        sketch.name = _sketch_name(params, 'Fret Slots')

        # The bridge mark gets its own sketch: the slot sketch is consumed
        # (and auto-hidden) by the Cut slots feature, which would hide the
        # mark with it.
        bridge_sketch = None
        if params.mark_bridge:
            bridge_sketch = _draw_polyline_sketch(
                component, fret_zero, direction, 'Bridge Mark',
                [layout['bridge']], construction=True)
            extra_sketches.append(bridge_sketch)

        # Tuner geometry first: with tuners on, the string-line head
        # extensions reach each string's own post instead of the manual
        # headstock length (which is preserved untouched for when the
        # feature is off again).
        tuner_geo = None
        if params.place_tuners:
            try:
                tuner_geo = _tuner_layout_geometry(params, layout)
            except ValueError as error:
                raise FretSlotsError('Tuner layout: {}.'.format(error))

        strings_sketch = None
        if params.draw_strings:
            head_lengths = (tuner_geo['head_lengths'] if tuner_geo
                            else params.headstock_length)
            strings = fret_math.string_layout(
                layout['fret_zero'], layout['bridge'], params.string_count,
                params.string_spread_nut, params.string_spread_bridge,
                head_lengths)
            strings_sketch = _draw_polyline_sketch(
                component, fret_zero, direction,
                'String Layout ({} strings)'.format(params.string_count),
                strings)
            extra_sketches.append(strings_sketch)

        if tuner_geo:
            if tuner_geo['tilted']:
                (tuner_sketch, angled_plane, hinge_sketch,
                 offset_plane) = _apply_tuner_plane(params, component,
                                                    tuner_geo)
                tuner_tooling.append(hinge_sketch)
                tuner_planes.append(angled_plane)
                if offset_plane:
                    tuner_planes.append(offset_plane)
            else:
                tuner_sketch = _draw_tuner_plan_sketch(
                    component, params, fret_zero, direction, tuner_geo)
            extra_sketches.append(tuner_sketch)

        if params.radius_mode:
            radius_feature, radius_sketches, radius_planes = _apply_radius(
                params, component, layout, board)

        if params.cut_depth:
            all_profiles = adsk.core.ObjectCollection.create()
            for profile in sketch.profiles:
                all_profiles.add(profile)

            fret_area = params.slot_width * params.half_span * 2.0
            nut_area = ((params.nut_slot_width or 0.0)
                        * params.half_span * 2.0)
            split_nut = (params.nut_slot_width and params.nut_slot_depth
                         and nut_area > fret_area * 1.5)
            if split_nut:
                fret_profiles, nut_profiles = _partition_slot_profiles(
                    sketch, fret_area, nut_area)
                cut_feature = _cut_profiles(sketch, fret_profiles,
                                            params.cut_depth, board,
                                            'fret slots')
                if nut_profiles.count > 0:
                    nut_cut_feature = _cut_profiles(sketch, nut_profiles,
                                                    params.nut_slot_depth,
                                                    board, 'nut slot')
            else:
                # Nut and fret widths too similar to tell apart (or no nut):
                # cut everything at the fret slot depth.
                cut_feature = _cut_profiles(sketch, all_profiles,
                                            params.cut_depth, board, 'slots')

        # Lock every created curve so the sketches are fully defined, then
        # tidy the browser: only the working references (string layout,
        # bridge mark, tuner layout) stay visible. The outline sketch became
        # the board body and the tooling exists as solid geometry — but
        # without a slot cut the slot sketch stays visible, or there would
        # be nothing to see of the layout. The slot sketch's visibility is
        # set BOTH ways: an edit may have inherited a hidden sketch from a
        # previous run whose cut is now unchecked.
        for created_sketch in ([sketch] + extra_sketches + radius_sketches
                               + tuner_tooling):
            _fix_all_curves(created_sketch)
        to_hide = (list(radius_sketches) + list(radius_planes)
                   + list(tuner_tooling) + list(tuner_planes)
                   + [taper_sketch])
        if cut_feature:
            to_hide.append(sketch)
        for visible_object in to_hide:
            try:
                visible_object.isLightBulbOn = False
            except Exception:
                pass
        if not cut_feature:
            try:
                sketch.isLightBulbOn = True
            except Exception:
                pass

        tuner_metadata = {
            'place_tuners': params.place_tuners,
            'tuner_mode': getattr(params, 'tuner_mode', None),
            'tuner_bass_count': getattr(params, 'tuner_bass_count', None),
            'tuner_reversed': getattr(params, 'tuner_reversed', False),
            'headstock_angle_rad': getattr(params, 'headstock_angle', 0.0),
            'face_drop_cm': getattr(params, 'face_drop', None),
            'break_offset_cm': getattr(params, 'break_offset', None),
            'tuner_first_cm': getattr(params, 'tuner_first', None),
            'tuner_spacing_cm': getattr(params, 'tuner_spacing', None),
            'pattern_first_cm': getattr(params, 'pattern_first', None),
            'pattern_pitch_cm': getattr(params, 'pattern_pitch', None),
            'pattern_row_offset_cm': getattr(params, 'pattern_row_offset', None),
            'pattern_row_slant_cm': getattr(params, 'pattern_row_slant', None),
            'tuner_hole_cm': getattr(params, 'tuner_hole', None),
            'tuner_clearance_cm': getattr(params, 'tuner_clearance', None),
            'tuners_token': _entity_token(tuner_sketch) if tuner_sketch else '',
            'tuner_hinge_token': (_entity_token(tuner_tooling[0])
                                  if tuner_tooling else ''),
            'tuner_angled_plane_token': (_entity_token(tuner_planes[0])
                                         if tuner_planes else ''),
            'tuner_offset_plane_token': (_entity_token(tuner_planes[1])
                                         if len(tuner_planes) > 1 else ''),
        }
        metadata = json.dumps({
            'version': 7,
            **tuner_metadata,
            'scale_cm': (params.bass_scale + params.treble_scale) / 2.0,
            'bass_scale_cm': params.bass_scale,
            'treble_scale_cm': params.treble_scale,
            'multiscale': params.multiscale,
            'perpendicular_fret': params.perpendicular_fret,
            'fret_count': params.fret_count,
            'slot_width_cm': params.slot_width,
            'slot_length_cm': params.half_span * 2.0,
            'nut_slot_width_cm': params.nut_slot_width,
            'nut_slot_depth_cm': params.nut_slot_depth,
            'board_thickness_cm': params.board_thickness,
            'board_setback_cm': params.board_setback,
            'cut_depth_cm': params.cut_depth,
            'mark_bridge': params.mark_bridge,
            'draw_strings': params.draw_strings,
            'string_count': params.string_count,
            'string_spread_nut_cm': params.string_spread_nut,
            'string_spread_bridge_cm': params.string_spread_bridge,
            'headstock_length_cm': params.headstock_length,
            'nut_width_cm': params.nut_width,
            'board_overhang_cm': params.board_overhang,
            'radius_mode': params.radius_mode,
            'radius_start_cm': params.radius_start,
            'radius_end_cm': params.radius_end,
            'board_token': _entity_token(board_feature),
            'cut_token': _entity_token(cut_feature) if cut_feature else '',
            'nut_cut_token': _entity_token(nut_cut_feature) if nut_cut_feature else '',
            'bridge_token': _entity_token(bridge_sketch) if bridge_sketch else '',
            'strings_token': _entity_token(strings_sketch) if strings_sketch else '',
            'taper_token': _entity_token(taper_sketch) if taper_sketch else '',
            'radius_feature_token': _entity_token(radius_feature) if radius_feature else '',
            'radius_sketch_tokens': [_entity_token(s) for s in radius_sketches],
            'radius_plane_tokens': [_entity_token(p) for p in radius_planes],
        })
        sketch.attributes.add(ATTRIBUTE_GROUP, ATTRIBUTE_NAME, metadata)

        if created_new:
            try:
                component.name = _sketch_name(params, 'Fretboard')
            except Exception:
                pass  # e.g. a name collision — the default name stays

        # Wrap everything this run created in one timeline group (new layouts
        # only — edited features are appended at the end of the timeline,
        # away from the original sketch, so they cannot share a group).
        if created_new and timeline_start is not None:
            try:
                timeline = design.timeline
                end_index = timeline.markerPosition - 1
                if end_index > timeline_start:
                    group = timeline.timelineGroups.add(timeline_start, end_index)
                    group.name = sketch.name
            except Exception:
                pass
    except Exception:
        # Never leave half-built geometry behind. A new layout lives entirely
        # in the component this run created — removing its occurrence removes
        # everything with it. On edit, remove the recreated pieces in
        # feature-before-consumed-object order (the board extrude before the
        # outline sketch it consumes, the tuner sketch — inside
        # extra_sketches — before the angled plane, then the hinge sketch,
        # then the offset plane, mirroring _delete_tracked); the edited slot
        # sketch is the user's existing object — leave it for undo instead
        # of deleting it.
        if created_new:
            try:
                if occurrence and occurrence.isValid:
                    occurrence.deleteMe()
            except Exception:
                pass
        else:
            cleanup = ([nut_cut_feature, cut_feature, radius_feature]
                       + radius_sketches + radius_planes + [board_feature]
                       + extra_sketches
                       + tuner_planes[:1] + tuner_tooling + tuner_planes[1:])
            for obj in cleanup:
                if obj is None:
                    continue
                try:
                    if obj.isValid:
                        obj.deleteMe()
                except Exception:
                    pass
        raise
    return sketch


class CreateFretSlotsCommand(Fusion360CommandBase):
    def __init__(self, cmd_def, debug):
        super().__init__(cmd_def, debug)
        self._preview_ok = False
        self._edit_sketches = []
        # Values of the last run, as loaded when the dialog opened; kept so
        # switching the Start-from dropdown back to "last used" can restore
        # them after a defaults reset or an edit prefill.
        self._settings = dict(DEFAULTS)

    def _edit_sketch_from_inputs(self, inputs):
        dropdown = inputs.itemById('edit_target')
        if not dropdown:
            return None
        item = dropdown.selectedItem
        if not item or item.index < len(NEW_LAYOUT_LABELS):
            return None
        index = item.index - len(NEW_LAYOUT_LABELS)
        if index >= len(self._edit_sketches):
            return None
        sketch = self._edit_sketches[index]
        return sketch if sketch and sketch.isValid else None

    def _new_layout_settings(self, inputs):
        """Which values a new fretboard starts from: defaults or last used."""
        dropdown = inputs.itemById('edit_target')
        item = dropdown.selectedItem if dropdown else None
        if item and item.name == CREATE_DEFAULT_LABEL:
            return DEFAULTS
        return self._settings

    def _apply_settings(self, inputs, settings):
        """Refill the whole dialog from a settings dict.

        Used when the Start-from dropdown switches between the defaults and
        the last-used values (on_create builds the inputs from the same dict
        instead — the inputs do not exist yet at that point).
        """
        for key, input_id in EXPRESSION_INPUTS:
            command_input = inputs.itemById(input_id)
            if not command_input:
                continue
            # A stored expression can be invalid in this document (it may have
            # referenced a user parameter of another design); fall back to the
            # default rather than leaving the field red.
            for expression in (settings.get(key), DEFAULTS[key]):
                if not isinstance(expression, str):
                    continue
                try:
                    command_input.expression = expression
                    if command_input.isValidExpression:
                        break
                except Exception:
                    pass

        for key, input_id, low, high in SPINNER_INPUTS:
            spinner = inputs.itemById(input_id)
            stored = settings.get(key, DEFAULTS[key])
            if spinner and isinstance(stored, int) and low <= stored <= high:
                try:
                    spinner.value = stored
                except Exception:
                    pass

        for key, input_id in CHECKBOX_INPUTS:
            checkbox = inputs.itemById(input_id)
            if checkbox:
                checkbox.value = bool(settings.get(key, DEFAULTS[key]))

        for key, input_id in DROPDOWN_INPUTS:
            dropdown = inputs.itemById(input_id)
            if not dropdown:
                continue
            name = settings.get(key, DEFAULTS[key])
            # Only select the target item — clearing first would leave the
            # dropdown transiently empty and break the template's get_inputs.
            for i in range(dropdown.listItems.count):
                item = dropdown.listItems.item(i)
                if item.name == name:
                    item.isSelected = True
                    break

        self._apply_group_state(inputs, settings)
        self._apply_nut_cut_visibility(inputs,
                                       bool(settings.get('create_nut_slot')),
                                       bool(settings.get('cut_slots')))
        self._apply_multiscale_visibility(inputs, bool(settings.get('multiscale')))
        self._apply_radius_visibility(inputs, settings.get('radius_mode'))
        self._apply_tuner_visibility(inputs)

    @staticmethod
    def _apply_group_state(inputs, settings):
        for group_id, key in GROUP_EXPANDERS:
            group = inputs.itemById(group_id)
            if not group:
                continue
            expanded = (settings.get(key) != 'No radius' if key == 'radius_mode'
                        else bool(settings.get(key)))
            try:
                group.isExpanded = expanded
            except Exception:
                pass

    def _prefill_from_sketch(self, inputs, sketch):
        """Load stored parameters of an existing fret layout sketch."""
        metadata = _sketch_metadata(sketch)

        def set_value(input_id, key):
            value_input = inputs.itemById(input_id)
            stored = metadata.get(key)
            if value_input and isinstance(stored, (int, float)) and stored > 0:
                try:
                    value_input.value = float(stored)
                except Exception:
                    pass

        def set_check(input_id, key, default=False):
            checkbox = inputs.itemById(input_id)
            if checkbox:
                checkbox.value = bool(metadata.get(key, default))
            return bool(metadata.get(key, default))

        def set_spinner(input_id, key, low, high):
            spinner = inputs.itemById(input_id)
            stored = metadata.get(key)
            if spinner and isinstance(stored, int) and low <= stored <= high:
                spinner.value = stored

        multiscale = set_check('multiscale', 'multiscale')
        if multiscale:
            set_value('bass_scale', 'bass_scale_cm')
            set_value('treble_scale', 'treble_scale_cm')
            set_spinner('perpendicular_fret', 'perpendicular_fret', 0, 36)
        else:
            set_value('scale_length', 'scale_cm')
        self._apply_multiscale_visibility(inputs, multiscale)

        set_spinner('fret_count', 'fret_count', 1, 36)
        set_value('slot_width', 'slot_width_cm')
        set_value('slot_length', 'slot_length_cm')

        nut_width = metadata.get('nut_slot_width_cm')
        has_nut = isinstance(nut_width, (int, float)) and nut_width > 0
        checkbox = inputs.itemById('create_nut_slot')
        if checkbox:
            checkbox.value = has_nut
        if has_nut:
            set_value('nut_slot_width', 'nut_slot_width_cm')
            set_value('nut_slot_depth', 'nut_slot_depth_cm')

        set_value('board_thickness', 'board_thickness_cm')
        # Zero is a legitimate setback, so this skips set_value's "> 0" guard.
        setback_input = inputs.itemById('board_setback')
        stored_setback = metadata.get('board_setback_cm')
        if setback_input and isinstance(stored_setback, (int, float)):
            try:
                setback_input.value = float(stored_setback)
            except Exception:
                pass

        cut_depth = metadata.get('cut_depth_cm')
        has_cut = isinstance(cut_depth, (int, float)) and cut_depth > 0
        cut_checkbox = inputs.itemById('cut_slots')
        if cut_checkbox:
            cut_checkbox.value = has_cut
        if has_cut:
            set_value('slot_depth', 'cut_depth_cm')
        self._apply_nut_cut_visibility(inputs, has_nut, has_cut)

        set_check('mark_bridge', 'mark_bridge')
        set_check('draw_strings', 'draw_strings')
        set_spinner('string_count', 'string_count', 1, 12)
        set_value('string_spread_nut', 'string_spread_nut_cm')
        set_value('string_spread_bridge', 'string_spread_bridge_cm')
        set_value('headstock_length', 'headstock_length_cm')
        set_value('nut_width', 'nut_width_cm')
        set_value('board_overhang', 'board_overhang_cm')

        def select_dropdown_item(input_id, name):
            dropdown = inputs.itemById(input_id)
            if not dropdown:
                return
            # Only select the target item — clearing first would leave the
            # dropdown transiently empty and break get_inputs (see radius).
            for i in range(dropdown.listItems.count):
                item = dropdown.listItems.item(i)
                if item.name == name:
                    item.isSelected = True
                    break

        set_check('place_tuners', 'place_tuners')
        select_dropdown_item('tuner_mode',
                             'Pattern (two rows)'
                             if metadata.get('tuner_mode') == 'pattern'
                             else 'Straight pull')
        set_spinner('tuner_bass_count', 'tuner_bass_count', 0, 12)
        set_check('tuner_reversed', 'tuner_reversed')
        # Zero (and for offsets, zero-adjacent) values are legitimate here, so
        # these skip set_value's "> 0" guard — same pattern as board_setback.
        for input_id, key in (('headstock_angle', 'headstock_angle_rad'),
                              ('face_drop', 'face_drop_cm'),
                              ('break_offset', 'break_offset_cm'),
                              ('pattern_row_offset', 'pattern_row_offset_cm'),
                              ('pattern_row_slant', 'pattern_row_slant_cm'),
                              ('tuner_clearance', 'tuner_clearance_cm')):
            command_input = inputs.itemById(input_id)
            stored = metadata.get(key)
            if command_input and isinstance(stored, (int, float)):
                try:
                    command_input.value = float(stored)
                except Exception:
                    pass
        set_value('tuner_first', 'tuner_first_cm')
        set_value('tuner_spacing', 'tuner_spacing_cm')
        set_value('pattern_first', 'pattern_first_cm')
        set_value('pattern_pitch', 'pattern_pitch_cm')
        stored_hole = metadata.get('tuner_hole_cm')
        if isinstance(stored_hole, (int, float)) and stored_hole > 0:
            preset_name = 'Custom'
            for name, diameter in HOLE_PRESETS:
                if diameter is not None and abs(diameter - stored_hole) < 1e-6:
                    preset_name = name
                    break
            select_dropdown_item('tuner_hole_preset', preset_name)
            if preset_name == 'Custom':
                set_value('tuner_hole_custom', 'tuner_hole_cm')
        self._apply_tuner_visibility(inputs)

        mode = metadata.get('radius_mode')
        mode_name = ('Single radius' if mode == 'single'
                     else 'Compound radius' if mode == 'compound'
                     else 'No radius')
        dropdown = inputs.itemById('radius_mode')
        if dropdown:
            # Only select the target item — a dropdown deselects the rest by
            # itself, and clearing first would leave it transiently empty
            # (which breaks the template's get_inputs on the next event).
            for i in range(dropdown.listItems.count):
                item = dropdown.listItems.item(i)
                if item.name == mode_name:
                    item.isSelected = True
                    break
        set_value('radius_start', 'radius_start_cm')
        set_value('radius_end', 'radius_end_cm')
        self._apply_radius_visibility(inputs, mode_name)

    @staticmethod
    def _apply_nut_cut_visibility(inputs, nut_on, cut_on):
        for input_id, visible in (('nut_slot_width', nut_on),
                                  ('nut_slot_depth', nut_on and cut_on),
                                  ('slot_depth', cut_on)):
            command_input = inputs.itemById(input_id)
            if command_input:
                command_input.isVisible = visible

    @staticmethod
    def _apply_multiscale_visibility(inputs, multiscale):
        for input_id, visible in (('scale_length', not multiscale),
                                  ('bass_scale', multiscale),
                                  ('treble_scale', multiscale),
                                  ('perpendicular_fret', multiscale)):
            command_input = inputs.itemById(input_id)
            if command_input:
                command_input.isVisible = visible

    @staticmethod
    def _apply_tuner_visibility(inputs):
        checkbox = inputs.itemById('place_tuners')
        on = bool(checkbox.value) if checkbox else False
        dropdown = inputs.itemById('tuner_mode')
        mode = (dropdown.selectedItem.name if dropdown and dropdown.selectedItem
                else TUNER_MODES[0])
        straight = mode == TUNER_MODES[0]
        hole_dropdown = inputs.itemById('tuner_hole_preset')
        custom_hole = bool(hole_dropdown and hole_dropdown.selectedItem
                           and hole_dropdown.selectedItem.name == 'Custom')
        for input_id, visible in (
            ('tuner_mode', on),
            ('tuner_bass_count', on),
            ('tuner_reversed', on),
            ('headstock_angle', on),
            ('break_offset', on),
            ('face_drop', on),
            ('tuner_first', on and straight),
            ('tuner_spacing', on and straight),
            ('pattern_first', on and not straight),
            ('pattern_pitch', on and not straight),
            ('pattern_row_offset', on and not straight),
            ('pattern_row_slant', on and not straight),
            ('tuner_hole_preset', on),
            ('tuner_hole_custom', on and custom_hole),
            ('tuner_clearance', on),
            # The manual head-line length is superseded (per string) while
            # the tuner feature is on; its stored value is preserved.
            ('headstock_length', not on),
        ):
            command_input = inputs.itemById(input_id)
            if command_input:
                command_input.isVisible = visible

    @staticmethod
    def _apply_radius_visibility(inputs, mode_name):
        start_input = inputs.itemById('radius_start')
        if start_input:
            start_input.isVisible = mode_name != 'No radius'
        end_input = inputs.itemById('radius_end')
        if end_input:
            end_input.isVisible = mode_name == 'Compound radius'

    def on_create(self, command, inputs):
        self._preview_ok = False
        self._edit_sketches = []

        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Open a design in the Design workspace first.')
            return

        try:
            command.setDialogInitialSize(400, 620)
        except Exception:
            pass

        settings = load_settings()
        self._settings = settings
        units = design.unitsManager.defaultLengthUnits

        self._edit_sketches = _find_fret_sketches(design)
        edit_dropdown = inputs.addDropDownCommandInput(
            'edit_target', 'Start from',
            adsk.core.DropDownStyles.TextListDropDownStyle)
        for index, label in enumerate(NEW_LAYOUT_LABELS):
            edit_dropdown.listItems.add(label, index == 0, '')
        for sketch in self._edit_sketches:
            edit_dropdown.listItems.add(sketch.name, False, '')
        edit_dropdown.tooltip = (
            'Which values this dialog starts with. "Last used values" repeats '
            'your previous run; "Default values" resets every field to the '
            'add-in defaults for a fresh design. Picking an existing layout '
            'of this document loads its parameters back and rebuilds it in '
            'place on OK — switch back to a New entry to build another '
            'fretboard instead.')

        def value_input(container, input_id, label, expr_key):
            # A stored expression can be invalid in this document (e.g. it
            # referenced a user parameter of another design); fall back to the
            # default instead of aborting the whole dialog.
            for expression in (settings[expr_key], DEFAULTS[expr_key]):
                try:
                    container.addValueInput(input_id, label, units,
                                            adsk.core.ValueInput.createByString(expression))
                    return
                except Exception:
                    if inputs.itemById(input_id):
                        return

        value_input(inputs, 'scale_length', 'Scale length', 'scale_length_expr')
        inputs.addIntegerSpinnerCommandInput(
            'fret_count', 'Number of frets', 1, 36, 1, int(settings['fret_count']))
        value_input(inputs, 'slot_width', 'Fret slot width', 'slot_width_expr')
        value_input(inputs, 'slot_length', 'Fret slot length', 'slot_length_expr')

        nut_on = bool(settings['create_nut_slot'])
        cut_on = bool(settings['cut_slots'])

        inputs.addBoolValueInput('create_nut_slot', 'Create nut slot', True, '',
                                 nut_on)
        value_input(inputs, 'nut_slot_width', 'Nut slot width', 'nut_slot_width_expr')
        value_input(inputs, 'nut_slot_depth', 'Nut slot depth', 'nut_slot_depth_expr')
        nut_depth_input = inputs.itemById('nut_slot_depth')
        if nut_depth_input:
            nut_depth_input.tooltip = ('Depth of the nut seat cut — usually '
                                       'shallower than the fret slots.')

        inputs.addBoolValueInput('cut_slots', 'Cut slots (Push/Pull)', True, '',
                                 cut_on)
        value_input(inputs, 'slot_depth', 'Slot depth', 'slot_depth_expr')
        self._apply_nut_cut_visibility(inputs, nut_on, cut_on)

        bridge_checkbox = inputs.addBoolValueInput(
            'mark_bridge', 'Mark bridge position', True, '',
            bool(settings['mark_bridge']))
        bridge_checkbox.tooltip = (
            'Draw a construction line across the neck at the full scale '
            'length from fret 0 — the theoretical saddle contact point. '
            'It is a reference only: it is never selected or cut.')

        board_group = inputs.addGroupCommandInput('grp_board', 'Fretboard body')
        board_group.isExpanded = True
        bg = board_group.children
        value_input(bg, 'board_thickness', 'Board thickness',
                    'board_thickness_expr')
        thickness_input = inputs.itemById('board_thickness')
        if thickness_input:
            thickness_input.tooltip = (
                'Thickness of the created board body. The top face sits on '
                'the XY plane; slot and radius depths are measured down '
                'from it.')
        value_input(bg, 'board_setback', 'Board start behind nut',
                    'board_setback_expr')
        setback_input = inputs.itemById('board_setback')
        if setback_input:
            setback_input.tooltip = (
                'How far the board front edge extends behind fret 0 (toward '
                'the headstock). 0 starts the board exactly at fret 0 (the '
                'nut sits against its end face); set it to at least the nut '
                'slot width when the nut sits in a slot inside the board.')
        value_input(bg, 'nut_width', 'Nut width', 'nut_width_expr')
        value_input(bg, 'board_overhang', 'Board end past last fret',
                    'board_overhang_expr')

        multiscale_group = inputs.addGroupCommandInput(
            'grp_multiscale', 'Multi-scale (fanned frets)')
        multiscale_group.isExpanded = bool(settings['multiscale'])
        ms_children = multiscale_group.children
        ms_children.addBoolValueInput('multiscale', 'Multi-scale', True, '',
                                      bool(settings['multiscale']))
        value_input(ms_children, 'bass_scale', 'Bass side scale', 'bass_scale_expr')
        value_input(ms_children, 'treble_scale', 'Treble side scale', 'treble_scale_expr')
        ms_children.addIntegerSpinnerCommandInput(
            'perpendicular_fret', 'Perpendicular fret', 0, 36, 1,
            int(settings['perpendicular_fret']))
        self._apply_multiscale_visibility(inputs, bool(settings['multiscale']))

        strings_group = inputs.addGroupCommandInput(
            'grp_strings', 'String layout')
        strings_group.isExpanded = bool(settings['draw_strings'])
        sg = strings_group.children
        sg.addBoolValueInput('draw_strings', 'Draw string lines', True, '',
                             bool(settings['draw_strings']))
        sg.addIntegerSpinnerCommandInput(
            'string_count', 'Number of strings', 1, 12, 1,
            int(settings['string_count']))
        value_input(sg, 'string_spread_nut', 'String spread at nut',
                    'string_spread_nut_expr')
        value_input(sg, 'string_spread_bridge', 'String spread at bridge',
                    'string_spread_bridge_expr')
        value_input(sg, 'headstock_length', 'Headstock line length',
                    'headstock_length_expr')

        radius_group = inputs.addGroupCommandInput('grp_radius', 'Fretboard radius')
        radius_group.isExpanded = settings['radius_mode'] != 'No radius'
        rg = radius_group.children
        radius_dropdown = rg.addDropDownCommandInput(
            'radius_mode', 'Radius',
            adsk.core.DropDownStyles.TextListDropDownStyle)
        for mode in RADIUS_MODES:
            radius_dropdown.listItems.add(mode, mode == settings['radius_mode'], '')
        value_input(rg, 'radius_start', 'Radius at nut', 'radius_start_expr')
        value_input(rg, 'radius_end', 'Radius at board end', 'radius_end_expr')
        self._apply_radius_visibility(inputs, settings['radius_mode'])

        def angle_input(container, input_id, label, expr_key):
            # Same fallback dance as value_input, but in degree units (the
            # length-only value_input cannot host an angle).
            for expression in (settings[expr_key], DEFAULTS[expr_key]):
                try:
                    container.addValueInput(
                        input_id, label, 'deg',
                        adsk.core.ValueInput.createByString(expression))
                    return
                except Exception:
                    if inputs.itemById(input_id):
                        return

        hardware_group = inputs.addGroupCommandInput('grp_hardware', 'Hardware')
        hardware_group.isExpanded = bool(settings['place_tuners'])
        hg = hardware_group.children
        tuners_checkbox = hg.addBoolValueInput(
            'place_tuners', 'Tuner layout', True, '',
            bool(settings['place_tuners']))
        tuners_checkbox.tooltip = (
            'Place tuner post positions: hole circles and center points, as '
            'a reference sketch (no cutting). Straight pull puts each post '
            'on its own string line; Pattern uses fixed rows the strings '
            'angle toward (classic 3+3). See HARDWARE_RESEARCH.md.')

        mode_dropdown = hg.addDropDownCommandInput(
            'tuner_mode', 'Placement',
            adsk.core.DropDownStyles.TextListDropDownStyle)
        for mode in TUNER_MODES:
            mode_dropdown.listItems.add(mode, mode == settings['tuner_mode'], '')
        mode_dropdown.tooltip = (
            'Straight pull: posts sit ON the extended string lines, distances '
            'are PLAN (top view) values along the neck. Pattern: two fixed '
            'rows parallel to the center line, distances are measured along '
            'the wood surface (template-true).')

        hg.addIntegerSpinnerCommandInput(
            'tuner_bass_count', 'Bass-side posts', 0, 12, 1,
            int(settings['tuner_bass_count']))
        bass_spinner = inputs.itemById('tuner_bass_count')
        if bass_spinner:
            bass_spinner.tooltip = (
                'How many posts on the bass row; the rest go to the treble '
                'row. 6 strings: 6 = inline, 3 = 3+3, 4 = 4+2.')

        hg.addBoolValueInput('tuner_reversed', 'Reversed headstock', True, '',
                             bool(settings['tuner_reversed']))
        reversed_checkbox = inputs.itemById('tuner_reversed')
        if reversed_checkbox:
            reversed_checkbox.tooltip = (
                'Mirror the headstock: the nearest post moves to the '
                'opposite outer string and the rows swap sides (a reversed '
                'inline puts the low E farthest). No-op for a symmetric '
                '3+3 pattern. This is NOT a left-handed layout.')

        angle_input(hg, 'headstock_angle', 'Headstock angle',
                    'headstock_angle_expr')
        angle_input_ref = inputs.itemById('headstock_angle')
        if angle_input_ref:
            angle_input_ref.tooltip = (
                '0 = flat (Fender-style) headstock: posts are drawn on the '
                'fretboard plane. Tilted (common: 10 PRS, 14, 17 Gibson): '
                'posts are drawn on a tilted construction plane in TRUE face '
                'distances — drill perpendicular to that face. Single-scale '
                'layouts only.')
        value_input(hg, 'break_offset', 'Break line behind nut',
                    'break_offset_expr')
        break_input = inputs.itemById('break_offset')
        if break_input:
            break_input.tooltip = (
                'Where the headstock face starts tilting, measured behind '
                'fret 0 (plan view). Set it to at least your nut slot width '
                '(default 3.5 mm suits a typical nut); scarf joints break '
                'farther out. Used only when the angle is > 0.')
        value_input(hg, 'face_drop', 'Face drop below top', 'face_drop_expr')
        drop_input = inputs.itemById('face_drop')
        if drop_input:
            drop_input.tooltip = (
                'How far below the fretboard TOP the headstock face plane '
                'sits at the break line (about the fretboard thickness). '
                'Used only when the angle is > 0. Note: a ruler hooked where '
                'the nut meets the face reads about face_drop*sin(angle) off '
                'this sketch origin.')

        value_input(hg, 'tuner_first', 'First post from nut', 'tuner_first_expr')
        first_input = inputs.itemById('tuner_first')
        if first_input:
            first_input.tooltip = (
                'Plan-view distance from fret 0 to the nearest post, along '
                'the neck. 41.9 mm is the Fender-documented 1.650" (its '
                'exact nut reference edge is unverified — adjust by the nut '
                'thickness if your drawing measures from the back edge).')
        value_input(hg, 'tuner_spacing', 'Post spacing (along neck)',
                    'tuner_spacing_expr')
        spacing_input = inputs.itemById('tuner_spacing')
        if spacing_input:
            spacing_input.tooltip = (
                'Plan-view distance between consecutive post stations. '
                '23.3 mm = Fender 0.919"; vintage Kluson rows want 23.8 mm '
                '(15/16"), modern retrofits 25.4 mm (1"). With a split '
                '(3+3, 4+2) the stations interleave between the two rows so '
                'converging inner strings never collide.')

        value_input(hg, 'pattern_first', 'First post from nut (surface)',
                    'pattern_first_expr')
        value_input(hg, 'pattern_pitch', 'Post pitch per side',
                    'pattern_pitch_expr')
        pitch_input = inputs.itemById('pattern_pitch')
        if pitch_input:
            pitch_input.tooltip = ('35 mm is the canonical Kluson/Waverly '
                                   '3+3 spacing, electric and acoustic.')
        value_input(hg, 'pattern_row_offset', 'Row offset from center',
                    'pattern_row_offset_expr')
        row_input = inputs.itemById('pattern_row_offset')
        if row_input:
            row_input.tooltip = ('Lateral distance of each post row from the '
                                 'neck center line, at the first post.')
        value_input(hg, 'pattern_row_slant', 'Row slant per station',
                    'pattern_row_slant_expr')
        slant_input = inputs.itemById('pattern_row_slant')
        if slant_input:
            slant_input.tooltip = (
                'How much each row steps toward the center line per station. '
                '0 = rows parallel to the neck (Gibson 3+3). 7.14 mm (0.281") '
                'per 23.3 mm pitch reproduces Fender\'s 17-degree inline row.')

        hole_dropdown = hg.addDropDownCommandInput(
            'tuner_hole_preset', 'Post hole',
            adsk.core.DropDownStyles.TextListDropDownStyle)
        for name, _diameter in HOLE_PRESETS:
            hole_dropdown.listItems.add(name, name == settings['tuner_hole_preset'], '')
        value_input(hg, 'tuner_hole_custom', 'Hole diameter', 'tuner_hole_expr')
        value_input(hg, 'tuner_clearance', 'Housing clearance margin',
                    'tuner_clearance_expr')
        clearance_input = inputs.itemById('tuner_clearance')
        if clearance_input:
            clearance_input.tooltip = (
                'Warn when two post centers are closer than hole diameter + '
                'this margin (tuner housings/buttons collide). 8 mm suits '
                'typical sealed housings; 0 disables the extra margin.')

        bridge_hw_checkbox = hg.addBoolValueInput(
            'place_bridge', 'Bridge hardware (coming soon)', True, '', False)
        bridge_hw_checkbox.isEnabled = False
        bridge_hw_checkbox.tooltip = (
            'Planned: per-string compensated saddle points and mounting '
            'footprint presets at the bridge mark — see HARDWARE_RESEARCH.md.')
        self._apply_tuner_visibility(inputs)

        inputs.addTextBoxCommandInput(
            'info_box', 'Info',
            'Set the parameters — OK creates the fretboard as a new '
            'component (fret 0 at the origin, neck along +X).',
            8, True)

    def on_input_changed(self, command_, command_inputs, changed_input, input_values):
        if changed_input.id == 'info_box':
            return

        if changed_input.id == 'edit_target':
            sketch = self._edit_sketch_from_inputs(command_inputs)
            if sketch:
                self._prefill_from_sketch(command_inputs, sketch)
            else:
                # A New entry: refill from its source, so "default values"
                # really is a clean slate and either New entry undoes the
                # prefill left behind by an edit target.
                self._apply_settings(command_inputs,
                                     self._new_layout_settings(command_inputs))

        if changed_input.id in ('create_nut_slot', 'cut_slots'):
            nut_checkbox = command_inputs.itemById('create_nut_slot')
            cut_checkbox = command_inputs.itemById('cut_slots')
            self._apply_nut_cut_visibility(
                command_inputs,
                bool(nut_checkbox.value) if nut_checkbox else False,
                bool(cut_checkbox.value) if cut_checkbox else False)

        if changed_input.id == 'multiscale':
            self._apply_multiscale_visibility(command_inputs, changed_input.value)

        if changed_input.id == 'radius_mode':
            item = changed_input.selectedItem
            self._apply_radius_visibility(command_inputs,
                                          item.name if item else 'No radius')

        if changed_input.id in ('place_tuners', 'tuner_mode',
                                'tuner_hole_preset'):
            self._apply_tuner_visibility(command_inputs)

        info = command_inputs.itemById('info_box')
        if info:
            _, message, _ = validate_and_compute(
                command_inputs, self._edit_sketch_from_inputs(command_inputs))
            if info.text != message:
                info.text = message

    def on_preview(self, command, inputs, args, input_values):
        self._preview_ok = False
        ok, message, params = validate_and_compute(
            inputs, self._edit_sketch_from_inputs(inputs))
        if not ok:
            return
        try:
            build_slots(params)
            args.isValidResult = True
            self._preview_ok = True
        except FretSlotsError as error:
            message = str(error)
            info = inputs.itemById('info_box')
            if info and info.text != message:
                info.text = message
        except Exception:
            # Never let an unexpected error escape to the base handler — it
            # would raise a message box on every input change. Report in the
            # info box instead.
            message = ('Preview failed: {}'
                       .format(traceback.format_exc().splitlines()[-1]))
            info = inputs.itemById('info_box')
            if info and info.text != message:
                info.text = message

    def on_execute(self, command, inputs, args, input_values):
        # When the preview succeeded, Fusion keeps it as the result and this
        # event is skipped; this is only the fallback path.
        if self._preview_ok:
            return
        if inputs.count == 0:
            return  # on_create bailed out (no active design)

        app = adsk.core.Application.get()
        ui = app.userInterface
        ok, message, params = validate_and_compute(
            inputs, self._edit_sketch_from_inputs(inputs))
        if not ok:
            ui.messageBox('Cannot create the fretboard:\n\n{}'.format(message))
            return
        try:
            build_slots(params)
        except FretSlotsError as error:
            ui.messageBox('Cannot create the fretboard:\n\n{}'.format(error))
        except Exception:
            ui.messageBox('Create Fretboard failed:\n{}'.format(traceback.format_exc()))

    def on_destroy(self, command, inputs, reason, input_values):
        if reason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
            return
        # info_box is the last input on_create adds; without it the dialog was
        # never fully built (no active design, or on_create failed part-way).
        # Saving from a crippled dialog would overwrite the stored settings
        # with defaults.
        if not inputs.itemById('info_box'):
            return

        # Reload rather than reuse self._settings: this keeps the keys the
        # dialog does not own (buttons_promoted) at their stored value.
        settings = load_settings()
        for key, input_id in EXPRESSION_INPUTS:
            value_input = inputs.itemById(input_id)
            if value_input:
                settings[key] = value_input.expression

        for key, input_id, _low, _high in SPINNER_INPUTS:
            spinner = inputs.itemById(input_id)
            if spinner:
                settings[key] = int(spinner.value)

        for key, input_id in CHECKBOX_INPUTS:
            checkbox = inputs.itemById(input_id)
            if checkbox:
                settings[key] = bool(checkbox.value)

        for key, input_id in DROPDOWN_INPUTS:
            dropdown = inputs.itemById(input_id)
            if dropdown and dropdown.selectedItem:
                settings[key] = dropdown.selectedItem.name

        save_settings(settings)
