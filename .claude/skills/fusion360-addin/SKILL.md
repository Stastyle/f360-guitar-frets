---
name: fusion360-addin
description: Build, extend and debug Autodesk Fusion 360 add-ins and scripts in Python (the adsk.core / adsk.fusion API) — scaffold a complete add-in project in one command, design a command dialog with live preview and persisted settings, generate sketches / bodies / construction planes / cuts in a new component, make layouts editable later via attributes, register toolbar buttons and icons, keep the math pytest-able, and write the README/DEV_NOTES. Use it whenever the user mentions Fusion 360 (or just "Fusion"), a תוסף / add-in / plugin / script for Fusion, adsk.core, adsk.fusion, CommandInputs, a .manifest add-in, "Scripts and Add-Ins", or wants to automate CAD geometry (sketch, extrude, construction plane, timeline) in Fusion — even if the word "add-in" never appears. Also use it to debug a traceback or misbehaving preview, edit mode, settings or toolbar button in an existing Fusion add-in.
---

# Fusion 360 add-in development

Distilled from building GuitarFrets (a ~2k-line production add-in with a live
preview, edit mode, settings, multi-sketch/plane/loft geometry) through
several release cycles. Everything below exists because its absence cost a
debugging round with the user — who is the only one who can run Fusion.

## The one constraint that shapes everything

**Fusion cannot run here.** Not in this sandbox, not in CI. The user installs
the add-in, clicks, and pastes back a traceback from a message box. So:

- Put every deterministic computation in a **pure-Python math module with no
  `adsk` import** and test it with pytest here. The Fusion-facing code only
  adapts params and draws.
- Make the Fusion-facing code **self-verifying and self-cleaning**: probe
  sign conventions instead of assuming them, fail with a clear message,
  delete what a failed run created.
- Run `scripts/check_addin.py <Folder>` before every handoff: it compiles
  the code, imports the package with a stub `adsk` (catches import-time
  errors, wrong absolute imports, third-party imports), and checks the
  manifest and icon folders.
- Keep `DEV_NOTES.md` with the API assumptions the code makes and a Text
  Commands snippet that verifies each one (`references/preflight-snippets.md`),
  so a new Fusion release is a 2-minute check, not an archaeology session.

## Starting a new add-in

```bash
python <skill>/scripts/scaffold_addin.py <repo-dir> --name MyAddin \
    --command-name "Create Bracket" --description "One sentence for manifest and README"
```

It creates the installable folder `<repo>/MyAddin/` (entry module with
toolbar registration, manifest with a fresh UUID, a **working example
command**, pure math module, the verbatim `Fusion360Utilities` framework
(MIT, Patrick Rainsberry), generated icons), plus `tests/`, `scripts/make_icons.py`,
README, CHANGELOG, DEV_NOTES and `.gitignore`, then runs the checker.
`python -m pytest tests/` passes out of the box.

The example command (a plate with a hole grid) is not a toy to delete; it
is the structure to keep: settings tables, *Start from* dropdown (last used
/ defaults / rebuild an existing layout), validation → info box, preview
that becomes the result, build in a new component with metadata, timeline
group and failure cleanup. Replace the inputs and the geometry, keep the
skeleton. Adding an input is a 3-place change (DEFAULTS, a table, `on_create`)
— `references/command-dialog.md` has the checklist.

When extending an **existing** add-in instead, read its DEV_NOTES/README
first, then compare its command module against the skeleton above; most
bugs reported on older add-ins are a missing piece of it (no preview guard,
settings saved on Cancel, no cleanup on failure, absolute imports).

## Architecture rules (and why)

1. **Three layers, one direction of imports**: entry module (`run`/`stop`,
   toolbar) → command module (dialog, validation, build) → math module
   (pure Python). `constants.py` is adsk-free so tests can import it.
2. **Internal units are cm and radians.** The math works in cm; dialogs show
   and store the user's *expressions* (`'25.5 in'`); metadata on geometry
   stores cm values. Format for display with
   `unitsManager.formatInternalValue(value, defaultLengthUnits, True)`.
3. **Stdlib only** inside the add-in (Fusion ships its own Python with no
   pip packages). Icons are generated with `struct` + `zlib`; JSON for
   settings and metadata.
4. **Create, don't select.** Build in a new component in a documented
   canonical frame (datum at origin, main axis +X, top face on XY) and
   sketch only on that component's construction planes. Selections bring
   occurrence proxies, assembly transforms and references that go stale
   after the first cut; the created-component design has none of that.
5. **Probe, don't assume.** Offset-plane sign, extrude direction, cut
   direction, `setByAngle` sense, sketch axis orientation on derived
   planes: verify each with a mapped probe point / bounding box and try the
   other sign; raise a domain error when all candidates fail.
6. **Everything a run creates is tracked and reversible.** Metadata (JSON in
   an attribute on the first sketch) holds every parameter in cm plus the
   `entityToken` of every created object; edit mode deletes them
   feature-before-consumed-sketch and rebuilds; a failed new build deletes
   its occurrence.
7. **The preview is the build.** `on_preview` builds for real and sets
   `args.isValidResult = True`; `on_execute` is a guarded fallback. Nothing
   escapes `on_preview` as an exception (it would message-box every
   keystroke) — expected problems go to the info box.
