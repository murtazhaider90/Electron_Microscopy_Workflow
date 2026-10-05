#!/usr/bin/env python3
"""Optional: permanently integrate the abTEM tool into your ASE installation.

This copies the three modules into the ``ase/gui`` package and adds a
"abTEM TEM simulation ..." item to the Tools menu of ``ase gui`` by patching
``ase/gui/gui.py`` (a timestamped backup is made, and the patch is idempotent).

    python install.py            # install / patch
    python install.py --uninstall

If you would rather NOT modify your ASE installation, use ``run_gui.py``
instead -- it registers the tool at runtime with no source changes.
"""

import os
import sys
import shutil

MODULES = ('abtem_tem.py', 'abtem_tem_backend.py', 'abtem_2d_database.py')
HERE = os.path.dirname(os.path.abspath(__file__))

LAUNCHER_METHOD = (
    "\n"
    "    def abtem_tem_window(self, key=None):\n"
    "        from ase.gui.abtem_tem import ABTEMSimulation\n"
    "        return ABTEMSimulation(self)\n"
)
MENU_LINE_CONTENT = "M(_('Electron Microscopy Workbench'), self.abtem_tem_window),"
METHOD_ANCHOR = "return self.pipe('reciprocal', bandpath)"
MENU_ANCHOR = "M(_('Reciprocal space ...'), self.reciprocal),"


def ase_gui_dir():
    import ase.gui
    return os.path.dirname(ase.gui.__file__)


def _patch_gui(gui_path):
    with open(gui_path, 'r') as fh:
        src = fh.read()
    if 'abtem_tem_window' in src:
        print('  gui.py already patched -- skipping.')
        return True
    if METHOD_ANCHOR not in src or MENU_ANCHOR not in src:
        print('  WARNING: could not find the expected anchors in gui.py '
              '(ASE version differs).')
        print('  The menu item was NOT added. Use run_gui.py instead, or apply '
              'gui.py.patch manually.')
        return False

    backup = gui_path + '.abtem_backup'
    if not os.path.exists(backup):
        shutil.copy2(gui_path, backup)
        print('  backup written: %s' % backup)

    out = []
    for line in src.splitlines(keepends=True):
        out.append(line)
        if METHOD_ANCHOR in line:
            out.append(LAUNCHER_METHOD)
        elif MENU_ANCHOR in line:
            indent = line[:len(line) - len(line.lstrip())]
            out.append(indent + MENU_LINE_CONTENT + '\n')
    with open(gui_path, 'w') as fh:
        fh.write(''.join(out))
    print('  patched Tools menu + added launcher method.')
    return True


def install():
    d = ase_gui_dir()
    print('ASE gui package: %s' % d)
    for m in MODULES:
        shutil.copy2(os.path.join(HERE, m), os.path.join(d, m))
        print('  copied %s' % m)
    ok = _patch_gui(os.path.join(d, 'gui.py'))
    print('\nDone.' + ('' if ok else '  (menu not patched -- see warning above)'))
    print('Start ASE GUI normally:  ase gui   ->  Tools -> abTEM TEM simulation ...')


def uninstall():
    d = ase_gui_dir()
    gui_path = os.path.join(d, 'gui.py')
    backup = gui_path + '.abtem_backup'
    if os.path.exists(backup):
        shutil.copy2(backup, gui_path)
        os.remove(backup)
        print('  restored original gui.py from backup')
    else:
        print('  no gui.py backup found (leaving gui.py as-is)')
    for m in MODULES:
        p = os.path.join(d, m)
        if os.path.exists(p):
            os.remove(p)
            print('  removed %s' % m)
    pycache = os.path.join(d, '__pycache__')
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if f.startswith(('abtem_tem', 'abtem_2d_database', 'gui.')):
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass
    print('Uninstalled.')


if __name__ == '__main__':
    try:
        import ase  # noqa: F401
    except Exception:
        sys.exit('ERROR: ASE is not importable in this Python environment.')
    if '--uninstall' in sys.argv[1:]:
        uninstall()
    else:
        install()
