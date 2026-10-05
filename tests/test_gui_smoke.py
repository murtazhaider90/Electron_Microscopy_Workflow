"""Tk GUI smoke tests (marked gui; need a display / Xvfb)."""
import numpy as np
import pytest

EXPECTED_TABS = ['Structure & Orientation', 'Sample Preparation',
                 'Microscope Setup', 'TEM / HRTEM Image', 'Diffraction',
                 'Preview & Sweep', '2D Materials', 'Results & Export',
                 'Help / About']


@pytest.fixture
def tool(si_bulk):
    try:
        from ase.gui.gui import GUI
    except Exception as e:  # pragma: no cover
        pytest.skip(f"ASE GUI import failed: {e}")
    try:
        gui = GUI(images=[si_bulk])
    except Exception as e:  # no display
        pytest.skip(f"no display for Tk: {e}")
    import ase.gui.ui as ui
    ui.error = lambda *a, **k: None  # don't block on modal dialogs
    return gui.abtem_tem_window()


@pytest.mark.gui
def test_menu_item_registered(si_bulk):
    try:
        from ase.gui.gui import GUI
        gui = GUI(images=[si_bulk])
    except Exception as e:
        pytest.skip(f"no display: {e}")
    labels = [getattr(it, 'label', '') for _, items in gui.get_menu_data()
              for it in items]
    assert any('Workbench' in s for s in labels)
    assert hasattr(gui, 'abtem_tem_window')


@pytest.mark.gui
def test_expected_tabs(tool):
    names = [tool._notebook.tab(t, 'text') for t in tool._notebook.tabs()]
    assert names == EXPECTED_TABS


@pytest.mark.gui
def test_key_actions_exist(tool):
    for m in ('run', 'run_diffraction', 'run_benchmark', 'update_preview'):
        assert callable(getattr(tool, m, None))
    # combined preview+benchmark lives on one tab
    assert set(tool._sliders) == {'defocus', 'focal', 'angular', 'dose'}
    assert all(hasattr(tool, a) for a in
               ('bench_folder', 'bench_defocus', 'out_path', 'diff_out_path'))


@pytest.mark.gui
def test_window_fits_screen(tool):
    top = tool.win.win
    top.update_idletasks()
    h = int(top.geometry().split('+')[0].split('x')[1])
    assert h <= top.winfo_screenheight()


@pytest.mark.gui
@pytest.mark.slow
def test_preview_no_extra_windows(tool):
    before = len(tool._image_windows)
    tool.preview_image_size.value = 48
    tool.preview_wave_res.value = 48
    tool.update_preview()
    assert len(tool._image_windows) == before   # embedded, no popups
