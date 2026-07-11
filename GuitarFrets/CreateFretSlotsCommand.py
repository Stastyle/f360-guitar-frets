# "Create Fret Slots" command: lays out a guitar neck on the fretboard top —
# fret slot rectangles (standard or multi-scale/fanned), an optional nut slot,
# a bridge mark, string guide lines, a tapered board outline, an optional
# single/compound radius cut, and an optional Push/Pull cut of the slots.
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
    'nut_slot_offset_expr': '0 mm',
    'nut_slot_depth_expr': '1.5 mm',
    'cut_slots': False,
    'slot_depth_expr': '2.5 mm',
    'mark_bridge': True,
    'flip_direction': False,
    'draw_strings': True,
    'string_count': 6,
    'string_spread_nut_expr': '35 mm',
    'string_spread_bridge_expr': '52.5 mm',
    'headstock_length_expr': '150 mm',
    'draw_taper': True,
    'nut_width_expr': '43 mm',
    'board_overhang_expr': '5 mm',
    'cut_taper': False,
    'multiscale': False,
    'bass_scale_expr': '26.5 in',
    'treble_scale_expr': '25.5 in',
    'perpendicular_fret': 7,
    'radius_mode': 'No radius',
    'radius_start_expr': '9.5 in',
    'radius_end_expr': '16 in',
    'buttons_promoted': False,
}

CREATE_NEW_LABEL = 'Create new sketch'
RADIUS_MODES = ('No radius', 'Single radius', 'Compound radius')

# sin(1 deg): the fret-zero reference may not be (nearly) parallel to the
# center line, or fret 0 cannot be located on it.
MIN_REF_ANGLE_SIN = 0.0175
COS_MIN_REF_ANGLE = 0.99985
# sin(15 deg): center line must lie roughly in the fretboard plane.
OUT_OF_PLANE_SIN_LIMIT = 0.2588

TANGENT_PLANE_MESSAGE = (
    'The selected fretboard top is not planar (radiused board?). '
    'Create a plane tangent to the board (Construct > Tangent Plane), '
    'project the board outline onto it, draw the center line in that sketch, '
    'and select the tangent plane here instead.'
)


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
    except Exception:
        pass
    if settings['radius_mode'] not in RADIUS_MODES:
        settings['radius_mode'] = DEFAULTS['radius_mode']
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as handle:
            json.dump(settings, handle, indent=2)
    except Exception:
        pass


def _get_selected(inputs, input_id):
    selection_input = inputs.itemById(input_id)
    if not selection_input or selection_input.selectionCount == 0:
        return None
    return selection_input.selection(0).entity


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
    """Every sketch this add-in tagged as a fret slot layout."""
    sketches = []
    for attribute in design.findAttributes(ATTRIBUTE_GROUP, ATTRIBUTE_NAME):
        parent = attribute.parent
        if not parent:  # the sketch was deleted; attributes can outlive entities
            continue
        sketch = adsk.fusion.Sketch.cast(parent)
        if sketch and sketch.isValid:
            sketches.append(sketch)
    return sketches


def _sketch_instances(design, sketch):
    """The sketch itself, or its proxies when its component occurs in the assembly."""
    occurrences = design.rootComponent.allOccurrencesByComponent(sketch.parentComponent)
    if occurrences.count == 0:
        return [sketch]

    instances = []
    for i in range(occurrences.count):
        try:
            instances.append(sketch.createForAssemblyContext(occurrences.item(i)))
        except Exception:
            pass
    return instances or [sketch]


def _top_plane_geometry(entity):
    """Plane of the fretboard top selection, or None when it is not planar."""
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            return None
        return adsk.core.Plane.cast(face.geometry)
    plane = adsk.fusion.ConstructionPlane.cast(entity)
    if plane:
        return plane.geometry
    return None


def _line_geometry(entity):
    """World-space Line3D of a sketch line or linear edge, or None."""
    line = adsk.fusion.SketchLine.cast(entity)
    if line:
        return line.worldGeometry
    edge = adsk.fusion.BRepEdge.cast(entity)
    if edge:
        return adsk.core.Line3D.cast(edge.geometry)
    return None


def _unit_direction(line3d):
    direction = line3d.startPoint.vectorTo(line3d.endPoint)
    if direction.length < 1e-9:
        return None
    direction.normalize()
    return direction


