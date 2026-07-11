# Hardware features — research & design analysis (2026-07-11)

Multi-agent web research (4 topics, adversarially fact-checked) + design synthesis
for the two planned "Hardware (coming soon)" features: tuner layout and bridge
hardware. Numeric claims below were independently verified where marked; values
flagged unverified should be re-checked before shipping as defaults.

# GuitarFrets — Design Analysis: Tuner Layout & Bridge Hardware

Context anchors from the codebase: the dialog already has `grp_hardware` ("Hardware (coming soon)") with a `place_bridge` placeholder (`GuitarFrets/CreateFretSlotsCommand.py:1562-1573`), the string layout already extends past the nut by `headstock_length` (default 150 mm, `fret_math.string_layout`), and edit mode round-trips everything through attributes on the layout sketch. Both features below are designed to fit that architecture.

---

## 1. Tuner Feature

### 1.1 The core geometric decision: model the headstock angle explicitly. Do not stay in top-view.

The projection math settles this. Tilting the headstock back by θ about the nut line foreshortens all longitudinal (nut-ward) distances in the fretboard-plane view by cos(θ), while lateral offsets are unchanged. At real angles, against the Fender-documented 6th-post distance of 6.245" (158.6 mm) from the nut:

| Headstock angle | cos(θ) | Error at 6th post if drawn un-corrected in top view |
|---|---|---|
| 10° (PRS) | 0.985 | ~2.4 mm |
| 14° (Norlin Gibson, Epiphone) | 0.970 | ~4.8 mm |
| 17° (Gibson, Fender tuner-row angle era) | 0.956 | ~7.0 mm |

Fender's own placement tolerance is ±1/16" (1.6 mm). So **even at the shallowest common angle (10°), naive top-view placement of the far tuners is 1.5x out of tolerance, and at 17° it is off by nearly half a tuner-hole diameter.** The difference matters at *every* real angle; only θ = 0 (flat Fender headstock) is exempt. This kills the "stay in top view and let the user compensate" option.

The lutherie world's answer is unambiguous and CAD-friendly: layout is done in TRUE dimensions ON the face (Catto template sheets, Cumpiano jig, commercial stick-on templates), and holes are drilled perpendicular to the face, never vertical (StewMac drill-jig instructions). Fusion 360 makes this nearly free for us:

**Recommended construction:** add a `headstock_angle` parameter (default 0°, dropdown presets 0 / 10 / 14 / 17, free entry 0–25°). When θ = 0, tuner geometry goes on the existing fretboard-top plane, colinear with the current string-line extensions. When θ > 0, the add-in creates a construction axis along the nut line (we already have fret 0 in the local frame) and an angled construction plane hinged on it, then puts the tuner sketch **on that plane in true face coordinates**. Holes are then trivially normal to the face — exactly matching how a builder transfers a printed template to wood. No knowledge of the headstock solid is required; the plane and sketch live happily in the neck component next to everything else, and edit-mode attributes extend naturally (one more sketch, same attribute scheme).

One important free lunch from the math: **the plan-view path of a string is unaffected by break angle** (a straight 3D segment projects to the straight line between endpoint projections). So the existing string-layout extensions on the fretboard plane remain 100% valid for straight-pull *checking* — we keep them, and add the face-plane sketch for the *holes*. (Minor caveat to document: side-pull angles measured on the face are smaller by ~cos θ than in plan — 4–5% at 17° — irrelevant for pass/fail checks.)

### 1.2 Placement modes — ship exactly two

The research shows the industry splits into two workflows, and both are needed because they serve disjoint headstock types:

**Mode A — Straight-pull (string-path-first).** Each post center is placed on its string's extended nut-slot line (mapped to the face: lateral offset unchanged, longitudinal distance = plan distance / cos θ). This is the documented custom-builder method (Luthier Talk / TalkBass) and covers 6-inline Fender, Music Man-style 4+2, PRS-style 3+3 straight-pull, and headless-adjacent layouts. Parameters: first-post distance from nut (default **41.9 mm** — Fender's documented 1.650"), axial post spacing (default **0.919"** / 23.3 mm; note the independently CMM-measured 1967 neck read 0.904"/0.945", so expose this, don't hardcode), per-side split (6+0, 4+2, 3+3).

