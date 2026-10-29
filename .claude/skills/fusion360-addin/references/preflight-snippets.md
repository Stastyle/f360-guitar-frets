# Pre-flight snippets for Fusion's Text Commands window

Fusion cannot run in a cloud session or in CI. When an API assumption needs
checking, give the user a snippet to paste into **Utilities → Text Commands**
(the window at the bottom; switch its input mode from `Txt` to `Py`), one
block at a time, and ask for the printed output. Keep the add-in's own
`DEV_NOTES.md` stocked with the snippets that verify *its* assumptions.

## Smoke test: API reachable, design open

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
print(app.version, 'design:', bool(d), 'units:', d.unitsManager.defaultLengthUnits if d else None)
```

## Inspect the selected entity (type, token, attributes)

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
ui = app.userInterface
for i in range(ui.activeSelections.count):
    e = ui.activeSelections.item(i).entity
    print(e.objectType, getattr(e, 'name', ''), e.entityToken[:24] + '...')
    for a in e.attributes:
        print('  attr', a.groupName, a.name, a.value[:120])
```

## Find every layout the add-in tagged

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
for a in d.findAttributes('GuitarFrets', 'fretSlotSketch'):   # your group / name
    print(a.parent.name if a.parent else '<deleted parent>', a.value[:80])
```

## Offset-plane sign: a known point must map to z ≈ 0

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
root = d.rootComponent
pi = root.constructionPlanes.createInput()
pi.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByReal(-0.6))
plane = root.constructionPlanes.add(pi)
sk = root.sketches.add(plane)
print('z of (0,0,-0.6):', sk.modelToSketchSpace(adsk.core.Point3D.create(0, 0, -0.6)).z)
```

## setByAngle with an axis line off the reference plane

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
pi.setByAngle(ln, adsk.core.ValueInput.createByReal(math.radians(17)), root.xYConstructionPlane)
ang = planes.add(pi)   # must succeed with the axis line OFF the reference plane
print('normal:', ang.geometry.normal.asArray())
```

## Extrude direction versus sketch normal

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
root = d.rootComponent
sk = root.sketches.add(root.xYConstructionPlane)
sk.sketchCurves.sketchLines.addTwoPointRectangle(
    adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(2, 1, 0))
ext = root.features.extrudeFeatures
inp = ext.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(-0.5))
f = ext.add(inp)
box = f.bodies.item(0).boundingBox
print('z range for distance -0.5:', box.minPoint.z, box.maxPoint.z)
```

## addThreePointRectangle corner semantics

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
sk = d.rootComponent.sketches.add(d.rootComponent.xYConstructionPlane)
sk.sketchCurves.sketchLines.addThreePointRectangle(
    adsk.core.Point3D.create(0, 0, 0),
    adsk.core.Point3D.create(1, 0, 0),
    adsk.core.Point3D.create(1, 3, 0))
for i in range(sk.sketchCurves.sketchLines.count):
    l = sk.sketchCurves.sketchLines.item(i)
    print(l.startSketchPoint.geometry.asArray(), '->', l.endSketchPoint.geometry.asArray())
```

## Arc sweep direction

```python
import adsk.core, adsk.fusion, math
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
sk = d.rootComponent.sketches.add(d.rootComponent.xYConstructionPlane)
arc = sk.sketchCurves.sketchArcs.addByCenterStartSweep(
    adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(1, 0, 0), math.pi / 2)
print('end point for +90deg sweep from (1,0):', arc.endSketchPoint.geometry.asArray())
# (0, 1, 0) => positive sweep is counter-clockwise in sketch coordinates
```

## List toolbar tabs and panels (ids change between releases)

```python
import adsk.core
ui = adsk.core.Application.get().userInterface
ws = ui.workspaces.itemById('FusionSolidEnvironment')
for i in range(ws.toolbarTabs.count):
    tab = ws.toolbarTabs.item(i)
    print('tab', tab.id, '|', tab.name)
    for j in range(tab.toolbarPanels.count):
        print('   panel', tab.toolbarPanels.item(j).id)
```

## Clean up a failed experiment

Ctrl+Z undoes Text Commands geometry like any other. To remove a component an
experiment (or a crashed build) left behind by name:

```python
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
d = adsk.fusion.Design.cast(app.activeProduct)
NAME = 'Fretboard (25.5 in, 22 frets)'
for occ in list(d.rootComponent.allOccurrences):
    if occ.component.name == NAME:
        occ.deleteMe(); print('deleted', NAME)
```
