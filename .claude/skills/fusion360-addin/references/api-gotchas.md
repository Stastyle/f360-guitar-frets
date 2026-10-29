# Fusion 360 API facts learned the hard way

Each entry: the fact, why it bites, what to do. Everything here was hit while
building a 2,000-line production add-in (GuitarFrets) and is reflected in the
scaffold templates. Items marked *(verify)* are known to vary between Fusion
releases — confirm them with a pre-flight snippet (`preflight-snippets.md`)
when something misbehaves.

## Contents

1. Runtime and packaging
2. Units and values
3. Command lifecycle and event handlers
4. Dialog inputs
5. Sketches
6. Construction planes and sign conventions
7. Features (extrude, cut, loft)
8. Components, attributes, tokens, timeline
9. Toolbar, panels, icons
10. Settings and files

---

## 1. Runtime and packaging

- **Fusion runs its own Python, standard library only.** Add-ins cannot
  `pip install`; `numpy`, `PIL`, `requests` are not there. Keep every helper
  pure stdlib — the icon generator writes PNGs with `struct` + `zlib` for
  exactly this reason. `check_addin.py` flags third-party imports.
- **The folder, the entry `.py` and the `.manifest` share one name**
  (`GuitarFrets/GuitarFrets.py` + `GuitarFrets/GuitarFrets.manifest`).
  Fusion imports the entry module as `<Folder>.<Folder>` with the folder as
  its package (no `__init__.py` needed), so **sibling modules must be imported
  relatively**: `from .MyCommand import MyCommand`, `from . import my_math`.
  An absolute `import my_math` works in pytest and fails inside Fusion —
  and if that import sits inside a handler (`on_create`), Run succeeds and
  the failure only shows on the first click ("Command created failed",
  no dialog). Keep imports at module top so a typo fails at Run time.
- **The pure-math module imports nothing from `adsk`.** That is what makes
  it testable with pytest outside Fusion (`sys.path.insert(0, '<Folder>')`
  in the test, then `import my_math`). Keep `constants.py` adsk-free too.
- **Module caching** *(verify)*: after editing a sub-module, Stop and Run
  the add-in again from Scripts and Add-Ins; if a change still seems
  ignored, restart Fusion — Fusion caches imported sub-modules aggressively.
