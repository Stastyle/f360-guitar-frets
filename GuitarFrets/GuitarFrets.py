# Guitar fret slot layout add-in.
# "Create Fret Slots" lays out the whole neck: fret slots (standard or
# fanned), nut slot, string lines, board outline, radius and cuts. The button
# lives in a "Guitar Frets" panel on the Utilities tab and in Solid > Create.

import traceback

import adsk.core

from .CreateFretSlotsCommand import CreateFretSlotsCommand

UTILITIES_TAB_IDS = ('UtilitiesTab', 'ToolsTab')
UTILITIES_PANEL_ID = 'GuitarFretsPanel'
UTILITIES_PANEL_NAME = 'Guitar Frets'

cmd_create = {
    'cmd_name': 'Create Fret Slots',
    'cmd_description': 'Lay out a guitar neck: fret slots (standard or fanned), '
                       'nut slot, string lines, board outline, radius and cuts',
    'cmd_resources': './resources/create_fret_slots',
    'cmd_id': 'cmdID_GuitarFrets_Create',
    'workspace': 'FusionSolidEnvironment',
    'toolbar_panel_id': 'SolidCreatePanel',
}

create_command = CreateFretSlotsCommand(dict(cmd_create), debug=False)


def _delete_ui_object(obj):
    try:
        if obj and obj.isValid:
            obj.deleteMe()
    except Exception:
        pass


def _find_utilities_tab(workspace):
    for tab_id in UTILITIES_TAB_IDS:
        tab = workspace.toolbarTabs.itemById(tab_id)
        if tab:
            return tab
    if workspace.toolbarTabs.count > 0:
        return workspace.toolbarTabs.item(0)
    return None


def _ensure_utilities_panel(ui):
    panel = ui.allToolbarPanels.itemById(UTILITIES_PANEL_ID)
    if panel:
        return panel
    workspace = ui.workspaces.itemById('FusionSolidEnvironment')
    if not workspace:
        return None
    tab = _find_utilities_tab(workspace)
    if not tab:
        return None
    return tab.toolbarPanels.add(UTILITIES_PANEL_ID, UTILITIES_PANEL_NAME)


def _register_utilities_button(ui):
    """Put the Create button in the Guitar Frets panel on the Utilities tab.

    Its command definition already exists (base-class on_run created it for
    the Solid > Create button), so this only adds a second control.
    """
    panel = _ensure_utilities_panel(ui)
    if not panel:
        return
    cmd_def = ui.commandDefinitions.itemById(create_command.cmd_id)
    if cmd_def and not panel.controls.itemById(create_command.cmd_id):
        control = panel.controls.addCommand(cmd_def)
        try:
            control.isPromoted = True
        except Exception:
            pass


def _promote_create_button(ui):
    # Make the Create button directly visible in Solid > Create — but only on
    # the first ever run, so a user who demotes it is not overridden on every
    # startup.
    from .CreateFretSlotsCommand import load_settings, save_settings
    from .Fusion360Utilities.Fusion360CommandBase import get_controls

    settings = load_settings()
    if settings.get('buttons_promoted'):
        return
    try:
        controls = get_controls(False, create_command.workspace,
                                create_command.toolbar_panel_id, ui)
        control = controls.itemById(create_command.cmd_id)
        if control:
            control.isPromoted = True
            settings['buttons_promoted'] = True
            save_settings(settings)
    except Exception:
        pass


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        create_command.on_run()        # Solid > Create button + definition
        _register_utilities_button(ui)
        _promote_create_button(ui)
    except Exception:
        if ui:
            ui.messageBox('GuitarFrets start failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        panel = ui.allToolbarPanels.itemById(UTILITIES_PANEL_ID)
        if panel:
            _delete_ui_object(panel.controls.itemById(create_command.cmd_id))
            if panel.controls.count == 0:
                _delete_ui_object(panel)

        create_command.on_stop()
    except Exception:
        if ui:
            ui.messageBox('GuitarFrets stop failed:\n{}'.format(traceback.format_exc()))
