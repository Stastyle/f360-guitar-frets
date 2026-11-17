#!/usr/bin/env python3
"""Static sanity check of a Fusion 360 add-in folder, without Fusion.

    python check_addin.py path/to/MyAddin

Fusion itself cannot run here, so this catches what can be caught before
the user installs the add-in and reports a traceback from a message box:

  * the manifest parses, is of type "addin" and has a UUID id
  * <Folder>.py exists and defines run() and stop()
  * every .py compiles
  * the package imports with a stub `adsk` (so import-time NameErrors,
    missing relative imports, typos in class bodies and broken module-level
    object construction show up now)
  * every 'cmd_resources' folder referenced from the entry module exists and
    holds 16x16.png and 32x32.png
  * absolute imports of the add-in's own modules anywhere in the code,
    including inside handlers (they pass under pytest and fail in Fusion)
  * third-party imports (Fusion's Python has no pip packages for add-ins)
  * settings.json is gitignored when the add-in writes one

Exit status 0 = all checks passed, 1 = at least one failed.
"""

import ast
import importlib
import json
import os
import py_compile
import re
import sys
import tempfile
import types
import uuid

sys.dont_write_bytecode = True   # the stub import must not leave __pycache__ behind

STDLIB = set(getattr(sys, 'stdlib_module_names', ()))


# --- a permissive stand-in for the adsk package ----------------------------

class _Meta(type):
    def __getattr__(cls, name):
        return _stub_class(name)


class _StubBase(metaclass=_Meta):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _stub_class(name)

    def __call__(self, *args, **kwargs):
        return _stub_class('result')()


_cache = {}


def _stub_class(name):
    if name not in _cache:
        _cache[name] = _Meta(name, (_StubBase,), {})
    return _cache[name]


def install_adsk_stub():
    adsk = types.ModuleType('adsk')
    for sub in ('core', 'fusion', 'cam', 'drawing'):
        module = types.ModuleType('adsk.' + sub)
        module.__getattr__ = lambda name, _m=module: _stub_class(name)
        sys.modules['adsk.' + sub] = module
        setattr(adsk, sub, module)
    adsk.autoTerminate = lambda *a, **k: None
    adsk.doEvents = lambda *a, **k: None
    adsk.terminate = lambda *a, **k: None
    sys.modules['adsk'] = adsk


# --- checks -----------------------------------------------------------------

