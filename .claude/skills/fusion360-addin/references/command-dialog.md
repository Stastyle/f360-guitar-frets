# Command dialog patterns

How the dialog side of a command is structured so it stays correct as inputs
multiply. The scaffold's `<Name>Command.py` implements all of this for a
small example; this file explains the shape so you can extend it without
breaking the invariants.

## The shape of a command module

```
DEFAULTS, *_INPUTS tables, labels/constants      # declarative top
class BuildError(Exception)                      # expected problems, no traceback
load_settings / save_settings                    # settings.json
_entity_token / _sketch_metadata / _find_layout_sketches / _delete_tracked
_read_values(inputs) -> (values, problems)       # dialog -> plain dict (cm)
validate_and_compute(inputs, edit_sketch) -> (ok, message, params)
_success_message(units_manager, params)          # the info box text
geometry helpers (sketch/extrude/cut...)         # see geometry.md
build(params) -> tagged sketch                   # create or rebuild, atomic
class <Name>Command(Fusion360CommandBase)        # events + dialog plumbing
```

The command class holds no geometry logic; `build()` holds no dialog logic;
`_read_values` is the only place that touches input ids for reading. This
split is what lets you add an input in three places (DEFAULTS, a table,
`on_create`) and have it persist, prefill and validate automatically.

Keep all four tables even when one is empty (`SPINNER_INPUTS = ()`): the
loops over them in `_apply_settings` and `on_destroy` are no-ops, and the
next feature that needs a spinner or dropdown slots in without touching
the loops.

## Adding an input — checklist

1. `DEFAULTS[key]` with the default *expression* (`'5 mm'`), int, bool or
   dropdown item name.
2. One row in the matching table (`EXPRESSION_INPUTS`, `SPINNER_INPUTS`
   with its range, `CHECKBOX_INPUTS`, `DROPDOWN_INPUTS`).
3. `on_create`: add the input (through `value_input()` for expressions so an
   invalid stored expression falls back to the default); add a tooltip.
4. `_read_values`: read it with `read_length` (positive), `read_nonnegative`
   (0 allowed), `read_spinner`, `read_checkbox` or the dropdown pattern.
   Read a value only when its feature is on; keep the dict key present with
   `None`/0 otherwise so `params` always has every attribute.
5. `validate_and_compute`: cross-field rules (depth < thickness, grid fits).
6. `build`/metadata: store its cm value under a `*_cm` key (or raw for
   ints/bools/strings) and read it back in `_prefill_from_sketch`.
7. `_apply_visibility` if it depends on a checkbox/dropdown.
8. Bump `METADATA_VERSION` only if old layouts can no longer be rebuilt
   correctly; otherwise keep reading old metadata with defaults.

## Reading values safely

```python
def read_length(input_id, label):
    value_input = inputs.itemById(input_id)
    if not value_input or not value_input.isValidExpression:
        problems[input_id] = '{}: enter a valid length.'.format(label)
        return None
    value = value_input.value          # cm
    if value <= 0:
        problems[input_id] = '{}: must be greater than zero.'.format(label)
        return None
    return value
```

Collect *all* problems and join them for the info box — the user fixes
several fields at once instead of discovering them one by one. Return
`(values, problems)`; the caller stops at the first non-empty problem list.

## Validation returns a message either way

`validate_and_compute` returns `(ok, message, params)`. On success the
message is the sanity readout (`_success_message`): dimensions in the
document's units, counts, warnings that are not errors ("part of the nut
seat hangs off the board"). On failure it is the problem text. The same
call feeds `on_input_changed` (info box), `on_preview` and `on_execute`, so
the dialog never shows one thing and builds another.

Two rules that proved their worth:

- A **warning** goes in the message and lets the build proceed; an **error**
  blocks it. Decide per rule which it is, and prefer a warning when the user
  may know better.
- Every message says what to change ("raise *Board start behind nut* to
  3.5 mm"), not just what is wrong.

## Live preview

```python
def on_preview(self, command, inputs, args, input_values):
    self._preview_ok = False
    ok, message, params = validate_and_compute(inputs, self._edit_sketch_from_inputs(inputs))
    if not ok:
        return
    try:
        build(params)
        args.isValidResult = True
        self._preview_ok = True
    except BuildError as error:
        _set_info(inputs, str(error))
    except Exception:
        _set_info(inputs, 'Preview failed: ' + traceback.format_exc().splitlines()[-1])
```

Fusion rolls back the preview geometry before the next preview, so `build`
does not have to undo itself between keystrokes — but it must undo itself
*within* a failed run (see geometry.md, cleanup), or the rollback leaves a
half-built component visible until the next change.

## Settings persistence

- `load_settings()` starts from `dict(DEFAULTS)` and copies a stored value
  only if `isinstance(stored[key], type(DEFAULTS[key]))`. Then whitelist the
  dropdown values and migrate renamed keys
  (`if 'new_key' not in stored and isinstance(stored.get('old_key'), str): ...`).
- `on_destroy` saves only on `CompletedTerminationReason` and only if the
  dialog was fully built; it stores `.expression` (as typed), `int(spinner.value)`,
  `bool(checkbox.value)`, `dropdown.selectedItem.name`.
- `self._settings` keeps the dict loaded in `on_create` so the Start-from
  dropdown can restore "last used" after a reset to defaults without reading
  the file again. Nothing is written until OK.

## The Start-from dropdown (new vs. defaults vs. edit)

The first dropdown of the dialog lists `NEW_LAYOUT_LABELS` (two create
entries) followed by every tagged layout of the open document
(`_find_layout_sketches`). The mapping from a selected item to a sketch is
`item.index - len(NEW_LAYOUT_LABELS)` — adding a create entry moves the
offset with the tuple.

On change:

- an existing layout → `_prefill_from_sketch` (metadata values, cm → `.value`);
- a New entry → `_apply_settings` from `DEFAULTS` or `self._settings`
  (expressions → `.expression`), which also undoes a previous prefill.

Both end by re-applying the visibility rules and group expansion, because
programmatic changes do not fire `inputChanged`.

Why this matters: without it the dialog always opens with the last run's
values and there is no way back to a clean slate, and picking a layout to
edit then changing your mind leaves its values behind with no undo short of
Cancel. Users asked for both within the first week.

## Visibility rules in one function

Keep *all* show/hide logic in `_apply_visibility(inputs)` (or a few
per-feature functions) that compute visibility from the current input
values, and call it from `on_create`, `on_input_changed` for the controlling
inputs, `_apply_settings` and `_prefill_from_sketch`. Scattered
`isVisible = ...` lines drift out of sync with the next feature.

A hidden input keeps its value. If the value is meaningless while hidden
(e.g. a manual length superseded by a computed one), read it leniently so a
stale value never blocks the build, but keep it in the metadata so turning
the feature off again restores it.

## Dialog hygiene the user notices

- Group inputs by feature; expand a group when its feature is on.
- Put the info box last, 6–8 rows, read-only.
- Default values that match the most common real-world case (and say so in
  the tooltip), so OK with no edits produces something sensible.
- Name created sketches/components with the key parameters
  (`'Fret Slots (25.5 in, 22 frets)'`) — the Start-from dropdown shows those
  names.
