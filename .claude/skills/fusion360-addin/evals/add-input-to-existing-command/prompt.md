---
tags: [fusion360-addin]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In the GuitarFrets add-in (this repo), add a "Zero fret" option to the Create Fretboard dialog: a checkbox, and when it's on, a "Zero fret distance from nut" length (default 8 mm) — an extra slot at that distance in front of fret 0, same width and depth as the other fret slots. It must remember the last value between sessions like the other fields, show up again when I edit an existing layout, and be validated (it can't be at or past fret 1). Add tests for the math.
