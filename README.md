# Guitar Frets — Fusion 360 Add-in

Lay out a guitar neck, ready to cut, from one dialog: **Create Fret Slots**
draws fret slot rectangles at mathematically correct positions
(`scale × (1 − 2^(−n/12))`), standard or **multi-scale (fanned)**, an optional
nut slot with its own depth, a bridge mark, **string guide lines**, a
**tapered board outline** (optionally cutting the board to it), an optional
single or **compound radius** cut, and an optional Push/Pull cut of the slots.

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

### Create Fret Slots

Model at least a fretboard blank, and draw a center line along the neck (a
sketch line on the fretboard top works well). Then click **Create Fret Slots**
and select:

| Input | What to pick |
|---|---|
| **Fret zero (nut)** | Where fret 0 sits — pick *one* of: the nut's face that looks toward the neck, the end face of the fretboard where the nut will go, or a sketch line drawn across the neck at the nut position. Fret distances are measured from here along the center line. |
| **Fretboard top** | The flat top face of the fretboard. The slot sketch is created on it. |
| **Center line** | A sketch line or straight edge running along the middle of the neck. Frets march from fret 0 *toward the far end of this line* — if they head the wrong way, tick **Flip direction**. |

The selections are guided: after each pick the next selection activates by
itself, and the tooltip beside the cursor (1/3 → 2/3 → 3/3) tells you what to
pick next — no need to click the dialog between picks.

Parameters: **scale length** (default 25.5 in — type any unit, e.g. `648 mm`),
**number of frets** (default 22), **fret slot width** (default 0.6 mm, a typical
fret-saw kerf), **fret slot length** across the neck (default 60 mm — keep it a
little wider than the board so the slots overhang the tapered edges; Press Pull
only removes material where the board actually is), and an optional **nut slot**
with its own width (default 3.5 mm). The nut slot is cut *backward* from fret 0:
its neck-side edge sits exactly on the fret-zero reference and the slot extends
away from the frets, where the nut material goes.

To cut the slots right away, tick **Cut slots (Push/Pull)** and enter the
**slot depth** (default 2.5 mm) — the sketch *and* the cut are created together,
and the cut shows in the live preview. Leave it unchecked to get just the
sketch.

**Nut offset** shifts fret 0 — and the *whole layout* with it (frets, nut
slot, strings, outline, bridge, radius) — along the neck away from the
selected fret-zero reference. Use it to push the assembly into the board, e.g.
when the nut sits in a slot inside the fretboard instead of against its end
(positive = into the board; 0 keeps fret 0 exactly on the reference).
**Nut slot depth** — shown when **Cut slots** is on — cuts the nut seat at its
own, usually shallower, depth (default 1.5 mm; a second Push/Pull feature,
separate from the fret slots — the nut profile is told apart from the fret
profiles by its area). The info box shows the exact span the nut seat covers
relative to the reference: make sure your board covers it, or part of the seat
is cut in the air.

With multi-scale layouts the fan is anchored so the *rearmost end* of the
angled nut line sits exactly on the fret-zero reference — nothing of the fret
layout reaches behind the edge you selected, so the full fan is on the board
and manufacturable.

**Mark bridge position** (on by default) adds a construction line across the
neck at the full scale length from fret 0 — the theoretical saddle contact
point, for placing the bridge. It is a reference only (never selected or cut).
Remember that a real saddle sits slightly farther for intonation compensation.

#### Strings and board outline

**Draw string lines** creates a separate **String Layout** sketch: one straight
line per string, from the bridge line through the nut and continuing past it by
the **headstock line length** — extend them under your headstock to align the
tuners. Inputs: number of strings, string spread (outer string to outer string)
at the nut and at the bridge.

**Draw fretboard outline** creates a separate **Fretboard Outline** sketch: a
closed tapered outline you can extrude into the board blank. You enter the
**nut width** and the bridge string spread; the side edges follow the outer
strings with a constant margin of `(nut width − nut spread) / 2`, from fret 0
to the last fret plus the **board end** overhang. Tick **Cut board to
outline** to also trim the board body to that shape right away (an Intersect
extrude through the whole blank — requires the top face selection).

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
needs a single-scale layout and the flat top FACE selected.

