# Geometry patterns: build in a component, probe, tag, clean up

The approach that made the add-in robust after a selection-based first
version kept breaking on stale references and assembly transforms.

## Create, don't select

Build everything in a **new component in a canonical frame** instead of
cutting into geometry the user selected:

- `occurrence = design.activeComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create())`,
  `component = occurrence.component`.
- Decide the frame once and document it (README, info box, DEV_NOTES): e.g.
  datum at the origin, main axis +X, top face on the XY plane, body hanging
  below (−Z). The user moves or joints the component afterwards.
- Sketch only on the component's own construction planes
  (`xYConstructionPlane`, `yZConstructionPlane`, offset/angled planes built
  from them). No face references → nothing goes stale when a cut changes a
  face, and no occurrence proxies (`createForAssemblyContext`) → sketch
  coordinates are component coordinates.
- The math module works in a local 2D/3D frame with plain tuples; the
  command maps points into sketch space with `sketch.modelToSketchSpace`
  per sketch (see `_sketch_point` in the template) rather than assuming the
  sketch axes coincide with the component axes.

If a feature genuinely needs user geometry (a face to cut, a line as datum),
keep that to one selection, store its `entityToken` in the metadata, and
validate it on rebuild — and expect that layouts become un-editable when the
user deletes that entity (hide them from the edit dropdown with a note).

## Feature order

1. Outline sketch → **body extrude** (NewBody). Everything else cuts into or
   references this body.
2. Layout sketches (the metadata-carrying sketch first, so it exists even if
   a later step fails), reference marks in their own sketches (a consumed
   sketch is auto-hidden; references must stay visible).
3. Shaping features that change the top face (e.g. a radius loft),
   participant-limited to the body.
4. Slot/hole cuts from the layout sketch profiles, participant-limited.

Do not shuffle: a later step must not hold a face reference taken before an
earlier cut changed that face.

**Several bodies** (panels of a box, a set of parts): treat each as its own
"outline sketch → NewBody extrude" on a sketch placed on the matching base
plane or an offset of it (`xYConstructionPlane` for a horizontal panel,
`xZConstructionPlane`/`yZConstructionPlane` for vertical ones — see
api-gotchas §6 about verifying their orientation), probe each extrude by
checking that the body's bounding box lands inside the part's outer
envelope, name each body, and track every extrude token in the metadata.
Cuts that must affect one body only get `participantBodies = [that body]`.

## Probe every sign convention

Whether an offset plane goes +z or −z, whether a positive extrude distance
goes along or against the sketch normal, whether `setByAngle` tilts toward
or away from the reference — treat all of these as unknown and verify:

```python
# Plane offset: a known on-plane point must map to sketch z ≈ 0.
for sign in (1.0, -1.0):
    plane_input = planes.createInput()
    plane_input.setByOffset(component.xYConstructionPlane,
                            adsk.core.ValueInput.createByReal(distance * sign))
    plane = planes.add(plane_input)
    probe = component.sketches.add(plane)
    if abs(probe.modelToSketchSpace(known_point.copy()).z) < 1e-3:
        break                      # keep plane + probe (reuse probe as the real sketch)
    probe.deleteMe(); plane.deleteMe()
else:
    raise BuildError('Could not place the plane.')

# Extrude direction: check where the body ended up.
for signed in (-thickness, thickness):
    feature = extrude(profiles, signed)
    if feature.bodies.item(0).boundingBox.maxPoint.z <= 1e-4:
        return feature
    feature.deleteMe()

# Cut direction: a cut that removes nothing raises on add — try the other sign.
for signed in (-depth, depth):
    try:
        return cut(profiles, signed, participant=body)
    except Exception:
        continue
```

For a sketch on a tilted plane, **measure the in-sketch frame** by mapping
three known component-space points (origin, a point along the intended x,
a point along the intended y) and build the axes from the differences —
never assume the sketch x/y orientation on a derived plane. Pick the lateral
probe *on the same plane* as the origin (projecting a point from a different
height smears height × sin θ into the other axis).

