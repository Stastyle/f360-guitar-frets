# Developer notes — API assumptions and pre-flight checks

The add-in leans on a few Fusion 360 API behaviors that are worth verifying
once per Fusion release, in **Utilities → Text Commands** (switch the input
mode from `Txt` to `Py`). Paste one block at a time.

## 1. Feature ordering inside `build_slots` (do not shuffle)

Sketches first (slot, bridge, strings, taper — they all reference the pristine
top face), then the radius loft (needs the pristine face for its normal and
`setByAngle` reference), then the outline Intersect cut (TRIMS the top face —
face references are stale from here on), then the slot/nut extrudes (which
only use the board BODY captured at the start and sketch profiles). The
"Select Fret Slots" button and its custom-event plumbing were removed
(2026-07-11); its sketch-lookup helpers (`_find_fret_sketches`,
`_sketch_instances`) now live in `CreateFretSlotsCommand.py` and serve the
Edit dropdown.

## 2. `isValidResult` keeps the preview and skips execute

`CreateFretSlotsCommand.on_preview` sets `args.isValidResult = True` after a
successful build; Fusion then reuses the preview as the final result on OK and
does not fire the execute event. `on_execute` keeps a `_preview_ok` guard as a
fallback either way, so a behavior change here degrades gracefully (worst case:
geometry is rebuilt once on OK).

## 3. Plane/line intersection

```python
import adsk.core
pl = adsk.core.Plane.create(adsk.core.Point3D.create(0,0,1), adsk.core.Vector3D.create(0,0,1))
ln = adsk.core.InfiniteLine3D.create(adsk.core.Point3D.create(0,0,0), adsk.core.Vector3D.create(0,0,1))
print(pl.intersectWithLine(ln).asArray())   # expect (0.0, 0.0, 1.0)
```

## 4. Fret-zero location and neck direction

Fret 0 comes from the fret-zero reference: a planar face is intersected with
the (extended) center line via `Plane.intersectWithLine`; a sketch line uses
`fret_math.closest_point_parameter` (pure Python, unit-tested) to find the
nearest point on the center line. The neck direction is simply "from fret 0
toward the farther endpoint of the selected center line", optionally flipped
by the checkbox — no face normals involved, so there is no
`isParamReversed`/evaluator orientation risk. The **nut offset** then
translates the fret-zero anchor point (and with it the whole local frame)
along the neck in 3D — local-frame math never sees the offset. Multi-scale
layouts are anchored in `fret_math.fanned_positions` so the rearmost end of
the fanned nut line is at local x = 0: nothing reaches behind the reference.

## 5. `Sketches.addWithoutEdges`

Used so the fretboard face outline is NOT auto-projected into the slot sketch —
projected outlines would slice every overhanging rectangle into several
profiles and break the profile-based cuts. `_create_sketch` falls back to
plain `add()` + deleting `isReference` curves if the method is missing:

```python
print([m for m in dir(d.rootComponent.sketches) if 'add' in m.lower()])
```

## 6. `addThreePointRectangle` corner semantics

`fret_math.segment_rectangle` returns (corner1, corner2, corner3) where
corner1→corner2 is one full side (the slot-width side) and corner3 is the
diagonally opposite corner. Draw one and check the sides:

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
sk = d.rootComponent.sketches.add(d.rootComponent.xYConstructionPlane)
sk.sketchCurves.sketchLines.addThreePointRectangle(
    adsk.core.Point3D.create(0, 0, 0),
    adsk.core.Point3D.create(1, 0, 0),
    adsk.core.Point3D.create(1, 3, 0))
