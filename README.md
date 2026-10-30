# Guitar Frets — Fusion 360 Add-in

Create a complete fretboard, ready to cut, from one dialog — nothing has to
be modeled beforehand. **Create Fretboard** builds the **tapered board body**
itself and puts everything on it: fret slots at mathematically correct
positions (`scale × (1 − 2^(−n/12))`), standard or **multi-scale (fanned)**,
an optional nut slot with its own depth, a bridge mark, **string guide
lines**, an optional single or **compound radius** cut, and a **tuner post
layout** — with the slots cut Push/Pull style in the same operation (or left
as a sketch).

## Installation

1. Download or `git clone` this repository.
2. In Fusion 360 go to **Utilities** tab → **Scripts and Add-Ins** (or press Shift+S).
3. Switch to the **Add-Ins** tab.
4. Click the green **+** ("Add existing script or add-in").
5. Browse to the `GuitarFrets` folder (the inner folder containing
   `GuitarFrets.py`) and select it.
6. Select **GuitarFrets** in the list and click **Run**.
   Optionally check **Run on Startup**.

The button appears in a **Guitar Frets** panel on the **Utilities** tab and in
**Solid → Create**.

## Usage

### Create Fretboard

Open (or create) a design and click **Create Fretboard** — there is nothing
to select and nothing to model first. The add-in creates a **new component**
containing the board body and all layout sketches, in a fixed frame: fret 0
at the component origin, the neck running along **+X**, the board top on the
**XY plane** (the board hangs below it). Move or joint the component to place
the fretboard on your neck.

The **Start from** dropdown at the top of the dialog decides which values you
begin with:

- **New fretboard (last used values)** — the default: your previous run's
  settings, for iterating on the same instrument.
- **New fretboard (default values)** — a genuinely fresh start: every field,
  checkbox and dropdown snaps back to the add-in defaults (25.5 in, 22 frets,
  no multi-scale, no radius, no tuners), as if you had never run it.