def _fret_zero_point(reference, centerline, center_direction):
    """Intersect the fret-zero reference with the center line.

    reference is either a planar BRepFace (nut face or fretboard end face) or
    a SketchLine drawn across the neck at the nut position. Returns a Point3D
    on the center line. Raises FretSlotsError on degenerate geometry.
    """
    face = adsk.fusion.BRepFace.cast(reference)
    if face:
        plane = adsk.core.Plane.cast(face.geometry)
        if abs(center_direction.dotProduct(plane.normal)) < MIN_REF_ANGLE_SIN:
            raise FretSlotsError('The fret-zero face is (nearly) parallel to the '
                                 'center line, so fret 0 cannot be located.')
        infinite_line = adsk.core.InfiniteLine3D.create(centerline.startPoint,
                                                        center_direction)
        point = plane.intersectWithLine(infinite_line)
        if not point:
            raise FretSlotsError('The center line does not cross the fret-zero '
                                 'face plane.')
        return point

    reference_geometry = _line_geometry(reference)
    if not reference_geometry:
        raise FretSlotsError('Could not read the fret-zero reference geometry.')
    reference_direction = _unit_direction(reference_geometry)
    if not reference_direction:
        raise FretSlotsError('The fret-zero line has zero length.')
    if abs(center_direction.dotProduct(reference_direction)) > COS_MIN_REF_ANGLE:
        raise FretSlotsError('The fret-zero line is (nearly) parallel to the '
                             'center line. Draw it across the neck at the nut '
                             'position.')

    try:
        t = fret_math.closest_point_parameter(
            centerline.startPoint.asArray(), center_direction.asArray(),
            reference_geometry.startPoint.asArray(), reference_direction.asArray())
    except ValueError as error:
        raise FretSlotsError('Could not locate fret 0 on the center line: {}'
                             .format(error))
    return adsk.core.Point3D.create(
        centerline.startPoint.x + t * center_direction.x,
        centerline.startPoint.y + t * center_direction.y,
        centerline.startPoint.z + t * center_direction.z)


def _neck_direction(centerline, fret_zero, flip):
    """Unit vector from fret 0 toward the far end of the center line."""
    to_start = fret_zero.distanceTo(centerline.startPoint)
    to_end = fret_zero.distanceTo(centerline.endPoint)
    target = centerline.endPoint if to_end >= to_start else centerline.startPoint

    direction = fret_zero.vectorTo(target)
    if direction.length < 1e-9:
        raise FretSlotsError('Could not determine the neck direction: fret 0 '
                             'sits on the far end of the center line.')
    direction.normalize()
    if flip:
        direction.scaleBy(-1.0)
    return direction


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

    for input_id, label in (
        ('slot_width', 'Fret slot width'),
        ('slot_length', 'Fret slot length'),
        ('string_spread_nut', 'String spread at nut'),
        ('string_spread_bridge', 'String spread at bridge'),
        ('headstock_length', 'Headstock line length'),
        ('nut_width', 'Nut width'),
        ('board_overhang', 'Board end past last fret'),
    ):
        read_length(input_id, label, input_id)

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

    # The nut offset shifts fret 0 (and the whole layout with it), so it is
    # read regardless of the nut slot checkbox. It may be zero or negative.
    values['nut_slot_offset'] = 0.0
    offset_input = inputs.itemById('nut_slot_offset')
    if offset_input:
        if offset_input.isValidExpression:
            values['nut_slot_offset'] = offset_input.value
        else:
            problems['nut_slot_offset'] = ('Nut offset: enter a valid '
                                           'length (0 for none).')

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
                          ('draw_strings', 'draw_strings'),
                          ('draw_taper', 'draw_taper'),
                          ('cut_taper', 'cut_taper'),
                          ('flip', 'flip_direction')):
        checkbox = inputs.itemById(input_id)
        values[key] = bool(checkbox.value) if checkbox else False

    return values, list(problems.values())