- **Where Fusion keeps add-ins** (useful when the user asks where to copy
  the folder, and the path tracebacks show): Windows
  `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\<Name>\`, macOS
  `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/<Name>/`.
  A git clone anywhere else works too — the green **+** in Scripts and
  Add-Ins registers any folder.
- **Scripts vs add-ins**: a script (`"type": "script"`) runs `run()` once and
  is auto-terminated unless it calls `adsk.autoTerminate(False)` to keep a
  dialog alive; an add-in has `run()`/`stop()` and can run on startup. Use
  an add-in whenever there is a toolbar button.
- **Tracebacks surface only if you show them**: wrap `run()`, `stop()` and
  every handler in `try/except` and `ui.messageBox(traceback.format_exc())`
  (the framework's handlers already do). Otherwise failures are silent.
- `adsk.fusion.Design.cast(app.activeProduct)` is **None outside the Design
  workspace** (Manufacture, Drawing, Simulation). Check it in `on_create`
  (message + return) and in validation.

## 2. Units and values

- **Internal units: centimetres and radians.** `ValueCommandInput.value`
  returns cm no matter what the user typed; `'deg'` inputs return radians.
  The math module works in cm; convert only for display, with
  `unitsManager.formatInternalValue(value, unitsManager.defaultLengthUnits, True)`.
- **Store expressions, compute with values.** `settings.json` keeps
  `input.expression` (`'25.5 in'` stays `'25.5 in'`); metadata on geometry
  stores the cm values (`*_cm` keys). Prefilling from settings sets
  `.expression`; prefilling from metadata sets `.value`.
- **Check `isValidExpression` before reading `.value`** — mid-typing the
  expression is invalid and `.value` is garbage (or raises in some
  releases). The framework's `get_inputs()` reads `.value` unguarded on
  every event; do not edit the verbatim framework — wrap your own reader.
- `addValueInput(id, label, units, ValueInput.createByString(expr))` **raises
  when the stored expression is invalid in this document** (e.g. it named a
  user parameter of another design). Fall back to the default expression
  (see `value_input()` in the template) instead of losing the whole dialog.
- **Zero-valid versus positive-only values** need separate readers
  (`read_length` rejects 0, `read_nonnegative` allows it) and separate
  prefill paths — a `> 0` guard silently drops a legitimate 0 (angle,
  offset, margin).
- `addValueInput(..., 'deg', ...)` for angles; `.value` is radians.
- `ValueInput.createByReal(x)` for internal values, `createByString('5 mm')`
  for user-facing expressions.

## 3. Command lifecycle and event handlers

Order of events for one dialog run:
`commandCreated` → `on_create` (build inputs) → [`inputChanged` → `executePreview`]* → `execute` → `destroy`.

- **Keep handler objects referenced** (a module-level `handlers` list) or
  they are garbage-collected and the events stop firing silently. The
  framework does this; keep it when you write handlers by hand.
- **`args.isValidResult = True` in the preview** makes Fusion keep the
  preview geometry as the final result and **skip `execute`** on OK. Build
  for real in `on_preview`; keep `on_execute` as a fallback guarded by a
  `_preview_ok` flag — if a release changes the behavior the geometry is
  merely rebuilt once.
- **Never let an exception escape `on_preview`.** The framework's handler
  would pop a message box on every keystroke. Catch the domain error class
  and write it to the info box; catch everything else and show the last
  traceback line there.
- **Programmatic input changes do not re-enter the running handler.** A
  `.value`/`.expression`/`isSelected` set from inside `on_input_changed`
  does not call `on_input_changed` again synchronously, so after refilling
  the dialog from settings or metadata, re-apply the visibility rules and
  refresh the info box explicitly. Some writes do produce a *queued*
  input-changed event afterwards (setting the info box `.text` is known
  to), and the framework runs `get_inputs()` before each one — so guard the
  handler against its own writes (`if changed_input.id == 'info_box': return`,
  set `.text` only when it differs) and never leave a dropdown with no
  selected item even for a moment (§4).
- **`on_destroy` fires on Cancel and Esc too.** Check
  `reason == adsk.core.CommandTerminationReason.CompletedTerminationReason`
  before saving anything. Also check that the dialog was fully built (the
  template tests for the info box, its last input) — saving from a dialog
  that bailed out in `on_create` overwrites the user's settings with
  defaults.
- `on_execute` with `inputs.count == 0` means `on_create` returned early
  (no design open) — return quietly.
- `command.setDialogInitialSize(width, height)` — wrap in try/except, it is
  cosmetic.

## 4. Dialog inputs

- Ids are the API; labels are UI. Never branch on `changed_input.name`.
- `addDropDownCommandInput(id, label, adsk.core.DropDownStyles.TextListDropDownStyle)`
  then `listItems.add(name, isSelected, '')` with exactly one item
  selected at creation. **To change the selection, set `item.isSelected = True`
  on the target only** — clearing the others first (or `listItems.clear()`
  and re-adding, or selecting by a name that matches no item) leaves the
  dropdown with no selected item, and the framework's `get_inputs()` reads
  `selectedItem.name` for every dropdown before each event: the symptom is
  an "Input changed event failed … 'NoneType' … 'name'" box that appears
  "sometimes" (whenever the rewriting code path runs).
- The stock framework uses the text **"Input changed event failed"** for
  three handlers (preview, destroy and input-changed); only the line number
  in the traceback tells them apart (277 / 304 / 331 in the verbatim file).
- `addIntegerSpinnerCommandInput(id, label, min, max, step, initial)` —
  when prefilling, ignore a stored value outside `[min, max]` rather than
  clamping it (the spinner would raise).
- `addBoolValueInput(id, label, True, '', initial)` for a checkbox.
- `addGroupCommandInput(id, label)`; add children to `.children`; set
  `.isExpanded` from the feature's on/off setting so a user sees at a glance
  which groups are active.
- `addTextBoxCommandInput(id, label, text, rows, True)` as a read-only info
  box; set `.text` **only when it changed** (every set is an input-changed
  event). Return early from `on_input_changed` when the changed input *is*
  the info box.
- Hide inputs with `isVisible` (a hidden input still has a value — read it
  leniently or skip it); use `isEnabled = False` for "coming soon"
  placeholders.
- Tooltips carry the domain knowledge (defaults, units, references) — the
  README repeats them, the tooltip is where the user actually reads them.
- Selection inputs (`addSelectionInput`) bring occurrence proxies and
  stale-reference problems; the created-component design in `geometry.md`
  avoids them entirely. If you must select, filter aggressively
  (`addSelectionFilter`) and map through `createForAssemblyContext`.

## 5. Sketches

- `component.sketches.add(planarEntity)`; a sketch on a construction plane
  of the *same* component is in that component's space — no occurrence
  transform.
- **Map points, do not assume axes**: `sketch.modelToSketchSpace(Point3D)`
  gives sketch coordinates; the z of the result should be ≈ 0 for a point on
  the sketch plane (that is also how plane directions are *probed*, see §6).
  `sketchToModelSpace` goes back.
- `sketch.isComputeDeferred = True` while adding many curves, `False` in a
  `finally` — otherwise every curve triggers a solve.
- `addThreePointRectangle(p1, p2, p3)`: p1→p2 is one full side, p3 is the
  diagonally opposite corner.
- `SketchArcs.addByCenterStartSweep(center, start, sweep)`: positive sweep
  is counter-clockwise in sketch coordinates *(verify)*; a backwards arc
  leaves an open profile — detect it with `sketch.profiles.count == 0`.
- `sketch.profiles.count == 0` after drawing = the outline is not closed.
- `curve.isFixed = True` locks a curve (fully defined, undraggable). Do it
  for everything the add-in draws.
- `line.isConstruction = True` for reference lines (never form profiles).
- **`sketch.isVisible` is read-only; use `sketch.isLightBulbOn`** to show or
  hide — including to re-show a sketch that a feature consumed.
- `profile.areaProperties().area` is a scalar — the robust way to tell
  profile kinds apart (e.g. a wide nut slot from narrow fret slots) without
  any coordinate-space reasoning.
- A sketch consumed by a feature is auto-hidden; anything that must stay
  visible (reference marks, guide lines) goes in its own sketch.

## 6. Construction planes and sign conventions

- `planes.createInput()`; `setByOffset(plane, ValueInput.createByReal(d))`;
  `setByAngle(line, ValueInput.createByReal(radians), planarEntity)`;
  `planes.add(input)`.
- **Do not trust the sign of an offset or angle** *(verify every release)*.
  Probe: add a sketch on the candidate plane, map a point you *know* lies on
  the intended plane with `modelToSketchSpace`, require `|z| < 1e-3`;
  otherwise delete sketch and plane and try the other sign (and for
  `setByAngle`, the other reference planar entity). Fail with a domain
  error instead of drawing a silently flipped reference.
- `setByAngle` accepts an axis line that lies *off* the reference plane
  *(verify)* — the tuner chain relies on it (hinge line on an offset plane,
  reference = XY plane).
- Component construction planes: `xYConstructionPlane`, `yZConstructionPlane`,
  `xZConstructionPlane`; use them as the only sketch references in a
  generated component so nothing references a face that may change.

## 7. Features (extrude, cut, loft)

- Extrude: `features.extrudeFeatures.createInput(profiles, operation)` with
  an `ObjectCollection` of profiles; `setDistanceExtent(False, ValueInput.createByReal(d))`;
  operations `NewBodyFeatureOperation`, `CutFeatureOperation`,
  `IntersectFeatureOperation`, `JoinFeatureOperation`.
- **Probe the extrude direction** instead of assuming the sign: extrude,
  check `feature.bodies.item(0).boundingBox` (e.g. `maxPoint.z <= 1e-4` for a
  body that must hang below the sketch plane), delete and redo with the
  opposite sign if wrong. For cuts, try `-depth` then `+depth`; a cut that
  removes nothing raises on `add`.
- `participantBodies = [body]` on cut/intersect/loft inputs keeps the
  operation from touching other bodies (and makes overshooting through-cuts
  harmless).
- Loft: `loftFeatures.createInput(operation)`, `loftSections.add(profile)`
  per section, `participantBodies`, `add`.
- **Feature order matters and later steps must not reference faces earlier
  steps change**: body first, then sketches, then shaping cuts (radius loft),
  then the slot/hole cuts. A face reference taken before a cut is stale
  after it.
- `feature.deleteMe()` works for features, sketches, planes, occurrences;
  **delete features before the sketches/planes they consume**.
- `body.name = ...` and `component.name = ...` can raise on name collisions
  — wrap them, the default name is fine.

## 8. Components, attributes, tokens, timeline

- New component: `parent.occurrences.addNewComponent(adsk.core.Matrix3D.create())`
  → `occurrence.component`. `design.activeComponent` is the one the user
  activated — create there, not always in `rootComponent`.
- Deleting the occurrence removes everything built inside it — the simplest
  failure cleanup for a freshly created layout.
- **Attributes** persist JSON on entities across save/reopen:
  `entity.attributes.add(group, name, json_text)`,
  `entity.attributes.itemByName(group, name).value`,
  `design.findAttributes(group, name)` to find all tagged entities —
  `attribute.parent` can be **None** (the entity was deleted; attributes can
  outlive it), always check.
- **Entity tokens** (`entity.entityToken`) survive save/reopen and are the
  way to remember created features/sketches/planes in metadata;
  `design.findEntityByToken(token)` returns a **list**. Cast with
  `adsk.fusion.ExtrudeFeature.cast(entity)` etc. and check `isValid`.
- **Version the metadata** (`'version': N`) and refuse to rebuild layouts
  older than what the current code can honor (hide them from the edit
  dropdown with a note in the README).
- Timeline group: remember `design.timeline.markerPosition` before building;
  after, `timeline.timelineGroups.add(start, markerPosition - 1)` and name
  the group. Groups must be **contiguous** — recreated features of an edit
  land at the end of the timeline and cannot join the original group.

## 9. Toolbar, panels, icons

- Workspace `'FusionSolidEnvironment'`; tab ids `'UtilitiesTab'` (older
  `'ToolsTab'` — try both, then fall back to the first tab); panels
  `'SolidCreatePanel'`, `'SolidScriptsAddinsPanel'`. Own panel:
  `tab.toolbarPanels.add(id, name)`; find it later with
  `ui.allToolbarPanels.itemById(id)`.
- One `commandDefinitions.addButtonDefinition(id, name, tooltip, resources)`
  can back several controls (`panel.controls.addCommand(definition)`).
- `control.isPromoted = True` shows the button on the panel face. Do it
  **once** (persist a `buttons_promoted` flag) — re-promoting on every start
  overrides a user who demoted it.
- `stop()` must delete what `run()` created: controls, then the panel if it
  is empty, then the definition — otherwise the next Run duplicates buttons
  or fails. Wrap each delete in try/except (`obj.isValid` first).
- Resources folder relative to the add-in folder (`'./resources/<cmd>'`)
  holding `16x16.png` and `32x32.png` (+ `-disabled` variants); missing or
  wrongly sized icons give a blank button, not an error.
- Command ids must be globally unique in Fusion (`cmdID_<Addin>_<Command>`).

## 10. Settings and files

- `settings.json` next to the add-in:
  `os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')`;
  gitignore it. Load with per-key **type validation** against `DEFAULTS` and
  **whitelist dropdown values**; **migrate renamed keys** in `load_settings`
  so old files keep working.
- Write it only from `on_destroy` on OK; reload before writing so keys the
  dialog does not own (promotion flag) keep their values.
- Tables (`EXPRESSION_INPUTS`, `SPINNER_INPUTS`, `CHECKBOX_INPUTS`,
  `DROPDOWN_INPUTS`) are the single mapping settings-key ↔ input-id, read
  by the refill path and the save loop — a new persisted input goes into a
  table *and* into `on_create`, nowhere else.