**Mode B — Pattern (shape/template-first).** Fixed hole grids that the nut slots are later aimed at — this is how every production 3+3 works, and 3+3 is exactly where straight-pull is geometrically impossible (the D/G strings kink ~10–15° sideways to reach the middle posts; that figure is a derivation, not published — treat as illustrative only). Presets:
- *Fender 6-inline*: first post 1.650", 0.919" axial / 0.281" lateral step (a 17°-to-centerline row); vintage-spacing variant 15/16" (23.8 mm) — the Kluson housing gap analysis makes ~0.945" the hard minimum for vintage housings.
- *3+3*: **35 mm pitch per side** (canonical Kluson/Waverly spacing, electric and acoustic), parameters for lateral offset of each row from centerline and first-post distance.

In both modes, emit as a derived output a **per-string nut-to-post line and its side-pull angle**, since nut slots are flared toward their posts (StewMac slotting guidance) — this is cheap, diagnostic, and no other tool does it.

### 1.3 Parameters (v1 set)

- `headstock_angle` (0/10/14/17 presets; 0 default)
- Layout mode: Straight-pull | Pattern-6-inline | Pattern-3+3
- Split (for straight-pull): 6+0 / 3+3 / 4+2
- First-post distance from nut: default 41.9 mm (practice band 40–45 mm)
- Post spacing: default 23.3 mm axial (0.919"); vintage option 23.8 mm (15/16"); modern retrofit 25.4 mm (1")
- Hole diameter: dropdown **10 mm (modern sealed — Gotoh/Grover/Hipshot/Schaller)** | **8.73 mm / 11/32" (vintage Kluson bushing)** | custom. These two defaults are verifier-**confirmed**; note some imports use 10.5 mm.
- Min edge distance (warning only, no outline known): default 12.7 mm center-to-edge, rule-of-thumb floor = hole diameter.

### 1.4 Honestly out of scope (tuner v1)

- **Headstock outline / scarf joint modeling.** We place hole centers and reference lines; the user owns the headstock solid. (This is still ahead of everything surveyed — GuitarEngine is the only prior art that places posts at all, flat-only, with its `HeadstockAngle` parameter literally dead code.)
- **Tangent-grazing post offset** (post radius + half string gauge perpendicular to string line) — real custom-builder refinement, sub-millimeter, v2.
- **Staggered post heights and string trees** — plan-view hole layout is *identical* for staggered sets (Fender/Hipshot: only post height changes), so this is a documentation note, not geometry. String-tree midpoint marker is a cheap v2 nicety.
- **Actual hole features.** V1 emits sketch circles + points on the correct plane; cutting requires a headstock body that doesn't exist in our data model. V2 can offer "cut into selected body, normal to face."
- **Bass tuners** (14–18 mm holes, different edge distances — the 0.475" P-bass edge figure in the research was flagged wrong by the verifier; do not ship bass defaults until researched separately).

---

## 2. Bridge Feature

### 2.1 Same command or separate? Both — deliberately phased, and the research says why.

Every authoritative placement rule found is a **nut-to-feature distance** (25-1/4" trem pivot line, scale + 1/16" TOM treble post, scale − 0.415" Floyd studs, 12th-fret-transfer acoustic saddle), never a body-outline offset; the standard workflow locates the bridge from the nut *after* the neck is fitted. So the fretboard layout sketch — which owns the nut datum and scale — is the *right source of truth*, and the current "bridge mark in the neck sketch" is not a mistake, it's the datum.

The complication is neck angle: at a typical TOM neck angle of 4°, plan-projected distance differs from along-string-plane distance by cos(4°) ≈ 0.9976 — **~1.5 mm over a 25.5" scale, which is the size of the entire treble compensation budget.** For flat-pocket Fender-style construction (0° neck angle, fret plane parallel to body top), vertical projection from the fretboard plane onto the body is exact.

**Recommendation:**

- **V1: extend the existing command.** Upgrade the bare bridge mark into a "Bridge reference" group drawn on the fretboard plane: per-string compensated saddle points, the compensated saddle line (the staircase/slant), and the chosen preset's mounting-hole centers and screw/stud lines as construction geometry. This is exactly correct for flat-neck-angle builds and a correct *reference* (with a documented cos-θ caveat) for angled-neck builds. It reuses the sketch, the local frame, and the attribute/edit infrastructure with zero new selection inputs.
- **V2: a separate command, "Place Bridge on Body."** Inputs: a body face + the existing GuitarFrets layout sketch (read its stored attributes for nut datum, scale(s), string spread) + neck angle. It measures scale along the string plane and projects the footprint onto the body face — mirroring the real "measure from the actual nut" workflow. This is the architecturally right home for TOM/Floyd placement, and it is genuinely novel: no surveyed tool places bridge mounting holes at all.

Do not try to make the v1 in-command version handle neck angle — that requires body knowledge the add-in explicitly doesn't have, and a wrong-by-1.5-mm "feature" is worse than a labeled reference.

### 2.2 Per-string compensation defaults

Ship an editable per-string table (mm behind nominal scale), defaulted for 6-string 25.5" with 10–46:

| String | Default | Research basis |
|---|---|---|
| high E | 1.5 | plain .009–.013: 0.8–1.6 mm |
| B | 2.0 | same band, upper end |
| G (plain) | 2.5 | plain .016–.018: 1.4–1.9 mm + staircase headroom |
| D | 2.5 | wound .024–.028: 2.0–2.6 mm |
| A | 3.0 | wound .036–.046: 2.6–3.4 mm |
| low E | 4.0 | practical intonated range 4–6 mm |

**Flag: these derive from the CMUSE geometric-stretch model, rated medium/unverified ("within a millimeter or two").** That is fine, because the design intent is not exact intonation — it is to center each preset's saddle travel on roughly **scale + 2–3 mm** so real intonation lands inside the adjustment window. Label the table "starting points, final intonation set by ear/strobe."

### 2.3 Bridge-type presets — ship these four first

1. **Fender vintage 6-screw tremolo:** pivot-screw line at **scale − 6.35 mm** (25-1/4" ± 1/16" on 25.5", StewMac assembly guide), 6 screws evenly spanning **56.36 mm** (2-7/32"), string spread 56.36 mm (import variant 52.4 mm — make spread a parameter).
2. **Fender hardtail:** front screw line at the same **scale − 6.35 mm** station (same source).
3. **Tune-o-matic ABR-1 + stopbar:** treble post at **scale + 1.6 mm** (+1/16", ±0.030"), bass post a **flat 1/8" (3.2 mm)** farther back — verifier correction: StewMac's spec is flat 1/8", not a 1/16–1/8" range, and 1/8" over the 73.66 mm post span is 2.47°, not the folkloric "3°". Posts **73.66 mm** c-c (Nashville variant 74.5 mm, more saddle travel). Stopbar: studs **82 mm** (Gotoh) / 82.55 mm (USA) c-c, default station ~45 mm behind the TOM line, clearly marked "break-angle governed, not intonation-critical, adjust freely" — the 1.5–2" figure is medium/unverified.
4. **Acoustic slanted saddle slot:** front edge at high E **scale + 2.3 mm**, bass E **scale + 5.5 mm** (per the verifier's re-run of the StewMac calculator for a true 25.5": 25.589"/25.715"; the originally quoted 25.428/25.553 belongs to a ~25.34" Martin scale — do not ship those numbers), slot width 3/32"–1/8". Crown compensation patterns (B-comp, wave, zig-zag) are explicitly out of scope per MacNichol — "no universal best pattern."

**V2 presets:** Floyd Rose (stud line at **scale − 10.5 mm** / 0.415", studs 74 mm c-c *as a parameter* — published values scatter 73.66–74.61 mm and sub-mm matters for knife edges; routing depths trace to a single third-party template vendor, so don't ship them as defaults without cross-checking official Floyd drawings) and Fender 2-point (studs 56 mm c-c; derive the stud-line offset geometrically from saddle travel rather than trusting the unverified 3/8–1/2" figure).

### 2.4 Neck-angle / bridge-height coupling — out of scope, documented

The stack-up (TOM saddle plane ~5/8" above a carved top forcing ~4° neck angle; low Fender bridges ~1/2" with a 0° pocket) is real but is a *body/neck-joint* design problem. V1: a doc note plus, in the v2 body command, a read-only "fret-plane height at bridge" readout. Do not attempt to recommend a neck angle.

### 2.5 Out of scope for bridge v1

3D bridge/saddle models; tremolo spring-cavity and Floyd recess routing; stopbar break-angle solver (13–17° window); per-string saddle-travel validation against specific hardware; bass bridges; body outline anything.

---

## 3. Recommended Roadmap

**Tuner v1 (smallest genuinely useful):** `headstock_angle` parameter; angled construction plane hinged on the nut line (fretboard plane itself when 0°); Straight-pull + Pattern (6-inline, 3+3) modes; face-true post points and hole circles (10 mm / 8.73 mm); per-string nut-to-post side-pull readout; keep existing plan-view string extensions as the straight-pull check. Sketch geometry only.

**Tuner v2:** cut holes normal to face into a selected body; tangent post offset; two-step vintage bore (11/32" face / 1/4" through) and counterbore support; edge-distance validation against a selected headstock profile; string-tree midpoint marker; 4+2 pattern preset; template (DXF/PDF flat-pattern) export of the face sketch — matching the FretFind2D-era expectation of printable 1:1 templates.

**Bridge v1 (same command):** compensated per-string saddle points + editable compensation table; four presets above drawn as construction footprints at the bridge mark; parameterized string spread (51.6 / 52.4 / 54.1 / 56.4 mm families).

**Bridge v2 (new command):** "Place Bridge on Body" — body face + layout-sketch attributes + neck angle, along-string-plane measurement, projected footprint with real hole features; Floyd and 2-point presets; Nashville/import footprint variants.

Sequencing opinion: **Tuner v1 first.** It is the feature with zero prior art (GuitarEngine's flat-only beta is the entire field), it needs no new selection inputs, and it directly redeems the existing "headstock line length" strings which are currently misleading for any angled build.

---

## 4. Open Questions for Stas

1. **Flat or angled headstocks?** Do you build Fender-style flat (step-down + trees) or tilted (10–17°)? Determines whether the angled-plane machinery is v1-critical or the 0° path dominates.
2. **6-inline or 3+3?** If you never build 3+3, Pattern mode can slip to v2 and v1 becomes straight-pull only.
3. **Electric only?** The acoustic saddle-slot preset and 35 mm 3+3 acoustic spacing are dead weight if yes; bass changes tuner hole defaults entirely (14–18 mm) if it's ever in scope.
4. **One Fusion design or separate neck/body designs?** The v2 body-face bridge command assumes the body face is selectable in the same design. If you use separate designs/x-refs, we need a "publish datum" strategy (named construction plane/point at the compensated saddle line) instead.
5. **Sketch references or cut features?** Are construction circles/points enough (you finish holes manually/CNC), or do you want the add-in cutting holes into solids? Affects both features' v1/v2 split.
6. **What hardware do you actually buy?** Specific tuner line (Gotoh SG381? Hipshot Grip-Lock? vintage Kluson) and bridge models — presets should lead with your parts. Also your typical string gauges, so the compensation defaults match your builds, not a generic 10–46 set.
7. **Vintage or modern spacing bias?** 15/16" vs 0.919"/1" inline spacing, and 10 vs 10.5 mm holes — which should be the one-click default?

Files most relevant to implementation: `X:\f360-guitar-frets\GuitarFrets\CreateFretSlotsCommand.py` (hardware group at lines 1562–1573, headstock_length plumbing at 38/269/1053–1056/1151/1313/1535–1536/1704) and `X:\f360-guitar-frets\GuitarFrets\fret_math.py` (`string_layout` — the straight-pull mode extends exactly this function's output).

---

# Review gaps (completeness critique — resolve before implementation)


**1. Multi-scale/fanned layouts are never addressed — for either feature — despite being an existing add-in capability.**
- The proposed angled plane is "hinged on the nut line," but in a fanned layout the nut is slanted; real tilted headstocks break perpendicular to the neck centerline, not along the slanted nut. The hinge axis must be decoupled from the nut line (new parameter: break-line station/orientation).
- "First-post distance from nut" is ambiguous per string when the nut is slanted (along the string? along the centerline? from that string's own nut point?).
- All four bridge presets are rigid straight hardware. A standard TOM/6-screw trem/hardtail cannot serve a fanned bridge line except within a small slant tolerance; fanned builds use individual saddles/single-string bridges. The design must define what presets do (disable? per-string hardware mode? max-slant warning) when the layout is multi-scale — currently undefined.
- Per-string compensation must offset from each string's *own* scale point on the slanted bridge line; the analysis implicitly assumes one scale.

**2. Left-handed layouts: zero mentions.** Everything directional mirrors — 6-inline lateral step direction, 4+2/3+3 side assignment, the TOM 1/8" bass-back offset, the acoustic saddle slant, compensation staircase, reverse headstocks. Needs a handedness flag (or inherit one from the existing layout) and an explicit open question to Stas.

**3. The angled sketch plane is not the headstock face — a real, tolerance-scale error the analysis misses.** The headstock face sits below the fret plane by fretboard thickness + step (~5–9 mm), and the break point is often behind the nut (Gibson breaks at the nut's back edge; scarf joints break further out). A plane hinged at fret 0 *on the fretboard top* is parallel-offset from the true face; vertical (plan) mapping of string lines onto the wrong parallel plane shifts hole plan positions by ~t·sin θ ≈ 1.5–2.5 mm at 14–17° — the same order as the ±1.6 mm tolerance the analysis itself invokes to justify the whole approach. Needs `face_offset` / `break_point_offset` parameters (or a documented error bound), and an open question about scarf vs. one-piece construction.

**4. Nut datum ambiguity, worth more than the tolerance budget.** The add-in models a nut *slot* with width. "First-post distance from nut = 41.9 mm" — from the fret-0 (front) edge or the headstock-side (back) edge? Nut thickness is 3–6 mm, i.e., 2–4x the ±1.6 mm tolerance. The datum must be specified and stored.

**5. Internal contradiction on the TOM preset.** Section 1.1 "kills" top-view tuner placement for a 2.4 mm error, but Bridge v1 ships TOM mounting-post centers on the fretboard plane knowing the cos(4°) error is ~1.5 mm — and TOM is used almost exclusively *with* an angled neck (that's why it's tall). So the one preset where the flat assumption essentially never holds is shipped as v1 drill-able geometry. Either restrict v1 hole centers to the genuinely-flat presets (6-screw trem, hardtail), demote TOM to saddle-line-only in v1, or accept an optional neck-angle input in v1 for longitudinal correction (which needs no body knowledge — it's just a cos θ scale factor, contradicting the claim that v1 correction "requires body knowledge").

**6. String count is hardcoded to 6 throughout.** The add-in draws N string lines; the design offers only 6+0/4+2/3+3 splits, a 6-row compensation table, and 6-string presets. No 4-inline/2+2 (bass), 7/8-string splits, or a generalized m+n split parameter; the compensation table has no story for N≠6 (should be gauge-driven or per-count defaults). The task explicitly raises bass; the analysis punts only bass *tuner holes* and is silent on bass splits, 19 mm bridge spacing, and what the UI even shows for a 4-string layout.

**7. Edit-mode holes are waved away as "extends naturally."** Unanswered: which object owns the new attributes (the layout sketch, the tuner sketch, both?); what happens when the user deletes the tuner sketch or the angled construction plane and re-enters edit; changing `headstock_angle` — redefine the plane in place (preserving the user's headstock solid built on it) vs. delete/recreate (orphans downstream geometry); toggling the tuner feature off in edit when user geometry depends on the plane; timeline position of the new plane relative to existing features.

**8. Component/occurrence handling is unaddressed.** Creating a construction plane and sketch when the selected face belongs to an occurrence requires assembly-context handling (`nativeObject`/`createForAssemblyContext`); the v2 body command crosses component boundaries (sketch in which component? projections across occurrence transforms?). Bigger miss: in an assembled design the neck angle *already exists* as the neck/body occurrence transform — v2 should measure it rather than take a user-typed `neck_angle` that can silently disagree with the model.

**9. Duplicate source of truth for bridge string spread.** The existing String Layout already fixes bridge-end spread; Bridge v1 adds an independent "string spread parameter (51.6/52.4/54.1/56.4)". Behavior on mismatch is undefined. Saddle compensation points must land on the existing string lines; preset spread should validate against (or drive) the string layout, not parallel it.

**10. `headstock_length` interaction not reconciled.** Once posts are computed, the plan-view extensions (fixed 150 mm default) can fall short of or overshoot the post row; the sensible behavior — derive extension length from farthest post plan distance (face distance x cos θ) — is never proposed, even though "redeeming" these lines is cited as the motivation for sequencing.

**11. The cos-error table overstates its case by mixing layouts.** It applies Fender's 158.6 mm 6th-post distance (a *flat* headstock spec) to 10–17° tilts; no real tilted headstock has a 158 mm post row. Worst realistic case (17° 3+3, farthest post ~110–115 mm) is ~5 mm — the conclusion survives, but the numbers as presented describe a guitar that doesn't exist. The "17° (Gibson, Fender tuner-row angle era)" row also conflates headstock tilt with Fender's *in-plane* 17° tuner-row angle (the 0.281"/0.919" step cited later) — different quantities that happen to share a value.

**12. Preset/scope omissions with no open question attached:**
- Wraparound bridge (LP Junior, PRS Stoptail): the case where placement *is* intonation (near-zero saddle travel) — more placement-critical than any listed preset, absent even from v2.
- String-through hardtail: ferrule pattern needs the body; the v1 "hardtail" preset silently covers only top-loaders.
- Slotted (classical/vintage) headstocks: side-mounted rollers, entirely different geometry — should be explicitly declared out of scope.
- Zero-fret builds: the add-in has a "fret-zero reference"; with a zero fret the string datum is fret 0, not the nut — affects both first-post distance and compensation datum. Never mentioned.

**13. Missing open questions for Stas:** handedness (see 2); string count / bass (beyond "electric only?"); scarf joint vs. one-piece and break-point location (see 3); whether his designs are assemblies with joints (enables measured neck angle, see 8); reverse/inline-lefty headstocks; metric vs. imperial display bias.

**14. Minor:** "min edge distance 12.7 mm center-to-edge, floor = hole diameter" mixes center-to-edge and edge-to-edge conventions — specify which; nut-slot flare readout should note the true string direction is 3D (side-pull + break angle), the plan angle alone under-flares the slot floor; §1.2 says "ship exactly two modes" but §1.3 lists three mode values.

---

# Decisions and final v1 spec (2026-07-11, after two-lens review)

Stas's decisions on the open questions: prefers **angled** headstocks but flat (0°) stays a
first-class path; wants **both** 6-inline and 3+3 — and 3+3 may also be straight-pull;
**electric guitar + electric bass** versatility (N strings); may work **fretboard-first**
with the body added to the design later; **reference sketches only** in v1 (cutting later);
no brand loyalty — **presets everywhere, always with manual entry**; **reversed headstock**
is an option.

The draft spec derived from these answers was reviewed by two independent agents
(lutherie-geometry lens; codebase-integration lens). All findings are folded in below.
Anything marked **[VERIFY]** must be checked before the value ships as a default.

## A. Tuner layout — v1

Two orthogonal controls: **arrangement** and **placement mode**.

### A.1 Arrangement (split)
- `m+n` posts per side; single `m` spinner, `n = string_count − m` derived (never validated
  after the fact). `m` = bass side. Presets: 6+0, 3+3, 4+2, 4+0, 2+2.
- **Reversed** checkbox, semantics per mode:
  - Straight-pull: reverse the string→station assignment (the nearest post moves to the
    opposite outer string) and swap the side assignment of split rows.
  - Pattern: mirror the grid laterally about the centerline. (No-op for a symmetric 3+3
    grid — say so in the tooltip.)

### A.2 Placement mode
- **Straight-pull** — posts lie on the strings' extended plan lines. The primitive is a
  per-string distance table (PLAN distances along the neck, measured from the datum, A.4);
  presets fill the table:
  - 6+0 / 4+0 inline: monotonic outer-to-outer, first post 41.9 mm **[VERIFY which nut edge
    Fender's 1.650" references]**, increment 23.3 mm (0.919"); vintage 23.8 mm, modern 25.4 mm.
  - 3+3 / 4+2 straight-pull: **one global sequence of string_count DISTINCT axial stations**,
    assigned alternating sides outer-to-inner (E,e,A,B,D,G for 3+3) — naive per-side symmetric
    sequences physically overlap the D/G posts (~7 mm apart at the same station; string plan
    lines CONVERGE past the nut).
  - Always: post-clearance check — warn when any two post centers are closer than
    hole diameter + 8 mm housing margin (margin editable).
- **Pattern (grid-first)** — fixed grids the nut slots aim at. FACE-true dimensions,
  drawn unscaled on the face plane:
  - Fender 6-inline: first post 1.650", axial step 0.919", lateral step 0.281"; the 17°
    in-plane row angle is a READ-ONLY readout (it IS atan(0.281/0.919) — never a second input).
  - Gibson-style 3+3: 35 mm pitch per side, lateral row-offset-from-centerline parameter,
    first-post distance parameter.
  - Custom: manual grid (per-post x/y table).
  - v1 restriction: pattern mode requires single-scale (fanned nut breaks grid assumptions).
- Distance conventions (state in tooltips, not just code): straight-pull parameters are
  PLAN distances (the string plan line is authoritative), mapped to the face by 1/cos θ;
  pattern grid parameters are FACE-true.

### A.3 Headstock plane
- `headstock_angle` θ: presets 0/10/14/17°, free 0–25°. Needs a NEW degree-unit input
  helper (existing value_input/read_length are length-only and reject 0).
- θ = 0: tuner geometry goes in its own dedicated sketch on the fretboard-top entity
  (NOT into the String Layout polyline sketch — circles need a new/extended helper).
- θ > 0 (v1: single-scale only): parametric chain, all four objects token-tracked
  (metadata v6), deleted in consumed-last order (tuner sketch → angled plane → hinge
  sketch → offset plane) BEFORE _clear_sketch_curves in edit mode:
  1. offset construction plane: setByOffset(top, −face_drop), face_drop default 6 mm;
  2. hinge sketch on it: hinge line perpendicular to the centerline at `break_offset`
     behind the datum (default = nut_slot_width when the nut slot is on, else 3.5 mm);
  3. angled plane: setByAngle on the hinge line;
  4. tuner sketch on the angled plane, in true face coordinates.
  Face-coordinate zero = the hinge line (the face plane's intersection with the vertical
  plane through the hinge station). Document: a ruler hooked where the nut meets the face
  reads ~face_drop·sin θ (~1.5–1.75 mm at 14–17°) off the sketch origin; defaults are
  one-piece-neck oriented, scarf users set break_offset (residual ~1 mm per 25 mm if not).
- Plan↔face mapping must include the hinge: plan = break_offset + face_beyond_hinge·cos θ.
  Use the SAME expression for post mapping, the straight-pull lateral lookup, and the
  head-line auto-extension. Unit test at θ=17°, break_offset=25 mm.
- Occurrence/sign safety: resolve the offset direction AND the setByAngle direction with
  dot-product checks against root-space up/neck vectors (like _apply_radius), plus a hard
  assertion that the angled plane origin lies BELOW the top face — raise FretSlotsError
  rather than draw a silently-flipped reference.

### A.4 Datum
- All tuner distances measure from **fret 0** — the string's nut contact point, which always
  exists (nut slot is optional!) and is single-valued per string even in fanned layouts
  (each string's own nut intersection, already computed by string_layout). Toggling the nut
  slot must never move tuner holes. The 41.9 mm default's tooltip notes the Fender reference
  edge is unverified — adjust by nut thickness if your source measures from the back edge.

### A.5 Outputs (reference only)
- Post center points + hole circles in the dedicated tuner sketch. Diameter presets:
  10 mm (modern sealed), 8.73 mm (11/32" vintage Kluson), manual. Bass sizes: manual only
  in v1 **[VERIFY before shipping bass presets — research round pending]**.
- Per-string nut→post guide line + side-pull angle readout — labeled as PLAN-view angle
  with the caveat that the true 3D pull (side + break) is larger; plan angle alone
  under-flares the nut slot floor.
- String-line head extensions: when the tuner feature is ON, extend each string to its own
  post's plan station (per-string computed lengths stored separately in metadata as a list);
  the user's manual `headstock_length` value is NEVER programmatically overwritten — it
  remains in its own metadata/settings slot and resumes when the feature is off. Skip/relax
  read_length validation for the hidden manual input while tuners are on.
- String math is computed UNCONDITIONALLY when tuners or saddle points are on —
  the draw_strings checkbox controls drawing only, not the math.

### A.6 Out of scope (tuner v1)
Headstock outline/scarf modeling; staggered post heights (doc note — plan layout identical);
string trees; hole cutting; edge-distance validation against an outline; θ>0 for multi-scale;
left-handed full mirror (Reversed ≠ lefty; lefty deferred).

## B. Bridge reference — v1 (same command)

Rationale: every documented placement rule is a nut-to-feature distance; the standard
workflow locates the bridge from the nut after the neck is fitted; and fretboard-first
users may not have a body yet. The fretboard sketch owns the datum; v1 enriches the
existing Bridge Mark, v2 projects onto a body face.

1. **Per-string compensated saddle points** on each string's own line, measured from that
   string's own scale point (multi-scale safe by construction). Editable table, defaults
   for 6-string 25.5"/10–46: 1.5/2.0/2.5/2.5/3.0/4.0 mm — labeled "starting points; final
   intonation is set by ear". N≠6: table has N rows; bass defaults TBD.
2. **Footprint presets** (construction geometry at the bridge mark):
   - Fender 6-screw tremolo: pivot-screw line at scale − 6.35 mm, 6 screws spanning 56.36 mm.
   - Fender hardtail: front screw line at scale − 6.35 mm (top-loader only — string-through
     ferrules need the body; explicitly a v2 body-command item).
   - Tune-o-matic + stopbar: treble post scale + 1.6 mm, bass post +3.2 mm further;
     post span sub-option ABR-1 73.66 mm / Nashville 74.5 mm; stopbar stud span sub-option
     82 mm (Gotoh) / 82.55 mm (USA), station default 45 mm behind the TOM line, labeled
     break-angle-governed / freely adjustable.
   - Custom: manual (station offset from scale, hole count, span).
   - Acoustic slanted saddle → v2 (user is electric+bass).
3. **`neck_angle` input** (default 0°, degree helper): applies cos θ to longitudinal
   stations. Tooltip (verbatim intent): "apply ONLY when using this sketch as a flat plan
   template on the body; leave 0 if the neck/sketch will be physically tilted in the
   assembly — otherwise the correction double-counts (cos²)." Store the flag in attributes
   so the v2 body command can reconcile.
4. **Multi-scale:** rigid straight-hardware presets disabled for fanned layouts (message:
   use per-string saddle points / individual bridges); saddle points always work.
5. **Spread source of truth:** presets never introduce a second bridge-spread input —
   saddle points land on the existing String Layout lines (spread_bridge); a preset whose
   fixed hardware spread mismatches the layout spread by >1 mm triggers an info-box
   warning, never a silent override.

## C. Cross-cutting implementation constraints (from the codebase review)

- Metadata version 5 → 6; new tokens: offset plane, hinge sketch, angled plane, tuner
  sketch, bridge-footprint additions; extend _delete_tracked in consumed-last order.
- Zero-valid inputs (headstock_angle, break_offset, neck_angle, row offset, compensation
  entries) must use the nut_slot_offset prefill pattern — the default set_value guard
  drops stored values ≤ 0.
- Per-string tables persist ONLY in sketch metadata (JSON lists, like radius_sketch_tokens),
  regenerate from defaults when string_count changes, and are excluded from settings.json
  (whose loader type-checks against flat DEFAULTS).
- Every new dropdown: whitelist validation in load_settings + select-only-target prefill
  (both existing conventions guard known crash modes). Reuse or retire the current
  grp_hardware placeholder input ids.
- Feature ordering (DEV_NOTES §1): the tuner plane chain + tuner/bridge sketches join the
  "sketches first" block — all created BEFORE the radius loft and the outline Intersect cut.

## D. v2 (both features)
"Place Bridge on Body" command (body face + layout-sketch attributes + neck angle measured
from the assembly joint when present); hole cutting normal to faces; Floyd Rose + 2-point
presets; acoustic saddle preset; bass hardware presets (after a dedicated verification
round); string-through ferrule patterns; DXF/PDF template export; string-tree marker;
tangent post offset; two-step vintage bores; θ>0 multi-scale; lefty full mirror.