def validate_and_compute(inputs, radius_rejected=False, edit_sketch=None):
    """Validate all inputs. Returns (ok, message, params)."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return False, 'Open a design in the Design workspace first.', None

    problems = []
    ref_entity = _get_selected(inputs, 'fret_zero_ref')
    top_entity = _get_selected(inputs, 'top_plane')
    line_entity = _get_selected(inputs, 'center_line')

    # A layout that has a radius cut has no flat top face anymore; on edit,
    # build_slots removes the old radius (restoring the face) and re-resolves
    # it from the stored token, so an empty top selection is allowed there.
    edit_metadata = _sketch_metadata(edit_sketch) if edit_sketch else {}
    top_restorable = bool(edit_metadata.get('radius_feature_token')
                          and edit_metadata.get('top_token'))

    if not ref_entity:
        problems.append('Select the fret-zero reference: the nut face looking '
                        'toward the neck, the fretboard end face where the nut '
                        'will go, or a sketch line at the nut position.')
    if not top_entity and not top_restorable:
        problems.append(TANGENT_PLANE_MESSAGE if radius_rejected
                        else 'Select the fretboard top face (or a tangent construction plane).')
    if not line_entity:
        problems.append('Select the fretboard center line (sketch line or linear edge).')

    values, value_problems = _read_values(inputs)
    problems.extend(value_problems)
    if problems:
        return False, '\n'.join(problems), None

    top_plane = _top_plane_geometry(top_entity) if top_entity else None
    if top_entity and top_plane is None:
        return False, TANGENT_PLANE_MESSAGE, None

    centerline = _line_geometry(line_entity)
    center_direction = _unit_direction(centerline) if centerline else None
    if not center_direction:
        return False, 'Could not read a straight line from the center line selection.', None

    if top_plane and abs(center_direction.dotProduct(top_plane.normal)) > OUT_OF_PLANE_SIN_LIMIT:
        return False, ('The center line runs more than 15 degrees out of the '
                       'fretboard plane. Draw the center line on (or parallel to) '
                       'the fretboard top.'), None

    try:
        _fret_zero_point(ref_entity, centerline, center_direction)
    except FretSlotsError as error:
        return False, str(error), None

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

    if values['draw_taper'] and values['nut_width'] <= values['string_spread_nut']:
        return False, ('Nut width must be larger than the string spread at the '
                       'nut, so the board has an edge margin.'), None

    if values['cut_taper']:
        if not values['draw_taper']:
            return False, ('"Cut board to outline" needs "Draw fretboard '
                           'outline" enabled.'), None
        if top_entity and not adsk.fusion.BRepFace.cast(top_entity):
            return False, ('"Cut board to outline" requires selecting the '
                           'fretboard top FACE (not a construction plane).'), None

    radius_span = half_span
    if values['radius_mode']:
        if top_entity and not adsk.fusion.BRepFace.cast(top_entity):
            return False, ('Radius requires selecting the flat fretboard top '
                           'FACE (not a construction plane).'), None
        if values['draw_taper']:
            # The radius cut must cover the board at its widest point, or the
            # loft leaves flat shoulders along the edges near the board end.
            try:
                probe = fret_math.slot_layout(
                    values['bass_scale'], values['treble_scale'], fret_count,
                    values['perpendicular_fret'], half_span, slot_width)
                corners = fret_math.taper_outline(
                    probe['fret_zero'], probe['bridge'], probe['last'],
                    values['string_spread_nut'], values['string_spread_bridge'],
                    values['nut_width'], values['board_overhang'])
                radius_span = max(half_span,
                                  max(abs(corner[1]) for corner in corners) * 1.02)
            except ValueError:
                pass
        for radius in (values['radius_start'], values['radius_end']):
            if radius <= radius_span * 1.02:
                return False, ('The fretboard radius must be larger than half '
                               'the board width at its widest point (and half '
                               'the fret slot length).'), None

    params = _Params()
    params.fret_zero_ref = ref_entity
    params.top_entity = top_entity
    params.center_line = line_entity
    for key, value in values.items():
        setattr(params, key, value)
    params.half_span = half_span
    params.radius_span = radius_span
    params.edit_sketch = edit_sketch

    return True, _success_message(design.unitsManager, params), params


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
            params.nut_slot_width, params.nut_slot_offset)
        lines.append('Nut slot spans {} to {} from the selected fret-zero '
                     'reference (negative = behind it). The board must cover '
                     'that span, or part of the seat is cut in the air — '
                     'increase the nut offset to push it in.'
                     .format(fmt(rear), fmt(front)))
    elif params.nut_slot_offset:
        lines.append('Whole layout shifted {} from the fret-zero reference.'
                     .format(fmt(params.nut_slot_offset)))
    slot_count = params.fret_count + (1 if params.nut_slot_width else 0)
    summary = '{} slots'.format(slot_count)
    if params.draw_strings:
        summary += ', {} string lines'.format(params.string_count)
    if params.draw_taper:
        summary += ', board outline'
    if params.cut_taper:
        summary += ' (board cut to it)'
    lines.append(summary + '. If frets march the wrong way, check Flip direction.')
    if params.cut_depth:
        lines.append('Slots will be cut {} deep.'.format(fmt(params.cut_depth)))
    if params.radius_mode:
        drop = params.radius_start - math.sqrt(
            max(0.0, params.radius_start ** 2 - params.half_span ** 2))
        lines.append('Radius drop at the slot ends: {} — edge slots end up that '
                     'much shallower.'.format(fmt(drop)))
    return '\n'.join(lines)


def _delete_projected_curves(sketch):
    stale = [curve for curve in sketch.sketchCurves if curve.isReference]
    for curve in stale:
        try:
            curve.deleteMe()
        except Exception:
            pass


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


def _create_sketch(top_entity):
    """Create a sketch on the selected face/plane.

    Returns (native_sketch, mapping_sketch): draw into the native sketch;
    use the mapping sketch (a proxy when the selection lives in an occurrence)
    to convert root-space points with modelToSketchSpace.
    """
    face = adsk.fusion.BRepFace.cast(top_entity)
    if face:
        context = face.assemblyContext
        native = face.nativeObject if context else face
        sketches = native.body.parentComponent.sketches
        if hasattr(sketches, 'addWithoutEdges'):
            sketch = sketches.addWithoutEdges(native)
        else:
            sketch = sketches.add(native)
            _delete_projected_curves(sketch)
    else:
        plane = adsk.fusion.ConstructionPlane.cast(top_entity)
        context = plane.assemblyContext
        native = plane.nativeObject if context else plane
        sketch = native.component.sketches.add(native)

    mapping_sketch = sketch
    if context:
        try:
            mapping_sketch = sketch.createForAssemblyContext(context)
        except Exception:
            sketch.deleteMe()
            raise FretSlotsError(
                'The fretboard lives inside a component occurrence that this '
                'add-in could not map. Activate (Edit in Place) the component '
                'that contains the fretboard and run the command again.')
    return sketch, mapping_sketch


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


def _board_body(top_entity):
    face = adsk.fusion.BRepFace.cast(top_entity)
    if face:
        native = face.nativeObject if face.assemblyContext else face
        return native.body
    return None


def _restore_top_entity(design, metadata):
    """Re-resolve the flat top face after the old radius cut was removed."""
    token = metadata.get('top_token') or ''
    if token:
        try:
            for entity in design.findEntityByToken(token):
                if _top_plane_geometry(entity) is not None:
                    return entity
        except Exception:
            pass
    raise FretSlotsError('The original fretboard top face could not be '
                         'restored after removing the old radius cut. Undo '
                         'and try again, or select the top face manually.')


def _delete_tracked(design, metadata):
    """Remove everything a previous run of this add-in created for a layout
    (except the slot sketch itself). Order matters: features first, then the
    sketches and planes they consume."""
    groups = (
        ('nut_cut_token', adsk.fusion.ExtrudeFeature),
        ('cut_token', adsk.fusion.ExtrudeFeature),
        ('taper_cut_token', adsk.fusion.ExtrudeFeature),
        ('radius_feature_token', adsk.fusion.LoftFeature),
        ('radius_sketch_tokens', adsk.fusion.Sketch),
        ('radius_plane_tokens', adsk.fusion.ConstructionPlane),
        ('bridge_token', adsk.fusion.Sketch),
        ('strings_token', adsk.fusion.Sketch),
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


def _intersect_board_with_outline(taper_sketch, board):
    """Trim the board body to the taper outline (an Intersect extrude)."""
    if not board:
        raise FretSlotsError('"Cut board to outline" requires selecting the '
                             'fretboard top face.')
    if taper_sketch.profiles.count == 0:
        raise FretSlotsError('The fretboard outline did not form a closed '
                             'profile to cut with.')
    features = taper_sketch.parentComponent.features.extrudeFeatures
    profiles = adsk.core.ObjectCollection.create()
    for profile in taper_sketch.profiles:
        profiles.add(profile)
    try:
        cut_input = features.createInput(
            profiles, adsk.fusion.FeatureOperations.IntersectFeatureOperation)
        # Generous symmetric extent so any board thickness is covered.
        cut_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(40.0), True)
        cut_input.participantBodies = [board]
        return features.add(cut_input)
    except Exception:
        raise FretSlotsError('Could not cut the board to the outline — make '
                             'sure the outline overlaps the board body.')


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


def _top_outward_normal(top_face):
    # Use the face as selected (a proxy inside an occurrence) so the normal
    # comes back in root space, consistent with the root-space crown points
    # and neck direction it is combined with.
    try:
        ok, normal = top_face.evaluator.getNormalAtPoint(top_face.pointOnFace)
        if ok and normal:
            return normal
    except Exception:
        pass
    try:
        normal = adsk.core.Plane.cast(top_face.geometry).normal.copy()
        if top_face.isParamReversed:
            normal.scaleBy(-1.0)
        return normal
    except Exception:
        raise FretSlotsError('The fretboard top face reference is no longer '
                             'valid — reselect the top face and try again.')


def _apply_radius(params, sketch, mapping_sketch, frame, direction, layout):
    """Loft-cut a single or compound radius onto the board top.

    Two arc profiles are sketched on transverse planes just behind the nut and
    just past the board end, then lofted as a cut restricted to the board
    body. Returns (loft_feature, sketches, planes) for edit-mode tracking.
    Raises FretSlotsError with a hint when the geometry cannot be built.
    """
    top_face = adsk.fusion.BRepFace.cast(params.top_entity)
    board = _board_body(params.top_entity)
    if not (top_face and board):
        raise FretSlotsError('Radius requires selecting the flat fretboard '
                             'top face.')
    context = top_face.assemblyContext
    native_top = top_face.nativeObject if context else top_face
    component = native_top.body.parentComponent
    up = _top_outward_normal(top_face)

    # Stations along the neck (local x): behind the fanned nut and past the
    # board end, so the loft covers the whole board with margin.
    nut_skew = abs(layout['fret_zero'][0][0] - layout['fret_zero'][1][0])
    back_x = -(2.0 + nut_skew + (params.nut_slot_width or 0.0))
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

    # Transverse base plane at fret zero, exactly perpendicular to the neck.
    # Built from our own construction line in the slot sketch (not the user's
    # fret-zero reference) so it stays true for fanned layouts, whose nut is
    # skewed — offsetting a skewed plane would distort the cut radius by
    # cos²(fan angle) — and so all references live in the board's component.
    try:
        transverse = sketch.sketchCurves.sketchLines.addByTwoPoints(
            _place_point((0.0, -params.half_span), frame),
            _place_point((0.0, params.half_span), frame))
        transverse.isConstruction = True
        plane_input = planes.createInput()
        plane_input.setByAngle(transverse,
                               adsk.core.ValueInput.createByReal(math.pi / 2),
                               native_top)
        base_plane = planes.add(plane_input)
        created_planes.append(base_plane)
        base_entity = base_plane
        base_normal = base_plane.geometry.normal
    except Exception:
        cleanup_and_raise('Could not build the radius reference plane:\n{}'
                          .format(traceback.format_exc().splitlines()[-1]))

    sign = 1.0 if base_normal.dotProduct(direction) >= 0 else -1.0

    profiles = []
    for station_x in (back_x, front_x):
        radius = radius_at(station_x)
        try:
            plane_input = planes.createInput()
            plane_input.setByOffset(
                base_entity, adsk.core.ValueInput.createByReal(station_x * sign))
            plane = planes.add(plane_input)
            created_planes.append(plane)

            profile_sketch = component.sketches.add(plane)
            created_sketches.append(profile_sketch)
            profile_sketch.name = 'Radius Profile'
            sketch_map = (profile_sketch.createForAssemblyContext(context)
                          if context else profile_sketch)

            crown3d = mapping_sketch.sketchToModelSpace(
                _place_point((station_x, 0.0), frame))
            up_point = crown3d.copy()
            up_step = up.copy()
            up_point.translateBy(up_step)
            crown2 = sketch_map.modelToSketchSpace(crown3d.copy())
            up2 = sketch_map.modelToSketchSpace(up_point)
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
            loft_input.participantBodies = [native_top.body]
        except Exception:
            pass
        feature = lofts.add(loft_input)
    except Exception:
        cleanup_and_raise('The radius cut failed — check that the radius is '
                          'larger than half the board width and that the board '
                          'top is still flat.')

    return feature, created_sketches, created_planes


def _draw_polyline_sketch(params, fret_zero, direction, name, point_pairs,
                          close_loop=False, construction=False):
    """Create an extra sketch on the top entity and draw the given local-frame
    lines into it. point_pairs is a list of (start, end) local points, or a
    list of corner points when close_loop is True."""
    sketch, mapping = _create_sketch(params.top_entity)
    try:
        frame = _sketch_frame(mapping, fret_zero, direction)
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


def build_slots(params):
    """Create or rebuild the whole layout.

    In edit mode (params.edit_sketch set) the slot sketch's curves are
    replaced in place — keeping the sketch object alive so downstream features
    (e.g. a manual Press Pull cut) can recompute — and every object the add-in
    created for the layout (cut, radius, string/taper sketches) is recreated.
    Raises FretSlotsError on geometric problems.
    """
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)

    centerline = _line_geometry(params.center_line)
    center_direction = _unit_direction(centerline) if centerline else None
    if not center_direction:
        raise FretSlotsError('Could not read the center line geometry.')

    fret_zero = _fret_zero_point(params.fret_zero_ref, centerline, center_direction)
    direction = _neck_direction(centerline, fret_zero, params.flip)

    # The nut offset pushes fret 0 — and with it the WHOLE layout (frets,
    # nut slot, strings, taper, bridge, radius) — along the neck away from
    # the selected reference, e.g. when the nut sits in a slot inside the
    # fretboard rather than against its end.
    if params.nut_slot_offset:
        shift = direction.copy()
        shift.scaleBy(params.nut_slot_offset)
        fret_zero.translateBy(shift)

    created_new = params.edit_sketch is None
    extra_sketches = []
    radius_feature = None
    radius_sketches = []
    radius_planes = []
    cut_feature = None
    nut_cut_feature = None
    taper_cut_feature = None
    try:
        timeline_start = design.timeline.markerPosition
    except Exception:
        timeline_start = None
    if created_new:
        sketch, mapping_sketch = _create_sketch(params.top_entity)
    else:
        sketch = params.edit_sketch
        mapping_sketch = _sketch_instances(design, sketch)[0]
        old_metadata = _sketch_metadata(sketch)
        # Remove everything the previous run created before touching the
        # curves those features consume; all of it is recreated below.
        _delete_tracked(design, old_metadata)
        if params.top_entity is None:
            # The old radius cut consumed the flat top face; deleting that cut
            # just restored it — pick it back up from the stored token.
            params.top_entity = _restore_top_entity(design, old_metadata)
        _clear_sketch_curves(sketch)

    try:
        frame = _sketch_frame(mapping_sketch, fret_zero, direction)

        # Capture the board body and selection tokens BEFORE any feature is
        # created: the radius loft consumes the flat top face, after which
        # neither its token nor its body can be resolved from the stale proxy.
        board = _board_body(params.top_entity)
        selection_tokens = {
            'fret_zero_token': _entity_token(params.fret_zero_ref),
            'top_token': _entity_token(params.top_entity),
            'center_line_token': _entity_token(params.center_line),
        }

        layout = fret_math.slot_layout(
            params.bass_scale, params.treble_scale, params.fret_count,
            params.perpendicular_fret, params.half_span, params.slot_width,
            params.nut_slot_width)

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
                params, fret_zero, direction, 'Bridge Mark',
                [layout['bridge']], construction=True)
            extra_sketches.append(bridge_sketch)

        strings_sketch = None
        if params.draw_strings:
            strings = fret_math.string_layout(
                layout['fret_zero'], layout['bridge'], params.string_count,
                params.string_spread_nut, params.string_spread_bridge,
                params.headstock_length)
            strings_sketch = _draw_polyline_sketch(
                params, fret_zero, direction,
                'String Layout ({} strings)'.format(params.string_count),
                strings)
            extra_sketches.append(strings_sketch)

        taper_sketch = None
        if params.draw_taper:
            try:
                corners = fret_math.taper_outline(
                    layout['fret_zero'], layout['bridge'], layout['last'],
                    params.string_spread_nut, params.string_spread_bridge,
                    params.nut_width, params.board_overhang)
            except ValueError as error:
                raise FretSlotsError(str(error))
            taper_sketch = _draw_polyline_sketch(
                params, fret_zero, direction, 'Fretboard Outline', corners,
                close_loop=True)
            extra_sketches.append(taper_sketch)

        if params.radius_mode:
            radius_feature, radius_sketches, radius_planes = _apply_radius(
                params, sketch, mapping_sketch, frame, direction, layout)

        # The outline cut trims the top face, invalidating face references —
        # so it must run AFTER the radius (which needs the pristine face) and
        # rely only on the taper profile and the board body from here on.
        if params.cut_taper and taper_sketch:
            taper_cut_feature = _intersect_board_with_outline(taper_sketch, board)

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
        # tidy the browser: only the working references (string layout and
        # bridge mark) stay visible. Sketches whose geometry now exists as
        # solid (cut slots / cut board) are hidden — but without a cut the
        # slot sketch stays visible, or there would be nothing to see.
        for created_sketch in [sketch] + extra_sketches + radius_sketches:
            _fix_all_curves(created_sketch)
        to_hide = list(radius_sketches) + list(radius_planes)
        if cut_feature:
            to_hide.append(sketch)
        if taper_cut_feature and taper_sketch:
            to_hide.append(taper_sketch)
        for visible_object in to_hide:
            try:
                visible_object.isLightBulbOn = False
            except Exception:
                pass

        metadata = json.dumps({
            'version': 5,
            'scale_cm': (params.bass_scale + params.treble_scale) / 2.0,
            'bass_scale_cm': params.bass_scale,
            'treble_scale_cm': params.treble_scale,
            'multiscale': params.multiscale,
            'perpendicular_fret': params.perpendicular_fret,
            'fret_count': params.fret_count,
            'slot_width_cm': params.slot_width,
            'slot_length_cm': params.half_span * 2.0,
            'nut_slot_width_cm': params.nut_slot_width,
            'nut_slot_offset_cm': params.nut_slot_offset,
            'nut_slot_depth_cm': params.nut_slot_depth,
            'cut_depth_cm': params.cut_depth,
            'mark_bridge': params.mark_bridge,
            'flip': params.flip,
            'draw_strings': params.draw_strings,
            'string_count': params.string_count,
            'string_spread_nut_cm': params.string_spread_nut,
            'string_spread_bridge_cm': params.string_spread_bridge,
            'headstock_length_cm': params.headstock_length,
            'draw_taper': params.draw_taper,
            'nut_width_cm': params.nut_width,
            'board_overhang_cm': params.board_overhang,
            'cut_taper': params.cut_taper,
            'taper_cut_token': (_entity_token(taper_cut_feature)
                                if taper_cut_feature else ''),
            'radius_mode': params.radius_mode,
            'radius_start_cm': params.radius_start,
            'radius_end_cm': params.radius_end,
            'fret_zero_token': selection_tokens['fret_zero_token'],
            'top_token': selection_tokens['top_token'],
            'center_line_token': selection_tokens['center_line_token'],
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
        # Never leave half-built geometry behind: remove everything this run
        # created, in feature-before-consumed-object order. An edited slot
        # sketch is the user's existing object — leave it for undo instead of
        # deleting it.
        cleanup = ([nut_cut_feature, cut_feature, taper_cut_feature,
                    radius_feature]
                   + radius_sketches + radius_planes + extra_sketches)
        if created_new:
            cleanup.append(sketch)
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
        self._radius_rejected = False
        self._edit_sketches = []

    @staticmethod
    def _focus_next(inputs, input_id):
        """Activate the next selection input so the user can keep picking in
        the canvas without clicking the dialog. Skipped when it already has a
        selection (e.g. restored by edit-mode prefill)."""
        next_input = inputs.itemById(input_id)
        if next_input and next_input.selectionCount == 0:
            try:
                next_input.hasFocus = True
            except Exception:
                pass

    def _edit_sketch_from_inputs(self, inputs):
        dropdown = inputs.itemById('edit_target')
        if not dropdown:
            return None
        item = dropdown.selectedItem
        if not item or item.index <= 0:
            return None
        index = item.index - 1
        if index >= len(self._edit_sketches):
            return None
        sketch = self._edit_sketches[index]
        return sketch if sketch and sketch.isValid else None

    def _prefill_from_sketch(self, inputs, sketch):
        """Load stored parameters and selections of an existing fret sketch."""
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
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

        offset_input = inputs.itemById('nut_slot_offset')
        stored_offset = metadata.get('nut_slot_offset_cm')
        if offset_input and isinstance(stored_offset, (int, float)):
            try:
                offset_input.value = float(stored_offset)
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
        set_check('flip_direction', 'flip')
        set_check('draw_strings', 'draw_strings')
        set_spinner('string_count', 'string_count', 1, 12)
        set_value('string_spread_nut', 'string_spread_nut_cm')
        set_value('string_spread_bridge', 'string_spread_bridge_cm')
        set_value('headstock_length', 'headstock_length_cm')
        set_check('draw_taper', 'draw_taper')
        set_value('nut_width', 'nut_width_cm')
        set_value('board_overhang', 'board_overhang_cm')
        set_check('cut_taper', 'cut_taper')

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

        for input_id, key in (('fret_zero_ref', 'fret_zero_token'),
                              ('top_plane', 'top_token'),
                              ('center_line', 'center_line_token')):
            selection_input = inputs.itemById(input_id)
            if not selection_input:
                continue
            selection_input.clearSelection()
            token = metadata.get(key) or ''
            if not token or not design:
                continue
            try:
                found = design.findEntityByToken(token)
                if found:
                    selection_input.addSelection(found[0])
            except Exception:
                pass

        self._radius_rejected = False

    @staticmethod
    def _apply_nut_cut_visibility(inputs, nut_on, cut_on):
        # The nut offset stays visible always: it moves the whole layout,
        # not just the nut slot.
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
    def _apply_radius_visibility(inputs, mode_name):
        start_input = inputs.itemById('radius_start')
        if start_input:
            start_input.isVisible = mode_name != 'No radius'
        end_input = inputs.itemById('radius_end')
        if end_input:
            end_input.isVisible = mode_name == 'Compound radius'

    def on_create(self, command, inputs):
        self._preview_ok = False
        self._radius_rejected = False
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
        units = design.unitsManager.defaultLengthUnits

        self._edit_sketches = _find_fret_sketches(design)
        edit_dropdown = inputs.addDropDownCommandInput(
            'edit_target', 'Edit',
            adsk.core.DropDownStyles.TextListDropDownStyle)
        edit_dropdown.listItems.add(CREATE_NEW_LABEL, True, '')
        for sketch in self._edit_sketches:
            edit_dropdown.listItems.add(sketch.name, False, '')
        if not self._edit_sketches:
            edit_dropdown.isVisible = False

        # The command prompt (3rd argument) is what Fusion shows in the tooltip
        # beside the cursor while the input is active — keep it short and
        # actionable; the longer explanation goes into the hover tooltip.
        ref_sel = inputs.addSelectionInput(
            'fret_zero_ref', 'Fret zero (nut)',
            '1/3  Select fret zero: the nut face, the fretboard end face, or '
            'a sketch line at the nut position')
        ref_sel.tooltip = (
            'Where fret 0 sits. Pick one: the nut face that looks toward the '
            'neck, the end face of the fretboard where the nut will go, or a '
            'sketch line drawn across the neck at the nut position.')
        ref_sel.addSelectionFilter('PlanarFaces')
        ref_sel.addSelectionFilter('SketchLines')
        ref_sel.setSelectionLimits(1, 1)

        top_sel = inputs.addSelectionInput(
            'top_plane', 'Fretboard top',
            '2/3  Select the fretboard top face (or a tangent plane for a '
            'radiused board)')
        top_sel.tooltip = (
            'Top face of the fretboard, or a tangent construction plane for a '
            'radiused board. The sketches are created on it.')
        top_sel.addSelectionFilter('Faces')
        top_sel.addSelectionFilter('ConstructionPlanes')
        top_sel.setSelectionLimits(1, 1)

        line_sel = inputs.addSelectionInput(
            'center_line', 'Center line',
            '3/3  Select the center line running along the neck')
        line_sel.tooltip = (
            'Sketch line or linear edge running along the middle of the neck. '
            'Frets march from fret 0 toward its far end.')
        line_sel.addSelectionFilter('SketchLines')
        line_sel.addSelectionFilter('LinearEdges')
        line_sel.setSelectionLimits(1, 1)

        inputs.addBoolValueInput('flip_direction', 'Flip direction', True, '',
                                 bool(settings['flip_direction']))

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
        value_input(inputs, 'nut_slot_offset', 'Nut offset', 'nut_slot_offset_expr')
        offset_input = inputs.itemById('nut_slot_offset')
        if offset_input:
            offset_input.tooltip = (
                'Shift fret 0 — and the WHOLE layout with it (frets, nut '
                'slot, strings, outline, bridge) — along the neck, away from '
                'the selected fret-zero reference. Positive pushes it into '
                'the board, e.g. when the nut sits in a slot inside the '
                'fretboard instead of against its end. 0 keeps fret 0 '
                'exactly on the reference.')
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
            'grp_strings', 'Strings and board outline')
        strings_group.isExpanded = bool(settings['draw_strings'] or settings['draw_taper'])
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
        sg.addBoolValueInput('draw_taper', 'Draw fretboard outline', True, '',
                             bool(settings['draw_taper']))
        value_input(sg, 'nut_width', 'Nut width', 'nut_width_expr')
        value_input(sg, 'board_overhang', 'Board end past last fret',
                    'board_overhang_expr')
        cut_taper_checkbox = sg.addBoolValueInput(
            'cut_taper', 'Cut board to outline', True, '',
            bool(settings['cut_taper']))
        cut_taper_checkbox.tooltip = (
            'Trim the board body to the drawn outline (an Intersect extrude '
            'through the whole board) — the blank takes the tapered shape in '
            'the same operation.')

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

        hardware_group = inputs.addGroupCommandInput(
            'grp_hardware', 'Hardware (coming soon)')
        hardware_group.isExpanded = False
        hg = hardware_group.children
        tuners_checkbox = hg.addBoolValueInput(
            'place_tuners', 'Tuner layout', True, '', False)
        tuners_checkbox.isEnabled = False
        tuners_checkbox.tooltip = (
            'Planned: tuner hole positions laid out along the headstock '
            'extensions of the string lines.')
        bridge_hw_checkbox = hg.addBoolValueInput(
            'place_bridge', 'Bridge hardware', True, '', False)
        bridge_hw_checkbox.isEnabled = False
        bridge_hw_checkbox.tooltip = (
            'Planned: bridge/saddle footprint placed on the bridge mark, '
            'with per-string compensation.')

        inputs.addTextBoxCommandInput(
            'info_box', 'Info',
            'Select the fret zero reference, fretboard top, and center line.',
            8, True)

    def on_input_changed(self, command_, command_inputs, changed_input, input_values):
        if changed_input.id == 'info_box':
            return

        if changed_input.id == 'edit_target':
            sketch = self._edit_sketch_from_inputs(command_inputs)
            if sketch:
                self._prefill_from_sketch(command_inputs, sketch)

        if changed_input.id == 'fret_zero_ref':
            if changed_input.selectionCount >= 1:
                self._focus_next(command_inputs, 'top_plane')

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

        if changed_input.id == 'top_plane':
            entity = _get_selected(command_inputs, 'top_plane')
            if entity:
                if _top_plane_geometry(entity) is None:
                    changed_input.clearSelection()
                    self._radius_rejected = True
                    # Keep the focus here so the user can re-pick right away.
                    try:
                        changed_input.hasFocus = True
                    except Exception:
                        pass
                else:
                    self._radius_rejected = False
                    self._focus_next(command_inputs, 'center_line')

        info = command_inputs.itemById('info_box')
        if info:
            _, message, _ = validate_and_compute(
                command_inputs, self._radius_rejected,
                self._edit_sketch_from_inputs(command_inputs))
            if info.text != message:
                info.text = message

    def on_preview(self, command, inputs, args, input_values):
        self._preview_ok = False
        ok, message, params = validate_and_compute(
            inputs, self._radius_rejected, self._edit_sketch_from_inputs(inputs))
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
            inputs, self._radius_rejected, self._edit_sketch_from_inputs(inputs))
        if not ok:
            ui.messageBox('Cannot create fret slots:\n\n{}'.format(message))
            return
        try:
            build_slots(params)
        except FretSlotsError as error:
            ui.messageBox('Cannot create fret slots:\n\n{}'.format(error))
        except Exception:
            ui.messageBox('Create Fret Slots failed:\n{}'.format(traceback.format_exc()))

    def on_destroy(self, command, inputs, reason, input_values):
        if reason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
            return
        # info_box is the last input on_create adds; without it the dialog was
        # never fully built (no active design, or on_create failed part-way).
        # Saving from a crippled dialog would overwrite the stored settings
        # with defaults.
        if not inputs.itemById('info_box'):
            return

        settings = load_settings()
        for key, input_id in (
            ('scale_length_expr', 'scale_length'),
            ('slot_width_expr', 'slot_width'),
            ('slot_length_expr', 'slot_length'),
            ('nut_slot_width_expr', 'nut_slot_width'),
            ('nut_slot_offset_expr', 'nut_slot_offset'),
            ('nut_slot_depth_expr', 'nut_slot_depth'),
            ('slot_depth_expr', 'slot_depth'),
            ('string_spread_nut_expr', 'string_spread_nut'),
            ('string_spread_bridge_expr', 'string_spread_bridge'),
            ('headstock_length_expr', 'headstock_length'),
            ('nut_width_expr', 'nut_width'),
            ('board_overhang_expr', 'board_overhang'),
            ('bass_scale_expr', 'bass_scale'),
            ('treble_scale_expr', 'treble_scale'),
            ('radius_start_expr', 'radius_start'),
            ('radius_end_expr', 'radius_end'),
        ):
            value_input = inputs.itemById(input_id)
            if value_input:
                settings[key] = value_input.expression

        for key, input_id in (('fret_count', 'fret_count'),
                              ('string_count', 'string_count'),
                              ('perpendicular_fret', 'perpendicular_fret')):
            spinner = inputs.itemById(input_id)
            if spinner:
                settings[key] = int(spinner.value)

        for key, input_id in (('create_nut_slot', 'create_nut_slot'),
                              ('cut_slots', 'cut_slots'),
                              ('mark_bridge', 'mark_bridge'),
                              ('flip_direction', 'flip_direction'),
                              ('draw_strings', 'draw_strings'),
                              ('draw_taper', 'draw_taper'),
                              ('cut_taper', 'cut_taper'),
                              ('multiscale', 'multiscale')):
            checkbox = inputs.itemById(input_id)
            if checkbox:
                settings[key] = bool(checkbox.value)

        dropdown = inputs.itemById('radius_mode')
        if dropdown and dropdown.selectedItem:
            settings['radius_mode'] = dropdown.selectedItem.name

        save_settings(settings)
