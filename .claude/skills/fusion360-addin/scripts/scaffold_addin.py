#!/usr/bin/env python3
"""Scaffold a new Fusion 360 add-in project from the skill's templates.

    python scaffold_addin.py TARGET_DIR --name MyAddin --command-name "Create Bracket" \
        [--description "..."] [--author "..."] [--part-name Bracket] [--panel-name "My Tools"]

TARGET_DIR is the repository root (created if missing). The result:

    TARGET_DIR/
    ├── MyAddin/                      # the folder installed in Fusion
    │   ├── MyAddin.py                #   run()/stop(), toolbar registration
    │   ├── MyAddin.manifest          #   fresh UUID
    │   ├── MyAddinCommand.py         #   dialog + validation + preview + build
    │   ├── my_addin_math.py          #   pure-python math (pytest-able)
    │   ├── constants.py
    │   ├── Fusion360Utilities/       #   verbatim framework (MIT, P. Rainsberry)
    │   └── resources/create_bracket/ #   16/32 px icons (+ disabled)
    ├── tests/test_my_addin_math.py
    ├── scripts/make_icons.py
    ├── README.md  CHANGELOG.md  DEV_NOTES.md  .gitignore

The generated command is a WORKING example (plate with a hole grid) that
already has settings persistence, a Start-from dropdown with edit mode, a
live preview and failure cleanup. Replace its inputs and geometry; keep the
structure. Existing files are never overwritten unless --force is given.
"""

import argparse
import datetime
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(SKILL_DIR, 'assets', 'template')
UTILITIES_DIR = os.path.join(SKILL_DIR, 'assets', 'Fusion360Utilities')
SCRIPTS_DIR = os.path.join(SKILL_DIR, 'scripts')

sys.path.insert(0, SCRIPTS_DIR)
from make_icons import make_icon_set  # noqa: E402