Fail loud: when every candidate fails, raise the domain error with a hint
that names the DEV_NOTES section — never draw a possibly flipped reference.

## Telling profiles apart

After drawing several closed shapes in one sketch, `sketch.profiles` has no
stable order. Classify by `profile.areaProperties().area` (a scalar, immune
to coordinate questions): e.g. everything above the midpoint between the two
expected areas is the big slot. Skip the split when the expected areas are
within ~1.5× of each other and cut everything at one depth instead.

## Metadata: parameters + tokens on one entity

The sketch created first carries a JSON attribute:

```python
metadata = json.dumps({
    'version': METADATA_VERSION,
    'length_cm': params.length, ...,            # every parameter, internal units
    'body_token': body_feature.entityToken,     # every created object
    'holes_sketch_token': ..., 'holes_cut_token': ...,
    'radius_plane_tokens': [p.entityToken for p in planes],   # lists for chains
})
sketch.attributes.add(ATTRIBUTE_GROUP, ATTRIBUTE_NAME, metadata)
```

Rebuild (edit mode):

1. `_delete_tracked(design, old_metadata)` deletes tracked objects in
   **consumed-last order** — cut features, then the sketches they used, then
   shaping features, then their sketches and planes, then the body extrude,
   then the outline sketch it consumed. A chain (sketch on angled plane on
   hinge sketch on offset plane) is deleted from the end of the chain.
2. `_clear_sketch_curves(tagged_sketch)` — the tagged sketch object itself
   is **kept** and its curves replaced in place, so a feature the *user*
   built on it (a manual Press Pull) recomputes instead of dying with a
   lost-profile error.
3. Build as new inside the same component; write fresh metadata (the
   attribute is replaced).

Caveat to document: a user feature that referenced the *recreated body* must
be reattached after an edit — same as any recreated body in Fusion.

## Cleanup on failure

Wrap the build in one `try/except` that undoes **everything created in this
run**, then re-raises:

- New layout: `occurrence.deleteMe()` — it removes the whole component.
- Edit: delete the recreated objects in feature-before-consumed-object
  order (mirror `_delete_tracked`), and leave the user's tagged sketch alone
  (empty curves are better than a deleted sketch; Undo restores it).

Inside helpers that create several objects (planes + sketches), keep a
`created` list and a `cleanup_and_raise(message)` closure that deletes it in
reverse before raising `BuildError`.

## Tidy up after a successful build

- `curve.isFixed = True` on every curve of every created sketch.
- Hide tooling (`isLightBulbOn = False`): the outline sketch (it lives on as
  the body), probe/profile sketches, construction planes, and the layout
  sketch *when its cut exists*. Set visibility **both ways** — an edit may
  inherit a hidden sketch from a run whose cut is now unchecked.
- Keep working references visible in their own sketches.
- Name the body, the sketches and the component after the key parameters.
- Wrap a new layout in a named timeline group (`timeline.markerPosition`
  before; `timelineGroups.add(start, markerPosition - 1)` after). Edits
  cannot join it.

## Sketch drawing helpers worth copying

- Polyline sketch: create the sketch, map each point with
  `modelToSketchSpace`, draw with `isComputeDeferred`, name it, and delete
  the sketch if anything raises (so a failed helper leaves nothing).
- Rectangles from a centre segment: compute the three corners in the math
  module (`segment_rectangle`), draw with `addThreePointRectangle`.
- Circles + centre points for hole templates:
  `sketchCircles.addByCenterRadius(center, r)` and `sketch.sketchPoints.add(center)`
  so the user can snap to the centre.
- Arc profile for a radius crown: `addByCenterStartSweep` from the `α−θ`
  end sweeping `2θ`, closed with three lines above the chord; then
  `profiles.count == 0` means the arc went the wrong way.
