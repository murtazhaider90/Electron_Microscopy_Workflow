"""Windows GUI entry point for the packaged Electron Microscopy Workbench.

Built with PyInstaller in windowed mode so users can double-click the .exe
without opening PowerShell or a console window. Any file dropped onto the exe
(or passed on the command line) is forwarded to ASE GUI.
"""
from abtem_ase_workbench.launcher import main


if __name__ == "__main__":
    main()
