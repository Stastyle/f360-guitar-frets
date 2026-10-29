---
tags: [fusion360-addin]
max_turns: 15
timeout_seconds: 400
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

my fusion addin worked yesterday and now when i click the button i get this popup and no dialog. i did move the helper functions into a separate file (slot_math.py next to the main .py) yesterday evening, maybe related?

```
Command created failed: Traceback (most recent call last):
  File "C:/Users/stas/AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/SlotCutter/Fusion360Utilities/Fusion360CommandBase.py", line 396, in notify
    self.cmd_object_.on_create(command_, inputs_)
  File "C:/Users/stas/AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/SlotCutter/SlotCutterCommand.py", line 88, in on_create
    import slot_math
ModuleNotFoundError: No module named 'slot_math'
```

also, separately: when I type a value like "1/8 in" the dialog sometimes shows a second popup "Input changed event failed" with something about selectedItem being None. Any idea?
