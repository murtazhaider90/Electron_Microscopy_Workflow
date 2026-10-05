"""Phase-2 GUI cleanup checks (marked gui)."""
import pytest

EXPECTED_TABS = ['Structure & Orientation', 'Sample Preparation',
                 'Microscope Setup', 'TEM / HRTEM Image', 'Diffraction',
                 'Preview & Sweep', '2D Materials', 'Results & Export',
                 'Help / About']


@pytest.fixture
def tool(si_bulk):
    try:
        from ase.gui.gui import GUI
        gui = GUI(images=[si_bulk])
    except Exception as e:
        pytest.skip(f"no display: {e}")
    import ase.gui.ui as ui
    ui.error = lambda *a, **k: None
    ui.ask_question = lambda *a, **k: True
    return gui.abtem_tem_window()


@pytest.mark.gui
def test_nine_tabs_and_title(tool):
    names = [tool._notebook.tab(t, 'text') for t in tool._notebook.tabs()]
    assert names == EXPECTED_TABS
    assert 'Workbench' in tool.win.win.title()


@pytest.mark.gui
def test_new_widgets_exist(tool):
    for a in ('preset_box', 'rep_x', 'rep_y', 'rep_z', 'vacuum',
              'results_listbox', 'lbl_structure', 'lbl_sweep_count'):
        assert hasattr(tool, a), a


@pytest.mark.gui
def test_preset_applies(tool):
    tool.preset_box.widget.current(3)   # HRTEM 300 kV
    tool.on_apply_preset()
    assert float(tool.voltage.value) == 300.0


@pytest.mark.gui
def test_repeat_builds_supercell(tool):
    tool.rep_x.value = 2
    tool.rep_y.value = 1
    tool.rep_z.value = 1
    tool.on_apply_repeat()
    assert len(tool.gui.atoms) == 16   # Si8 * 2


@pytest.mark.gui
def test_sweep_count_estimate(tool):
    tool.bench_defocus.value = '-1,-2,-3'
    tool.bench_focal.value = '2,4'
    tool.bench_angular.value = '0.2e-3'
    tool._update_sweep_count()
    assert '6 images' in tool.lbl_sweep_count.text


@pytest.mark.gui
def test_validation(tool):
    # periodic Si with a huge grid -> soft warning, no hard error
    tool.image_size.value = 4096
    tool.wave_res.value = 4096
    hard, soft = tool._validate_before('image')
    assert not hard
    assert any('Large grid' in s for s in soft)


@pytest.mark.gui
def test_repro_script(tool):
    s = tool._build_repro_script()
    assert 'simulate_tem_from_atoms' in s and 'view_axes' in s


@pytest.mark.gui
def test_current_view_matrix_is_exact_source(tool):
    import numpy as np
    axes = np.asarray(tool.gui.axes, float).copy()
    assert np.array_equal(tool._current_view_axes(), axes)


@pytest.mark.gui
def test_structure_summary(tool):
    tool._update_structure_summary()
    assert 'Si8' in tool.lbl_structure.text
