# Developer notes — API assumptions and pre-flight checks

The add-in leans on a few Fusion 360 API behaviors that are worth verifying
once per Fusion release, in **Utilities → Text Commands** (switch the input
mode from `Txt` to `Py`). Paste one block at a time.

## 1. The created-board flow (v2.0) and its canonical frame

The command no longer cuts a pre-existing board — it CREATES the fretboard:
a new component (`activeComponent.occurrences.addNewComponent(identity)`),
everything drawn with **native objects in that component's own space**, in a
canonical frame: fret 0 at the origin, neck along +x, board top on the XY
plane, up +z. There are no selections, no occurrence proxies, no
`createForAssemblyContext`, and no face references to go stale — construction
planes (XY, yZ) are the only sketch/feature references.

Feature order inside `build_slots` (do not shuffle):

1. **Outline sketch → board extrude** (`_extrude_board`, NewBody, downward so
   the top face stays at z = 0 — verified via the body's bounding box, not
   the extent sign convention). Everything else cuts into this body.
2. Slot sketch curves (the sketch object itself is created/kept first — it
   carries the metadata attribute), bridge mark, string layout, tuner
   sketches/planes.
3. Radius loft (participant-limited to the board body).
4. Slot/nut extrude cuts (profiles from the slot sketch, participant board).

On failure, a NEW layout is cleaned up by deleting the whole occurrence; an
EDITED layout deletes the recreated pieces feature-before-consumed-object
(see `_delete_tracked` order) and leaves the user's slot sketch for undo.

## 2. `isValidResult` keeps the preview and skips execute

`CreateFretSlotsCommand.on_preview` sets `args.isValidResult = True` after a
successful build; Fusion then reuses the preview as the final result on OK and
does not fire the execute event. `on_execute` keeps a `_preview_ok` guard as a
fallback either way, so a behavior change here degrades gracefully (worst case:
geometry is rebuilt once on OK).

## 3. `addThreePointRectangle` corner semantics

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

## 4. Board extrude direction is probed, not assumed

`_extrude_board` extrudes the outline with a −thickness distance first and
checks `feature.bodies.item(0).boundingBox.maxPoint.z <= 1e-4` (the board
must hang BELOW the sketch plane so slot cuts measured downward land in it);
a body that comes out above the plane is deleted and redone with the
opposite sign. The same distrust-and-probe idea is used for every
construction plane (radius stations, tuner planes): a sketch is added on the
candidate plane and a known component-space point must map to sketch z ≈ 0.

## 5. Radius cut internals

`_apply_radius` builds two transverse planes and loft-cuts an arc profile
pair over the board. API assumptions to check if it misbehaves:

- Station planes come from `setByOffset(yZConstructionPlane, ±station_x)` —
  the yZ plane is exactly perpendicular to the neck (+x) in the canonical
  frame, for fanned layouts too. The offset SIGN is probed per station (see
  §4); if both signs miss, the build aborts with a FretSlotsError.
- The loft covers `back_x = −(2 cm + nut skew + board setback)` to 1 cm past
  the board end, and the arc half-span is `params.radius_span` — widened to
  the board's widest half-width so no flat shoulders remain along the edges.
- `SketchArcs.addByCenterStartSweep(center, start, sweep)` — positive sweep is
  assumed counter-clockwise in sketch coordinates, so sweeping `2θ` from the
  `α−θ` endpoint passes through the crown. A backwards arc would make the
  profile open (caught: `profiles.count == 0`).
- `LoftFeatures` cut with `participantBodies = [board]` keeps the radius from
  slicing anything else.
- Validation guarantees the edge drop of the radius is smaller than the board
  thickness (else the loft would split the board lengthwise).
- All of it runs inside preview too; on any failure the created planes and
  sketches are deleted and a `FretSlotsError` explains what to try.

## 6. Tuner layout internals

- Pure math lives in `fret_math.tuner_reference` (pytest-covered): station
  interleaving for splits, reversed-headstock mirroring, plan↔face mapping
  with the hinge (`plan = break_offset + face·cos θ`), clearance checks,
  per-string head extensions. The command only adapts params and draws.
- **Tilted plane chain** (θ > 0, `_apply_tuner_plane`): offset construction
  plane `setByOffset(xYConstructionPlane, −face_drop)` → hinge sketch on it →
  hinge line (across the neck at `break_offset` behind fret 0) → angled plane
  `setByAngle(hinge_line, θ, reference)` → tuner sketch on that plane.
  Neither the offset sign nor the angle sign is trusted: each candidate
  plane gets a probe sketch, and a known component-space point (the dropped
  hinge center / a point 2 cm down the face) must map to sketch z ≈ 0, else
  the other sign — and for setByAngle also the other reference planarEntity
  (the XY plane, then the offset plane) — is tried; all-fail raises
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
  origin/axes come from mapping three component-space probe points
  (hinge center, a point 2 cm down the face, a LATERAL point **dropped onto
  the hinge plane** — projecting a top-plane lateral point would smear
  `face_drop·sin θ` into the longitudinal axis).