def camel_to_snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def words_to_snake(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def words_to_camel(text):
    return ''.join(part.capitalize() for part in re.split(r'[^A-Za-z0-9]+', text) if part)


def render(template_name, context):
    with open(os.path.join(TEMPLATE_DIR, template_name)) as handle:
        text = handle.read()
    for key, value in context.items():
        text = text.replace('{{%s}}' % key, str(value))
    leftover = re.findall(r'{{[A-Z_]+}}', text)
    if leftover:
        raise SystemExit('unfilled placeholders in {}: {}'.format(template_name, leftover))
    return text


def write(path, text, force):
    if os.path.exists(path) and not force:
        raise SystemExit('refusing to overwrite {} (use --force)'.format(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as handle:
        handle.write(text)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    parser.add_argument('target', help='repository root to scaffold into')
    parser.add_argument('--name', required=True,
                        help='add-in name, CamelCase, no spaces (also the folder and entry module)')
    parser.add_argument('--command-name', default='Create Part',
                        help='button label of the first command, e.g. "Create Bracket"')
    parser.add_argument('--description', default=None,
                        help='one sentence for the manifest, tooltip and README')
    parser.add_argument('--author', default=None, help='manifest author (default: the add-in name)')
    parser.add_argument('--part-name', default=None,
                        help='name of the component the command creates (default: last word of the command name)')
    parser.add_argument('--panel-name', default=None,
                        help='name of the panel on the Utilities tab (default: spaced add-in name)')
    parser.add_argument('--force', action='store_true', help='overwrite existing files')
    parser.add_argument('--no-check', action='store_true', help='skip the post-scaffold sanity check')
    args = parser.parse_args()

    name = args.name
    if not re.match(r'^[A-Z][A-Za-z0-9]*$', name):
        raise SystemExit('--name must be CamelCase letters/digits starting with a capital, e.g. GuitarFrets')
    command_name = args.command_name.strip()
    cmd_slug = words_to_snake(command_name)
    part_name = args.part_name or (command_name.split()[-1] if command_name else 'Part')
    panel_name = args.panel_name or re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    description = args.description or '{}: {} from one dialog'.format(name, command_name.lower())

    context = {
        'NAME': name,
        'MATH_MODULE': camel_to_snake(name) + '_math',
        'COMMAND_NAME': command_name,
        'COMMAND_ID': 'cmdID_{}_{}'.format(name, words_to_camel(command_name)),
        'CMD_SLUG': cmd_slug,
        'CMD_CAMEL': words_to_camel(command_name),
        'PART_NAME': part_name,
        'PANEL_NAME': panel_name,
        'DESCRIPTION': description.replace('"', "'"),
        'AUTHOR': args.author or name,
        'UUID': str(uuid.uuid4()),
        'DATE': datetime.date.today().strftime('%B %Y'),
    }

    target = os.path.abspath(args.target)
    addin_dir = os.path.join(target, name)
    written = []

    files = {
        os.path.join(addin_dir, name + '.py'): 'ADDIN.py.tmpl',
        os.path.join(addin_dir, name + '.manifest'): 'ADDIN.manifest.tmpl',
        os.path.join(addin_dir, name + 'Command.py'): 'Command.py.tmpl',
        os.path.join(addin_dir, context['MATH_MODULE'] + '.py'): 'math.py.tmpl',
        os.path.join(addin_dir, 'constants.py'): 'constants.py.tmpl',
        os.path.join(target, 'tests', 'test_{}.py'.format(context['MATH_MODULE'])): 'test_math.py.tmpl',
        os.path.join(target, 'README.md'): 'README.md.tmpl',
        os.path.join(target, 'CHANGELOG.md'): 'CHANGELOG.md.tmpl',
        os.path.join(target, 'DEV_NOTES.md'): 'DEV_NOTES.md.tmpl',
        os.path.join(target, '.gitignore'): 'gitignore.tmpl',
    }
    for path, template in files.items():
        written.append(write(path, render(template, context), args.force))

    utilities_target = os.path.join(addin_dir, 'Fusion360Utilities')
    os.makedirs(utilities_target, exist_ok=True)
    for filename in os.listdir(UTILITIES_DIR):
        if filename.endswith('.py'):
            destination = os.path.join(utilities_target, filename)
            if os.path.exists(destination) and not args.force:
                raise SystemExit('refusing to overwrite {} (use --force)'.format(destination))
            shutil.copyfile(os.path.join(UTILITIES_DIR, filename), destination)
            written.append(destination)

    icons_script = os.path.join(target, 'scripts', 'make_icons.py')
    os.makedirs(os.path.dirname(icons_script), exist_ok=True)
    if not os.path.exists(icons_script) or args.force:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, 'make_icons.py'), icons_script)
        written.append(icons_script)

    written.extend(make_icon_set(os.path.join(addin_dir, 'resources', cmd_slug)))

    # Compile-check without leaving __pycache__ folders in the add-in.
    with tempfile.TemporaryDirectory() as scratch:
        for index, path in enumerate(written):
            if path.endswith('.py'):
                py_compile.compile(path, cfile=os.path.join(scratch, '{}.pyc'.format(index)),
                                   doraise=True)

    print('Scaffolded {} in {}:'.format(name, target))
    for path in written:
        print('  ' + os.path.relpath(path, target))

    if not args.no_check:
        print()
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, 'check_addin.py'),
                                 addin_dir])
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    print("""
Next steps:
  1. python -m pytest {rel_tests}            # the math is testable without Fusion
  2. Replace the example inputs/geometry in {name}/{name}Command.py and
     {name}/{math}.py (keep the structure), extend the tests.
  3. Install in Fusion: Utilities > Scripts and Add-Ins > Add-Ins > + > pick
     the {name}/ folder > Run. Iterate on tracebacks (they pop up in message
     boxes); the pure-python parts never need Fusion.
  4. Keep README.md, CHANGELOG.md and DEV_NOTES.md current as you go.
""".format(rel_tests=os.path.relpath(os.path.join(target, 'tests'), os.getcwd()),
           name=name, math=context['MATH_MODULE']))


if __name__ == '__main__':
    main()