With tuners on, the string-line head extensions automatically reach each
string's own post (the manual **headstock line length** is preserved for
when the feature is off). Hole diameter presets: 10 mm (modern sealed),
11/32" (vintage Kluson), or custom. The dimensional research behind the
defaults is in [HARDWARE_RESEARCH.md](HARDWARE_RESEARCH.md).

#### Multi-scale (fanned frets)

Tick **Multi-scale** and enter the **bass side scale**, **treble side scale**,
and the **perpendicular fret** (the one that stays straight, commonly 7–9).
Fret midpoints follow the mean scale; the nut, bridge mark, strings, and taper
all fan accordingly. The fan is anchored so the *rearmost end* of the angled
nut line sits exactly on your fret-zero reference — nothing reaches behind the
edge you selected, so the whole layout is on the board and manufacturable.
The bass side is the **left** side looking from the nut toward the bridge —
if the fan leans the wrong way in the preview, swap the two scale values.

#### Fretboard radius

Choose **Single radius** (one radius, e.g. `9.5 in`) or **Compound radius**
(e.g. `9.5 in` at the nut to `16 in` at the board end). The add-in sketches an
arc profile at each end and loft-cuts the crown off the board — so the top you
selected must still be **flat**, and the cut only touches the board body.
Note: the slot cut depth is measured from the original flat top, so edge slots
end up shallower by the radius drop (the info box prints that number — add it
to your slot depth if it matters).

The dialog shows a live preview plus a sanity readout — the 12th fret must sit
at exactly half the scale length. Your last-used values are remembered.

### Cutting manually instead

If you created the sketch without **Cut slots**, you can always cut yourself:
show the Fret Slots sketch, window-select its profiles (or pick them one by
one), press **Q** (Press Pull) and enter the depth as a negative distance
(e.g. `-2.5 mm`).

### Radiused (curved) fretboards

If your board is still flat, prefer the built-in **Fretboard radius** option
above — it cuts the radius for you. The recipe below is for boards that
*already* have their radius. The fretboard-top selection must be flat, so:

1. **Construct → Tangent Plane** on the radiused top (tangent at the centerline).
2. Create a sketch on that plane and **Project** the board outline into it.
3. Draw the center line in that sketch.
4. In **Create Fret Slots**, select the *tangent plane* as the fretboard top.
5. After Press Pull, the slot depth is measured from the tangent plane — add the
   radius drop to your slot depth if you cut before radiusing, or simply slot
   first and radius afterwards.

### Changing the layout

Open **Create Fret Slots** again and pick your sketch in the **Edit** dropdown
at the top of the dialog. All its parameters *and* the original selections are
loaded back (they are stored on the sketch itself), so you can tweak just the
value you care about — say, the fret count — and press OK. The slots are redrawn
in place inside the same sketch, so an existing Press Pull cut recomputes onto
the new slots instead of breaking. A cut made with the **Cut slots** checkbox
is managed by the add-in: editing recreates it at the current depth, and
unchecking the box removes it.

If a stored selection can't be restored (e.g. the referenced face was deleted),
the info box asks you to re-pick just that one. Sketches made with older
versions of the add-in load their values but not their selections.

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
- Layout sketches are tagged with attributes on creation, so the **Edit**
  dropdown keeps finding them after saving and reopening the file.
- Settings are stored in `GuitarFrets/settings.json` (created automatically).
- All created sketch geometry is locked (fully defined) — nothing can be
  dragged out of position by accident. After a cutting run, only the
  **String Layout** and **Bridge Mark** sketches stay visible; the slot
  sketch, outline sketch, and radius tooling are hidden (the slot sketch
  stays visible when you skip the cut, so there is something to see).
- Everything a new layout creates (sketches, planes, cuts) is wrapped in one
  named **timeline group**. Edits append their recreated features at the end
  of the timeline, outside the original group.

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

## License

[MIT](LICENSE). The `Fusion360Utilities` framework is by Patrick Rainsberry
(MIT, from Fusion360AddinSkeleton).