- The angle input uses `'deg'` units (`addValueInput(..., 'deg', ...)`);
  `.value` returns radians. `_read_values.read_nonnegative` accepts 0 —
  the standard `read_length` rejects it. Prefill for zero-valid fields
  (angle, break offset, face drop, row offset, slant, clearance, board
  setback) bypasses `set_value`'s `> 0` guard.
- With tuners on, the String Layout head extensions are computed per string
  to reach each post (plan station × cos θ mapping included); the manual
  `headstock_length` input/settings slot is never overwritten.

## 7. Metadata and edit mode

- Metadata is **version 7** (created-board flow): every parameter plus the
  tokens of all created objects — `board_token` (the board extrude),
  `taper_token` (the outline sketch it consumes), cut/radius/tuner chains.
  `_delete_tracked` deletes them in consumed-last order; `_find_fret_sketches`
  lists only v7+ sketches in the Edit dropdown — **older (selection-based)
  layouts cannot be rebuilt** because the geometry they cut belonged to the
  user, not the add-in.
- Rebuilding replaces the slot sketch's curves *in place* (never deletes the
  sketch object) so a manual Press Pull cut recomputes instead of dying with
  a lost-profile error; everything else the add-in created — including the
  board body — is deleted via `_delete_tracked` and recreated. A user
  feature that referenced the old board geometry will need reattaching after
  an edit (same caveat as any recreated body).
- Settings migration: v1 settings stored `nut_slot_offset_expr` (layout
  shifted into the board); `load_settings` maps it to `board_setback_expr`
  (board extended behind the nut) when the latter is absent.
- The **Start from** dropdown (`edit_target`) holds `NEW_LAYOUT_LABELS` first
  and the editable layouts after them, so `_edit_sketch_from_inputs` indexes
  `self._edit_sketches` with that offset — adding a create entry means the
  offset moves with the tuple, not with a literal. Selecting a New entry
  refills the dialog through `_apply_settings` from either `DEFAULTS` or
  `self._settings` (the last-used dict loaded in `on_create`); it writes
  nothing to `settings.json` — only `on_destroy` does, on OK. The four
  `*_INPUTS` tables at the top of the module are the single settings-key ↔
  input-id mapping, read by `_apply_settings` and the `on_destroy` save loop;
  a new persisted input must be added to a table *and* to `on_create`.
  Programmatic value changes do not re-enter `on_input_changed` (same
  assumption `_prefill_from_sketch` already relies on).

## 8. Misc

- `Sketch.isLightBulbOn = True` re-shows a sketch that a feature consumed
  (plain `isVisible` is read-only). The outline sketch is always hidden
  after the build (its geometry lives on as the board body).
- `ValueCommandInput.value` while the expression is invalid mid-typing: the
  add-in never relies on it (`isValidExpression` is checked first), but the
  template's `get_inputs()` in `Fusion360Utilities` reads `.value` on every
  event. If a Fusion release makes that raise, wrap a tolerant copy of
  `get_inputs` in the command modules — do not edit the verbatim
  `Fusion360Utilities` copy.
- All geometry is drawn through native sketches of the fretboard component,
  so `modelToSketchSpace`/`sketchToModelSpace` operate in that component's
  space and occurrence transforms of the parent assembly are irrelevant.
- Separate nut depth: `_partition_slot_profiles` tells the nut profile apart
  from the fret profiles by `areaProperties().area` — a scalar, immune to
  coordinate-space ambiguity. When nut and fret widths are within 1.5× of
  each other, partitioning is skipped and everything cuts at the fret depth.
- After a build, every created curve is locked (`isFixed = True`, i.e. fully
  defined) and only the working-reference sketches (String Layout, Bridge
  Mark, Tuner Layout) stay visible; the slot sketch is hidden only when its
  cut exists — and explicitly re-shown otherwise, since an edit may inherit
  a hidden sketch from a run whose cut is now unchecked — and the outline
  sketch and radius/tuner tooling are always hidden.
- New layouts wrap everything they created — including the new component's
  occurrence — in one timeline group
  (`timeline.timelineGroups.add(start, end)`); edits cannot join it because
  recreated features land at the end of the timeline and groups must be
  contiguous.
- Validation knows the board now: slot/nut cut depths must be smaller than
  the board thickness, the radius edge drop must not eat the full thickness,
  and a nut-seat cut requires a board setback — the board front edge runs
  PARALLEL to the (possibly fanned) nut line, so seat coverage is
  perpendicular (`setback * cos(fan)`, see
  `fret_math.nut_seat_setback_required`) and the fan skew itself never
  provides material under the seat.
