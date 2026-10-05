"""Zero-touch launcher: register the Workbench on the ASE GUI class, then
start ASE GUI exactly as ``ase gui`` would so every normal argument (file
names, ``-R`` rotations, etc.) works unchanged.

Does NOT edit your ASE installation. For a permanent menu-item install, use
``install.py`` from the package root.
"""
import sys


def register_tool():
    """Attach the tool launcher + menu item to the ``GUI`` class in place."""
    import ase.gui.gui as guimod
    import ase.gui.ui as ui
    from ase.gui.i18n import _

    if getattr(guimod.GUI, "_abtem_registered", False):
        return

    def abtem_tem_window(self, key=None):
        from abtem_ase_workbench.gui import ABTEMSimulation
        return ABTEMSimulation(self)

    guimod.GUI.abtem_tem_window = abtem_tem_window

    _orig_get_menu_data = guimod.GUI.get_menu_data
    tools_title = _("_Tools")
    item_label = _("Electron Microscopy Workbench")

    def get_menu_data(self):
        data = _orig_get_menu_data(self)
        item = ui.MenuItem(item_label, self.abtem_tem_window)
        for entry in data:
            if entry[0] == tools_title:
                entry[1].append(item)
                break
        else:
            data.insert(-1, (_("Microscopy"), [item]))
        return data

    guimod.GUI.get_menu_data = get_menu_data
    guimod.GUI._abtem_registered = True


def main(argv=None):
    """Entry point for the ``abtem-ase-gui`` console command."""
    argv = list(sys.argv[1:] if argv is None else argv)
    register_tool()
    try:
        from ase.cli.main import main as ase_main
        return ase_main(args=["gui"] + argv)
    except SystemExit:
        raise
    except Exception:
        # Minimal fallback launcher.
        from ase.atoms import Atoms
        from ase.gui.gui import GUI
        from ase.gui.images import Images
        images = Images()
        if argv:
            images.read(argv)
        else:
            images.initialize([Atoms()])
        GUI(images).run()


if __name__ == "__main__":
    main()