def check(addin_dir):
    addin_dir = os.path.abspath(addin_dir.rstrip('/'))
    name = os.path.basename(addin_dir)
    problems = []
    notes = []

    def fail(message):
        problems.append(message)

    manifest_path = os.path.join(addin_dir, name + '.manifest')
    entry_path = os.path.join(addin_dir, name + '.py')
    if not os.path.isfile(manifest_path):
        fail('missing {}.manifest next to {}.py (the folder, the .py and the '
             '.manifest must share the same name)'.format(name, name))
    else:
        try:
            with open(manifest_path) as handle:
                manifest = json.load(handle)
            if manifest.get('type') != 'addin':
                notes.append('manifest type is {!r} (a script, not an add-in: no run-on-startup, '
                             'stop() is not called)'.format(manifest.get('type')))
            if manifest.get('autodeskProduct') != 'Fusion360':
                fail('manifest autodeskProduct should be "Fusion360"')
            try:
                uuid.UUID(str(manifest.get('id')))
            except ValueError:
                fail('manifest id is not a UUID (Fusion uses it to tell add-ins apart)')
        except ValueError as error:
            fail('manifest is not valid JSON: {}'.format(error))

    if not os.path.isfile(entry_path):
        fail('missing entry module {}.py'.format(name))
        return problems, notes

    py_files = []
    for root, _dirs, files in os.walk(addin_dir):
        if '__pycache__' in root:
            continue
        for filename in files:
            if filename.endswith('.py'):
                py_files.append(os.path.join(root, filename))
    # Compile into a scratch folder so the check leaves no __pycache__ in the
    # add-in (it would be shipped along if the folder is zipped).
    with tempfile.TemporaryDirectory() as scratch:
        for index, path in enumerate(py_files):
            try:
                py_compile.compile(path, cfile=os.path.join(scratch, '{}.pyc'.format(index)),
                                   doraise=True)
            except py_compile.PyCompileError as error:
                fail('does not compile: {}'.format(error.msg.strip()))

    with open(entry_path) as handle:
        entry_source = handle.read()
    try:
        tree = ast.parse(entry_source)
    except SyntaxError:
        tree = None
    if tree is not None:
        defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        for required in ('run', 'stop'):
            if required not in defined:
                fail('{}.py does not define {}(context)'.format(name, required))

    # Third-party imports: Fusion's bundled Python has no pip packages.
    for path in py_files:
        with open(path) as handle:
            try:
                module_tree = ast.parse(handle.read())
            except SyntaxError:
                continue
        for node in ast.walk(module_tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split('.')[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split('.')[0]]
            for top in names:
                if top in ('adsk',) or top in STDLIB or top == name:
                    continue
                if os.path.exists(os.path.join(addin_dir, top)) or \
                        os.path.exists(os.path.join(addin_dir, top + '.py')):
                    # Works under pytest (the folder is on sys.path there) and
                    # raises ModuleNotFoundError inside Fusion, where the folder
                    # is a package — at click time if the import is in a handler.
                    fail('{} line {} imports local module {!r} absolutely — use a relative '
                         'import (from . import {} / from .{} import ...) so it resolves '
                         'inside Fusion'.format(os.path.relpath(path, addin_dir),
                                                node.lineno, top, top, top))
                    continue
                fail('{} imports third-party module {!r}; Fusion add-ins run on Fusion\'s own '
                     'Python with the standard library only'.format(
                         os.path.relpath(path, addin_dir), top))

    # Resources referenced from the entry module.
    for resource in re.findall(r"""['"]cmd_resources['"]\s*:\s*['"]([^'"]+)['"]""", entry_source):
        folder = os.path.normpath(os.path.join(addin_dir, resource))
        if not os.path.isdir(folder):
            fail('resources folder {} does not exist'.format(resource))
            continue
        for icon in ('16x16.png', '32x32.png'):
            if not os.path.isfile(os.path.join(folder, icon)):
                fail('resources folder {} lacks {}'.format(resource, icon))

    # Import with the stub.
    install_adsk_stub()
    sys.path.insert(0, os.path.dirname(addin_dir))
    for key in list(sys.modules):
        if key == name or key.startswith(name + '.'):
            del sys.modules[key]
    try:
        # Fusion loads <Folder>/<Folder>.py as module "<Folder>.<Folder>" with
        # the folder as its package (no __init__.py needed), which is what
        # makes the relative imports inside the add-in work.
        module = importlib.import_module('{0}.{0}'.format(name))
        for required in ('run', 'stop'):
            if not callable(getattr(module, required, None)):
                fail('{} has no callable {}'.format(name, required))
    except Exception as error:  # noqa: BLE001 - report whatever import-time error there is
        fail('importing the package with a stub adsk failed: {}: {}'.format(
            type(error).__name__, error))

    # settings.json hygiene.
    writes_settings = any('settings.json' in open(path).read() for path in py_files)
    if writes_settings:
        repo_root = os.path.dirname(addin_dir)
        gitignore = os.path.join(repo_root, '.gitignore')
        ignored = os.path.isfile(gitignore) and 'settings.json' in open(gitignore).read()
        if not ignored:
            notes.append('the add-in writes settings.json but .gitignore does not list it')

    return problems, notes


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    problems, notes = check(sys.argv[1])
    for note in notes:
        print('note: ' + note)
    for problem in problems:
        print('FAIL: ' + problem)
    if problems:
        print('{} check(s) failed'.format(len(problems)))
        sys.exit(1)
    print('check_addin: all checks passed')


if __name__ == '__main__':
    main()