8. **Settings are table-driven**, type-checked on load, whitelisted for
   dropdowns, migrated when keys are renamed, written only on OK from a
   fully built dialog.
9. **Validation returns a message either way** — problems *or* a sanity
   readout (dimensions in document units, counts, non-blocking warnings).
   Every message says what to change.
10. **Document as you build**: README (install steps, usage with defaults,
    canonical frame, notes and limits, development layout), CHANGELOG per
    version, DEV_NOTES per API assumption. The tooltip is where the user
    actually reads a default's provenance — put it there too.

Details and code for each rule: `references/api-gotchas.md` (API facts by
topic), `references/command-dialog.md` (dialog/settings/edit mode),
`references/geometry.md` (component, probing, metadata, cleanup).

## Workflow for a feature

1. **Pin the geometry on paper first**: frame, parameters, formulas, edge
   cases (zero values, degenerate sizes, fanned/angled variants). For
   domain-heavy features (hardware dimensions, standards), research into a
   `*_RESEARCH.md` with verified numbers before coding — defaults that are
   wrong by a millimetre are worse than no feature.
2. **Math module + tests first** (`tests/test_*.py`): known reference values,
   symmetry, monotonicity, degenerate inputs raising `ValueError`. Run
   `python -m pytest tests/ -q`.
3. **Dialog**: inputs with tooltips, visibility rules, settings table rows,
   validation rules with actionable messages.
4. **Build**: in order body → sketches → shaping → cuts; metadata tokens for
   every created object; cleanup path; timeline group; lock curves; hide
   tooling, keep references visible.
5. **Static checks**: `python scripts/check_addin.py <Folder>` and pytest.
   Re-read the diff adversarially: what happens on Cancel, on an invalid
   expression mid-typing, when a feature is off, on edit of a layout made
   with the previous version, on a second run in the same document?
6. **Handoff to the user for a Fusion run.** Tell them exactly what to click
   and what to look for; ask for the message-box traceback or the Text
   Commands output when something is off. Iterate.
7. **Docs**: README usage + notes/limits, CHANGELOG entry, DEV_NOTES for
   any new API assumption, bump the manifest version for a release.

## Debugging an add-in that misbehaves

| Symptom | Usual cause |
|---|---|
| Button does nothing / no dialog | handler not kept referenced; exception in `on_create` swallowed — add `ui.messageBox(traceback.format_exc())` |
| `ModuleNotFoundError` for your own module | absolute import inside the add-in; use `from .module import …` |
| `No module named numpy/PIL/…` | third-party import; Fusion's Python is stdlib-only |
| Dialog opens with wrong/old values, or defaults after Cancel | settings saved on Cancel / from a half-built dialog; check `on_destroy` guards |
| Message box on every keystroke | exception escaping `on_preview`; catch and write to the info box |
| Geometry built twice on OK | `isValidResult` not set, or `_preview_ok` guard missing |
| Cut/extrude goes the wrong way or "removes nothing" | sign convention assumed; probe and retry the other sign |
| Sketch on an offset/angled plane is mirrored or shifted | sketch axes assumed; measure the frame with mapped probe points |
| Edit of an old layout fails with lost profile / deleted entity | deletion order (feature before consumed sketch), or the tagged sketch was deleted instead of having its curves replaced |
| Dropdown crash `selectedItem` is None | selection cleared before the new item was selected; set only the target `isSelected = True` |
| Button duplicated after re-run | `stop()` did not delete controls/panel/definition |
| Change seems ignored | module cache; Stop + Run the add-in, else restart Fusion |

For anything plane/sign related, hand the user the matching snippet from
`references/preflight-snippets.md` and reason from its output. For stepping
through code, Fusion's Scripts and Add-Ins dialog can launch the add-in
under the VS Code debugger (right-click → *Debug*); a `ui.messageBox` with
`traceback.format_exc()` at the failing spot is usually faster.

## Delivery checklist

- `python -m pytest tests/ -q` green; `check_addin.py` passes.
- Manifest version bumped when behavior changed; CHANGELOG entry written.
- README install steps still match (inner folder name, tab/panel names).
- `settings.json` gitignored; no absolute paths; no third-party imports.
- Every new API assumption has a DEV_NOTES line and a verifying snippet.
- Commit message explains *why* (the user-visible problem), not just what.

## Files in this skill

- `scripts/scaffold_addin.py` — new project from the templates (runs the checker).
- `scripts/check_addin.py` — static sanity check of any add-in folder, no Fusion needed.
- `scripts/make_icons.py` — stdlib PNG toolbar icons from a 16×16 ASCII glyph.
- `assets/template/` — the scaffold templates (entry, manifest, command, math, tests, docs).
- `assets/Fusion360Utilities/` — the verbatim command framework (MIT, Patrick Rainsberry); never edit it in a project, wrap it.
- `references/api-gotchas.md` — API facts by topic (read when touching that topic).
- `references/command-dialog.md` — dialog, settings, Start-from/edit mode patterns.
- `references/geometry.md` — component frame, feature order, probing, metadata, cleanup.
- `references/preflight-snippets.md` — Text Commands snippets to verify assumptions in Fusion.
