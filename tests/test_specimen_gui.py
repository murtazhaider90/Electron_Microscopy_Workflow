"""Actual OpenGL framebuffer and Qt widget regression tests (Xvfb/Mesa)."""
import numpy as np
import pytest
from ase import Atoms
from abtem_ase_workbench.backend import apply_view_rotation

pytestmark = pytest.mark.gui


def test_asymmetric_framebuffer_projection():
    Qt = pytest.importorskip('PySide6.QtWidgets')
    pytest.importorskip('vispy')
    from abtem_ase_workbench.specimen.widget import SpecimenCanvas
    from abtem_ase_workbench.specimen import Specimen
    application = Qt.QApplication.instance() or Qt.QApplication([])
    atoms = Atoms('CHON', positions=[[0, 0, 0], [2.7, 0.4, 0.8], [-1.2, 2.6, -0.3], [0.6, -2.3, 1.7]])
    model = Specimen(atoms)
    canvas = SpecimenCanvas(model)
    canvas.show_cell = canvas.show_bonds = False
    canvas.resize(640, 480)
    canvas.show()
    application.processEvents()
    try:
        for dx, dy in [(0.31, -0.42), (-0.13, 0.27)]:
            model.view.rotate(dx, dy)
        canvas.fit()
        model.view.pan = np.array([17., -9.])
        canvas.refresh()
        application.processEvents()
        framebuffer = canvas.canvas.render()
        h, w = framebuffer.shape[:2]
        size = np.array(canvas.canvas.size)
        oriented = apply_view_rotation(**model.backend_inputs(), recenter=False)
        q = oriented.positions - model.view.pivot @ model.view.axes
        expected = q[:, :2]*[model.view.scale, -model.view.scale] + size/2 + model.view.pan
        xy, _ = canvas.displayed_coordinates()
        np.testing.assert_allclose(xy, expected, atol=1e-12)
        # Validate visible marker pixels at backend-predicted positions, not only
        # two functions that share the same projection implementation.
        background = np.array([17, 24, 39])
        for point in expected:
            x, y = np.rint(point * [w/size[0], h/size[1]]).astype(int)
            patch = framebuffer[y-4:y+5, x-4:x+5, :3]
            assert patch.size and np.max(np.linalg.norm(patch.astype(float)-background, axis=2)) > 40
        for point in [[20, 20], [w-20, h-20]]:
            np.testing.assert_allclose(framebuffer[point[1], point[0], :3], background, atol=1)
    finally:
        canvas.close()
        application.processEvents()


def test_editor_and_mouse_gesture():
    Qt = pytest.importorskip('PySide6.QtWidgets')
    pytest.importorskip('vispy')
    from types import SimpleNamespace as Event
    from abtem_ase_workbench.specimen.widget import SpecimenEditor
    application = Qt.QApplication.instance() or Qt.QApplication([])
    editor = SpecimenEditor(Atoms('CH', positions=[[0, 0, 0], [2, 1, 1]]))
    editor.show()
    application.processEvents()
    try:
        canvas = editor.viewer
        start = editor.model.view.axes
        canvas._mouse_press(Event(pos=(100, 100)))
        canvas._mouse_move(Event(pos=(145, 120), is_dragging=True, buttons=[1], modifiers=[]))
        canvas._mouse_release(Event(pos=(145, 120), modifiers=[]))
        assert not np.allclose(start, editor.model.view.axes)
        assert len(editor.model._undo) == 1
        editor.model.undo()
        np.testing.assert_allclose(start, editor.model.view.axes)
        canvas._mouse_press(Event(pos=(100, 100)))
        canvas._mouse_move(Event(pos=(120, 110), is_dragging=True, buttons=[2], modifiers=[]))
        canvas._mouse_release(Event(pos=(120, 110), modifiers=[]))
        np.testing.assert_allclose(start, editor.model.view.axes)
        scale = editor.model.view.scale
        canvas._wheel(Event(delta=(0, 1)))
        assert editor.model.view.scale > scale
        xy, _ = canvas.displayed_coordinates()
        canvas._mouse_press(Event(pos=xy[0]))
        canvas._mouse_release(Event(pos=xy[0], modifiers=[]))
        assert editor.model.selection == {0}
    finally:
        editor.viewer.close()
        editor.close()
        application.processEvents()


def test_empty_editor_render():
    Qt = pytest.importorskip('PySide6.QtWidgets')
    pytest.importorskip('vispy')
    from abtem_ase_workbench.specimen.widget import SpecimenEditor
    application = Qt.QApplication.instance() or Qt.QApplication([])
    editor = SpecimenEditor()
    editor.show()
    application.processEvents()
    try:
        assert editor.viewer.canvas.render().shape[2] == 4
        editor.model.add('C', [0, 0, 0])
        editor.model.select([0])
        editor.model.delete()
        assert len(editor.model.atoms) == 0
        assert editor.viewer.canvas.render().shape[2] == 4
    finally:
        editor.viewer.close()
        editor.close()
        application.processEvents()