- **an existing layout of this document** — loads that fretboard's parameters
  back to edit it in place (see [Changing the layout](#changing-the-layout)).

Switching back and forth is free: the last-used values are still there after
a reset to defaults, and either New entry clears an edit target's parameters.
Nothing is written to disk until you press OK.

Parameters: **scale length** (default 25.5 in — type any unit, e.g. `648 mm`),
**number of frets** (default 22), **fret slot width** (default 0.6 mm, a typical
fret-saw kerf), **fret slot length** across the neck (default 60 mm — keep it a
little wider than the board so the slots overhang the tapered edges; the cut
only removes material where the board actually is), and an optional **nut slot**
with its own width (default 3.5 mm). The nut slot is cut *backward* from fret 0:
its neck-side edge sits exactly on fret 0 and the slot extends away from the
frets, where the nut material goes.

To cut the slots right away, keep **Cut slots (Push/Pull)** ticked and enter
the **slot depth** (default 2.5 mm) — the board, the sketch *and* the cut are
created together, and everything shows in the live preview. Untick it to get
just the board and the sketch.
**Nut slot depth** — shown when **Cut slots** is on — cuts the nut seat at its
own, usually shallower, depth (default 1.5 mm; a second Push/Pull feature,
separate from the fret slots — the nut profile is told apart from the fret
profiles by its area).

#### Fretboard body

The board body is generated from the tapered outline (see below):
**board thickness** (default 6 mm) sets its height, and **board start behind
nut** extends the front edge behind fret 0 (default 0 — the board starts
exactly at fret 0 and the nut sits against its end face). When the nut sits
in a slot *inside* the board, set the setback to at least the nut slot width;
the info box shows the exact span the nut seat covers and warns when part of
it would hang off the board front. **Nut width** and **board end past last
fret** shape the outline: the side edges follow the outer strings with a
constant margin of `(nut width − nut spread) / 2`, from the (possibly
setback) front edge to the last fret plus the overhang.

With multi-scale layouts the fan is anchored so the *rearmost end* of the
angled nut line sits exactly at fret 0 — nothing of the fret layout reaches
behind the board front (at setback 0), so the full fan is on the board and
manufacturable.

**Mark bridge position** (on by default) adds a construction line across the
neck at the full scale length from fret 0 — the theoretical saddle contact
point, for placing the bridge. It is a reference only (never selected or cut).
Remember that a real saddle sits slightly farther for intonation compensation.

#### String layout

**Draw string lines** creates a separate **String Layout** sketch: one straight
line per string, from the bridge line through the nut and continuing past it by
the **headstock line length** — extend them under your headstock to align the
tuners. Inputs: number of strings, string spread (outer string to outer string)
at the nut and at the bridge. The spreads are used even with the lines off:
they define the board taper and the tuner geometry.

#### Tuner layout

Tick **Tuner layout** (in the **Hardware** group) to get a **Tuner Layout**
reference sketch: a hole circle and a center point per post (no cutting —
that stays yours). Two independent controls shape it:

- **Placement** — *Straight pull*: each post sits **on its own string's
  extended line**; enter the first post's distance from the nut and the
  spacing between stations (plan-view values along the neck; defaults are
  Fender's documented 1.650" / 0.919"). With a split (3+3, 4+2) the stations
  interleave between the rows (E, e, A, B, D, G for 3+3) so the converging
  inner strings never collide — an automatic clearance check warns if posts
  get closer than hole diameter + margin. *Pattern (two rows)*: fixed rows
  parallel to the center line (the classic Gibson 3+3 — 35 mm pitch, outer
  strings nearest), with nut→post guide lines and a side-pull angle readout,
  since the strings angle toward the posts.
- **Bass-side posts** — the split: 6 = inline, 3 = 3+3, 4 = 4+2 (bass: 4+0,
  2+2). **Reversed headstock** mirrors it (a reversed inline puts the low E
  farthest, like a reversed Strat).

**Headstock angle** is the key option for tilted headstocks (PRS 10°,
14°, Gibson 17°): with an angle set, the posts are drawn on a **tilted
construction plane** in *true face distances* — exactly like a stick-on
template — hinged at the **break line** behind the nut and dropped **face
drop** below the fretboard top. Drill perpendicular to that face. At 0° the
posts are drawn on the fretboard plane (correct for flat Fender-style
headstocks; note plan-view distances understate on-face distances by
1/cos(angle) on tilted builds — that is why the plane exists). Tilted mode
needs a single-scale layout.

With tuners on, the string-line head extensions automatically reach each
string's own post (the manual **headstock line length** is preserved for
when the feature is off). Hole diameter presets: 10 mm (modern sealed),
11/32" (vintage Kluson), or custom. The dimensional research behind the
defaults is in [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md).

#### Multi-scale (fanned frets)

Tick **Multi-scale** and enter the **bass side scale**, **treble side scale**,
and the **perpendicular fret** (the one that stays straight, commonly 7–9).
Fret midpoints follow the mean scale; the nut, bridge mark, strings, and board
taper all fan accordingly, and the board's front edge stays parallel to the
fanned nut. The bass side is the **left** side looking from the nut toward
the bridge — if the fan leans the wrong way in the preview, swap the two
scale values.

#### Fretboard radius

Choose **Single radius** (one radius, e.g. `9.5 in`) or **Compound radius**
(e.g. `9.5 in` at the nut to `16 in` at the board end). The add-in sketches an
arc profile at each end and loft-cuts the crown off the board body it just
created. Note: the slot cut depth is measured from the original flat top, so
edge slots end up shallower by the radius drop (the info box prints that
number — add it to your slot depth if it matters).

The dialog shows a live preview plus a sanity readout — the 12th fret must sit
at exactly half the scale length. Your last-used values are remembered for the
next run; **Start from → New fretboard (default values)** resets them.

### Cutting manually instead

If you created the board without **Cut slots**, you can always cut yourself:
the Fret Slots sketch stays visible on the board top — window-select its
profiles (or pick them one by one), press **Q** (Press Pull) and enter the
depth as a negative distance (e.g. `-2.5 mm`).

### Changing the layout

Open **Create Fretboard** again and pick your layout in the **Start from**
dropdown at the top of the dialog (its entries come after the two *New
fretboard* ones). All its parameters are loaded back (they are stored
on the slot sketch itself), so you can tweak just the value you care about —
say, the fret count — and press OK. The slots are redrawn in place inside the
same sketch, and the board body and every other managed object (cuts, radius,
strings, tuner chain) are recreated inside the same component — so an existing
manual Press Pull cut on the slot sketch recomputes instead of breaking, but
features *you* built on the old board body will need reattaching. A cut made
with the **Cut slots** checkbox is managed by the add-in: editing recreates it
at the current depth, and unchecking the box removes it.

Layouts made with pre-2.0 versions of the add-in (which cut a board you
modeled yourself) are not listed in the Start from dropdown — they reference
selections the dialog no longer has. Recreate them once with the new flow.

## Roadmap

The goal is a full guitar-design plugin. **Tuner layout v1** (above) shipped
from the researched spec in [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md);
still deferred from it: a per-string station override table in the dialog,
nut→post guides on tilted headstocks, tilted multi-scale, hole cutting, and
bass hardware presets (pending a verification round). Next up is **bridge
hardware** v1 — per-string compensated saddle points and mounting footprint
presets at the bridge mark — also fully specified there.

## Notes and limits

- Slots are simple rectangles overhanging the board taper; they are not trimmed
  to the board edges (the cuts ignore the overhang anyway).
- Layout sketches are tagged with attributes on creation, so the **Start
  from** dropdown keeps finding them after saving and reopening the file.
- Settings are stored in `GuitarFrets/settings.json` (created automatically)
  and are what **New fretboard (last used values)** restores; deleting that
  file has the same effect as always starting from the default values.
- All created sketch geometry is locked (fully defined) — nothing can be
  dragged out of position by accident. After a cutting run, only the working
  references (**String Layout**, **Bridge Mark**, **Tuner Layout**) stay
  visible; the slot sketch, outline sketch, and radius/tuner tooling are
  hidden (the slot sketch stays visible when you skip the cut, so there is
  something to see).
- Everything a new layout creates (component, board body, sketches, planes,
  cuts) is wrapped in one named **timeline group**. Edits append their
  recreated features at the end of the timeline, outside the original group.
- Validation is board-aware: slot and nut depths must be smaller than the
  board thickness, the radius edge drop must leave board material, and a
  nut-seat cut requires a board start behind the nut.

## Development

```
GuitarFrets/                     # the folder you install
├── GuitarFrets.py               # entry: toolbar registration, run()/stop()
├── GuitarFrets.manifest
├── CreateFretSlotsCommand.py    # the command: dialog, validation, build
├── fret_math.py                 # pure-python layout math (no adsk)
├── constants.py                 # attribute names
├── Fusion360Utilities/          # verbatim command-framework template
└── resources/create_fret_slots/ # toolbar icons
tests/test_fret_math.py          # pytest suite for the math
scripts/make_icons.py            # icon generator (pure stdlib PNG writer)
```

- Fret math is pure Python in `GuitarFrets/fret_math.py`; test it without
  Fusion: `python -m pytest tests/`.
- Toolbar icons are generated by `python scripts/make_icons.py`.
- API assumptions and internal mechanisms worth re-verifying on new Fusion
  releases are listed in [DEV_NOTES.md](DEV_NOTES.md); the feature history is
  in [CHANGELOG.md](CHANGELOG.md); the research and spec behind the upcoming
  hardware features are in [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md).
- Command skeleton based on the `Fusion360Utilities` helpers from
  [Fusion360AddinSkeleton](https://github.com/tapnair/Fusion360AddinSkeleton)
  by Patrick Rainsberry (same pattern as our UserParamWindow add-in).
- The lessons from this project (architecture, API gotchas, dialog/geometry
  patterns, a project scaffolder and a static checker) are packaged as a
  Claude Code skill in
  [`.claude/skills/fusion360-addin/`](.claude/skills/fusion360-addin/SKILL.md)
  for the next Fusion add-in; copy that folder to `~/.claude/skills/` to use
  it from any project.

## License

[MIT](LICENSE). The `Fusion360Utilities` framework is by Patrick Rainsberry
(MIT, from Fusion360AddinSkeleton).