```

## 7. Radius cut internals (verify on first use)

`_apply_radius` builds two transverse planes and loft-cuts an arc profile pair
over the board. API assumptions to check if it misbehaves:

- The base plane comes from `setByAngle(construction line, 90°, topFace)`,
  where the line is drawn by the add-in in the slot sketch, exactly across the
  neck at fret 0. This keeps the plane perpendicular to the neck even for
  fanned layouts (whose nut is skewed) and keeps all references inside the
  board's component. The arc half-span is `params.radius_span` — widened to
  the board's widest half-width when the taper outline is drawn.
- `ConstructionPlaneInput.setByOffset(basePlane, distance)` — offset sign is
  taken along the plane's normal; the code resolves the sign with a dot
  product against the neck direction. If the loft lands on the wrong side, the
  offset-sign convention differs — flip `sign` in `_apply_radius`.
- A radius layout has no flat top face afterwards (the loft consumes it), so
  edit mode allows an empty top selection when the metadata records a radius:
  build_slots deletes the old loft first (restoring the face) and re-resolves
  it via the stored `top_token` (`_restore_top_entity`). For the same reason
  the board body and all selection tokens are captured BEFORE any feature is
  created in `build_slots`.
- Transformed (rotated/moved) occurrences are only partially handled: normals
  come from selection proxies (root space), but the construction-plane normal
  used for the offset sign is component space. If a rotated occurrence
  misbehaves, the loft errors out rather than cutting silently wrong.
- `SketchArcs.addByCenterStartSweep(center, start, sweep)` — positive sweep is
  assumed counter-clockwise in sketch coordinates, so sweeping `2θ` from the
  `α−θ` endpoint passes through the crown. A backwards arc would make the
  profile open (caught: `profiles.count == 0`).
- `LoftFeatures` cut with `participantBodies = [board]` keeps the radius from
  slicing the nut or neck.
- All of it runs inside preview too; on any failure the created planes and
  sketches are deleted and a `FretSlotsError` explains what to try.

## 8. Tuner layout internals (added with v1.1)

- Pure math lives in `fret_math.tuner_reference` (pytest-covered): station
  interleaving for splits, reversed-headstock mirroring, plan↔face mapping
  with the hinge (`plan = break_offset + face·cos θ`), clearance checks,
  per-string head extensions. The command only adapts params and draws.
- **Tilted plane chain** (θ > 0, `_apply_tuner_plane`): offset construction
  plane `setByOffset(native_top, −face_drop)` → hinge sketch on it → hinge
  line (perpendicular to the center line at `break_offset` behind the datum)
  → angled plane `setByAngle(hinge_line, θ, reference)` → tuner sketch on
  that plane. Neither the offset sign nor the angle sign is trusted: each
  candidate plane gets a probe sketch, and a known 3D point (the dropped
  hinge center / a point 2 cm down the face) must map to sketch z ≈ 0, else
  the other sign — and for setByAngle also the other reference planarEntity
  (`native_top`, then the offset plane) — is tried; all-fail raises
  `FretSlotsError` instead of drawing a flipped reference. Pre-flight:

  ```python
  import adsk.core, adsk.fusion, math
  app = adsk.core.Application.get()
  d = adsk.fusion.Design.cast(app.activeProduct)
  root = d.rootComponent
  planes = root.constructionPlanes
  pi = planes.createInput()
  pi.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByReal(-0.6))
  off = planes.add(pi)
  sk = root.sketches.add(off)
  ln = sk.sketchCurves.sketchLines.addByTwoPoints(
      adsk.core.Point3D.create(0, -3, 0), adsk.core.Point3D.create(0, 3, 0))
  pi = planes.createInput()
  pi.setByAngle(ln, adsk.core.ValueInput.createByReal(math.radians(17)),
                root.xYConstructionPlane)
  ang = planes.add(pi)   # must succeed with the axis line OFF the reference plane
  print(ang.geometry.normal.asArray())
  ```

- The face frame inside the tuner sketch is measured, not assumed: the
  origin/axes come from mapping three root-space probe points
  (hinge center, a point 2 cm down the face, a LATERAL point **dropped onto
  the hinge plane** — projecting a top-plane lateral point would smear
  `face_drop·sin θ` into the longitudinal axis).
- The angle input uses `'deg'` units (`addValueInput(..., 'deg', ...)`);
  `.value` returns radians. `_read_values.read_nonnegative` accepts 0 —
  the standard `read_length` rejects it. Prefill for zero-valid fields
  (angle, break offset, face drop, row offset, clearance) bypasses
  `set_value`'s `> 0` guard, like `nut_slot_offset`.
- Metadata is **version 6**: tuner params plus four tracked tokens
  (`tuners_token`, `tuner_angled_plane_token`, `tuner_hinge_token`,
  `tuner_offset_plane_token`), deleted in that (consumed-last) order by
  `_delete_tracked` — so toggling the feature off on edit removes the whole
  chain. v5 sketches load fine (missing keys default to feature-off).
- With tuners on, the String Layout head extensions are computed per string
  to reach each post (plan station × cos θ mapping included); the manual
  `headstock_length` input/settings slot is never overwritten.

## 9. Misc

- `Sketch.isLightBulbOn = True` re-shows a sketch that a feature consumed
  (plain `isVisible` is read-only).
- `ValueCommandInput.value` while the expression is invalid mid-typing: the
  add-in never relies on it (`isValidExpression` is checked first), but the
  template's `get_inputs()` in `Fusion360Utilities` reads `.value` on every
  event. If a Fusion release makes that raise, wrap a tolerant copy of
  `get_inputs` in the command modules — do not edit the verbatim
  `Fusion360Utilities` copy.
- Occurrences: geometry from proxies arrives in root space; `_create_sketch`
  creates the sketch in the native component and maps points through a sketch
  proxy (`createForAssemblyContext`). Verified only for the single-occurrence
  case; deep nesting is best avoided (edit the component in place instead).
- Edit mode: the sketch attribute stores the three selections as `entityToken`
  strings plus every parameter and the tokens of all created objects
  (metadata version 5); `_prefill_from_sketch` re-resolves selections with
  `design.findEntityByToken` and pushes them into the selection inputs with
  `addSelection`. Rebuilding replaces the slot sketch's curves *in place*
  (never deletes the sketch object) so a manual Press Pull cut recomputes
  instead of dying with a lost-profile error; everything else the add-in
  created (cuts, radius, extra sketches, planes) is deleted via
  `_delete_tracked` and recreated.
- Separate nut depth: `_partition_slot_profiles` tells the nut profile apart
  from the fret profiles by `areaProperties().area` — a scalar, immune to
  coordinate-space ambiguity. When nut and fret widths are within 1.5× of
  each other, partitioning is skipped and everything cuts at the fret depth.
- After a build, every created curve is locked (`isFixed = True`, i.e. fully
  defined) and only the String Layout and Bridge Mark sketches stay visible;
  the slot/outline sketches are hidden only when their cut exists, and the
  radius tooling (profile sketches + planes) is always hidden.
- New layouts wrap everything they created in one timeline group
  (`timeline.timelineGroups.add(start, end)`); edits cannot join it because
  recreated features land at the end of the timeline and groups must be
  contiguous.
