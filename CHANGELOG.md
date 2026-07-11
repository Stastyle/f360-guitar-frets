# Changelog

## 1.1 — July 2026

### Tuner layout v1 (Hardware group)

Built from the researched, reviewed spec in
[HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md) (multi-agent lutherie research
with fact-checked dimensions).

- **Two placement modes**: *Straight pull* — posts on each string's extended
  plan line, global interleaved stations for splits (3+3: E, e, A, B, D, G)
  so converging inner strings never collide; *Pattern (two rows)* — fixed
  rows relative to the center line with an optional per-station slant
  (0 = classic Gibson 3+3 at 35 mm pitch; 7.14 mm per station = Fender's
  17° inline row), with nut→post guide lines on flat headstocks.
- **Any split** via a bass-side post count (6+0, 3+3, 4+2, bass 4+0/2+2) on
  1–12 strings, plus **Reversed headstock** (true mirror semantics: a
  reversed inline puts the low E farthest; symmetric 3+3 pattern is a no-op).
- **Tilted headstocks** (0–25°, presets in the tooltip: 10/14/17): posts are
  drawn on an angled construction plane in TRUE face distances — offset
  plane (face drop) → hinge line (break offset behind the nut) → `setByAngle`
  plane — with probe-verified directions that fail loud instead of drawing a
  flipped reference. Flat (0°) stays on the fretboard plane. Single-scale
  only for now.
- Hole circles + center points as reference geometry (10 mm / 11/32" /
  custom), housing clearance warnings, plan-view side-pull angle readout,
  and string-line head extensions that reach each post automatically (the
  manual headstock length is preserved).
- Layout metadata bumped to v6 (older sketches still load); full edit-mode
  round-trip for all tuner parameters.
- Deferred from the spec to keep v1 honest: per-string station override
  table in the dialog, guides on tilted planes, tilted multi-scale, hole
  cutting, bass hardware presets (dimension verification pending).

## 1.0 — July 2026

First release, built up in one intensive development cycle. Everything lives
in a single command, **Create Fret Slots**, on the Utilities tab ("Guitar
Frets" panel) and in Solid → Create.

### Fret layout core

- Fret slot rectangles at `scale × (1 − 2^(−n/12))`, slot width/length and
  fret count as inputs; pure-Python math module with a pytest suite (verified
  against the standard 25.5" fret tables; fret 12 = scale/2).
- Flexible **fret-zero reference**: nut face, fretboard end face, or a sketch
  line across the neck. Fret 0 = its intersection with the center line.
- Neck direction from the center line (frets march toward its far end) with a
  **Flip direction** checkbox; guided selection flow — each pick activates the
  next input, with 1/3 → 2/3 → 3/3 prompts at the cursor.
- **Nut slot** with its own width, cut *backward* from fret 0 (neck-side edge
  exactly on the reference), and its own **cut depth** (separate extrude,
  identified by profile area).
- **Nut offset**: shifts fret 0 and the entire layout along the neck (for a
  nut slotted inside the fretboard, or a compensated nut). The info box
  reports the exact nut-seat span relative to the reference.
- **Bridge mark** at the theoretical scale length, in its own always-visible
  sketch.

### Multi-scale (fanned frets)

- Bass + treble scales with a chosen perpendicular fret; nut, bridge,
  strings and taper all fan consistently.
- Anchored so the rearmost end of the fanned nut line sits exactly on the
  fret-zero reference — the whole fan lands on the board (manufacturable).

### Strings, outline, radius, cuts

- **String Layout** sketch: per-string lines from the bridge through the nut,
  extended toward the headstock for tuner alignment (string count + spreads
  at nut/bridge as inputs).
- **Fretboard Outline** sketch: tapered board outline from nut width + bridge
  spread (constant edge margin along the outer strings), with optional
  **Cut board to outline** (Intersect extrude through the blank).
- **Fretboard radius**: single or compound, as a loft cut between arc
  profiles on true-transverse planes; arc span auto-widens to the board's
  widest point; participant-body limited to the board.
- **Cut slots (Push/Pull)**: fret slots and nut seat cut in one OK, shown in
  the live preview. Feature order: sketches → radius → outline cut → slot/nut
  cuts (later steps must not touch stale face references).

### Editing and housekeeping

- **Edit dropdown**: pick any existing layout — all parameters *and* the
  original selections load back from metadata stored on the sketch (entity
  tokens). Rebuild replaces curves in place; every feature the add-in created
  is recreated (or removed when unchecked). Radius layouts are editable even
  though the loft consumed the flat top face (it is restored and re-resolved
  during rebuild).
- Everything a new layout creates is wrapped in a named **timeline group**.
- All created sketch geometry is locked (fully defined); after a cutting run
  only String Layout and Bridge Mark stay visible.
- Last-used values persist across sessions (`settings.json`); expressions are
  stored as typed (`25.5 in` stays `25.5 in`).
- Live preview reuse (`isValidResult`), validation messages in the dialog's
  info box (12th-fret sanity readout, radius edge-drop, nut-seat span).

### Removed along the way

- The separate **Select Fret Slots** button (pre-select profiles for a manual
  Press Pull) — superseded by the in-dialog cut options.

### Planned (placeholders in the dialog)

- Tuner hole layout and bridge/saddle hardware footprints — researched,
  reviewed and specified in [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md)
  (2026-07-11); tuner layout v1 is next up.
