"""Optional PySide6/VisPy editor; no imports from the legacy Tk GUI."""
import sys
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as Qt
from vispy import app, scene
from ase.data.colors import jmol_colors
from .model import Specimen, build_specimen, element_number

app.use_app('pyside6')


class SpecimenCanvas(Qt.QWidget):
    """Orthographic scientific display with a single model-owned orientation.

    VisPy receives projected logical-pixel coordinates. Its fixed PanZoomCamera
    maps these to the framebuffer; it never rotates the specimen independently.
    """
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.show_bonds = self.show_cell = True
        self.canvas = scene.SceneCanvas(keys=None, bgcolor='#111827', parent=self)
        self.viewport = self.canvas.central_widget.add_view()
        self.viewport.camera = scene.PanZoomCamera(aspect=None)
        self.viewport.camera.interactive = False
        self.markers = scene.visuals.Markers(parent=self.viewport.scene, spherical=True)
        self.bonds = scene.visuals.Line(parent=self.viewport.scene, color='#94a3b8', connect='segments')
        self.cell = scene.visuals.Line(parent=self.viewport.scene, color='#38bdf8', connect='segments')
        layout = Qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas.native)
        self._press = self._last = None
        self._start_axes = None
        self._geometry_key = None
        self._geometry = None
        self.canvas.events.mouse_press.connect(self._mouse_press)
        self.canvas.events.mouse_move.connect(self._mouse_move)
        self.canvas.events.mouse_release.connect(self._mouse_release)
        self.canvas.events.mouse_wheel.connect(self._wheel)
        self.canvas.events.resize.connect(lambda event: self.refresh())
        model.observers.append(self.refresh)
        self.setToolTip('Drag: rotate • Right drag or Shift-drag: pan • Wheel: zoom • Click: select • Ctrl-click: toggle selection')
        self.setAccessibleName('Specimen 3D view')
        self.refresh()

    def closeEvent(self, event):
        if self.refresh in self.model.observers:
            self.model.observers.remove(self.refresh)
        self.canvas.close()
        super().closeEvent(event)

    def fit(self):
        self.model.view.fit(self.model.atoms, self.canvas.size)
        self.refresh()

    def displayed_coordinates(self):
        """Coordinates sent to the renderer before framebuffer scaling."""
        return self.model.view.project(self.model.atoms.positions, self.canvas.size)

    def refresh(self):
        w, h = self.canvas.size
        if w <= 0 or h <= 0:
            return
        self.viewport.camera.rect = (0, 0, w, h)
        atoms = self.model.atoms
        xy, z = self.displayed_coordinates()
        # Draw farther atoms first; nearest visible atom wins picking.
        order = np.argsort(z, kind='stable')
        colors = jmol_colors[atoms.numbers].copy()
        for index in self.model.selection:
            colors[index] = [1.0, 0.8, 0.15]
        # Markers use screen units; camera has no orientation state.
        pos = np.column_stack([xy[:, 0], h-xy[:, 1], np.zeros(len(xy))])
        self.markers.visible = len(atoms) > 0
        if len(atoms):
            self.markers.set_data(pos=pos[order].astype(np.float32), face_color=colors[order],
                                  edge_color='#f8fafc', size=18, edge_width=0.5)
        key = (self.model.revision, self.show_bonds, self.show_cell)
        if key != self._geometry_key:
            self._geometry = self.model.geometry(self.show_bonds, self.show_cell)
            self._geometry_key = key
        bonds, cell = self._geometry
        for visual, points in ((self.bonds, bonds), (self.cell, cell)):
            visual.visible = len(points) > 0
            if len(points):
                p, _ = self.model.view.project(points, (w, h))
                visual.set_data(pos=np.column_stack([p[:, 0], h-p[:, 1]]).astype(np.float32), connect='segments')
        self.canvas.update()

    def _mouse_press(self, event):
        self._press = self._last = np.asarray(event.pos, dtype=float)
        self._start_axes = self.model.view.axes

    def _mouse_move(self, event):
        if self._last is None or not event.is_dragging:
            return
        pos = np.asarray(event.pos, dtype=float)
        delta = pos-self._last
        if 2 in event.buttons or 'Shift' in event.modifiers:
            self.model.view.pan += delta
        elif 1 in event.buttons:
            self.model.view.rotate(delta[0]*0.008, delta[1]*0.008)
        self._last = pos
        self.refresh()

    def _mouse_release(self, event):
        if self._press is None:
            return
        if np.linalg.norm(np.asarray(event.pos)-self._press) < 4:
            i = self.model.view.pick(self.model.atoms.positions, self.canvas.size, event.pos)
            selection = set(self.model.selection) if 'Control' in event.modifiers else set()
            if i is not None:
                selection.symmetric_difference_update({i})
            self.model.select(selection)
        elif not np.allclose(self._start_axes, self.model.view.axes, atol=1e-14):
            final = self.model.view.axes
            self.model.view.set_axes(self._start_axes)
            self.model.orient(final)  # one undo entry per gesture
        self._press = self._last = None
        self._start_axes = None

    def _wheel(self, event):
        self.model.view.scale = float(np.clip(self.model.view.scale * 1.15**event.delta[1], 0.01, 1e5))
        self.refresh()


def numbers(text, count=None, integer=False):
    result = [int(v) if integer else float(v) for v in text.replace(',', ' ').split()]
    if count is not None and len(result) != count:
        raise ValueError('Enter {} numbers separated by spaces.'.format(count))
    if not np.isfinite(result).all():
        raise ValueError('Numbers must be finite.')
    return result


class SpecimenEditor(Qt.QWidget):
    """Embeddable editor. Access model.backend_inputs() for the simulation handoff."""
    def __init__(self, atoms=None, parent=None):
        super().__init__(parent)
        self.model = Specimen(atoms)
        self.viewer = SpecimenCanvas(self.model)
        self.setWindowTitle('Electron Microscopy Workbench — Specimen')
        self.resize(1100, 760)
        self.setStyleSheet("""
            QWidget { font-size: 13px; background: #111827; color: #e2e8f0; }
            QPushButton { padding: 8px 12px; background: #243247; border: 1px solid #3b4b62; border-radius: 5px; }
            QPushButton:hover { background: #334967; border-color: #38bdf8; }
            QPushButton:focus { border: 1px solid #38bdf8; }
            QGroupBox { margin-top: 12px; padding-top: 15px; border: 1px solid #3b4b62; border-radius: 5px; }
            QLineEdit { padding: 5px; background: #243247; border: 1px solid #3b4b62; }
        """)
        self._help = {}
        root = Qt.QVBoxLayout(self)
        toolbar = Qt.QHBoxLayout()
        root.addLayout(toolbar)
        for title, callback, help_text in [
            ('Open', self.open_file, 'Open an ASE-supported structure file. The last frame is loaded.'),
            ('Save', self.save_file, 'Save with ASE. Extended XYZ retains cell, PBC and orientation metadata.'),
            ('Build', self.builder, 'Create a crystal, slab, particle or nanotube with ASE.'),
            ('Undo', self.model.undo, 'Undo a structure edit or orientation gesture.'),
            ('Redo', self.model.redo, 'Restore an undone edit.'),
            ('Fit', self.viewer.fit, 'Fit the atoms in the view without changing orientation.')]:
            self.button(toolbar, title, callback, help_text)
        body = Qt.QHBoxLayout()
        root.addLayout(body, 1)
        body.addWidget(self.viewer, 1)
        panel = Qt.QWidget()
        form = Qt.QVBoxLayout(panel)
        panel.setMaximumWidth(300)
        body.addWidget(panel)
        self.status = Qt.QLabel()
        self.status.setWordWrap(True)
        form.addWidget(self.status)
        self.button(form, 'Edit selected atoms', self.edit_atoms, 'Move selected atoms by a displacement in Å or change their element.')
        self.button(form, 'Add atom', self.add_atom, 'Add an element at Cartesian x y z coordinates in Å.')
        self.button(form, 'Delete selected atoms', self.model.delete, 'Delete the highlighted atoms. Undo restores them.')
        self.button(form, 'Zone axis [u v w]', lambda: self.direction(False), 'Align a direct-lattice direction with the beam. Indices refer to the current cell.')
        self.button(form, 'Plane normal (h k l)', lambda: self.direction(True), 'Align a reciprocal-lattice plane normal with the beam. Requires a full-rank cell.')
        for title, attr in [('Bonds', 'show_bonds'), ('Cell', 'show_cell')]:
            check = Qt.QCheckBox(title)
            check.setChecked(True)
            check.setToolTip('Toggle display only; the ASE structure is unchanged.')
            check.toggled.connect(lambda checked, name=attr: self.display_option(name, checked))
            form.addWidget(check)
        advanced = Qt.QGroupBox('Advanced')
        advanced.setToolTip('Cell, periodicity, supercell, vacuum and exact matrix controls.')
        advanced.setCheckable(True)
        advanced.setChecked(False)
        form.addWidget(advanced)
        advanced_layout = Qt.QVBoxLayout(advanced)
        contents = Qt.QWidget()
        advanced_layout.addWidget(contents)
        controls = Qt.QVBoxLayout(contents)
        contents.hide()
        advanced.toggled.connect(contents.setVisible)
        for title, callback, tip in [
            ('Cell / PBC', self.cell_dialog, 'Cell vectors in Å and periodic boundary flags. Changing PBC changes physical topology.'),
            ('Repeat', self.repeat_dialog, 'Positive integer counts along cell vectors. PBC flags are preserved.'),
            ('Supercell', self.supercell_dialog, 'Integer 3×3 transformation of the cell, delegated to ASE.'),
            ('Wrap', self.model.wrap, 'Wrap atoms into periodic cell directions; nonperiodic directions remain unchanged.'),
            ('Center / vacuum', self.center_dialog, 'Center atoms and optionally add vacuum in Å on specified axes. PBC flags are preserved.'),
            ('Exact view matrix', self.matrix_dialog, 'Columns are screen right, up and beam. Positions project as positions × matrix.')]:
            self.button(controls, title, callback, tip)
        form.addStretch()
        self.model.observers.append(self.update_status)
        self.update_status()
        QtCore.QTimer.singleShot(0, self.viewer.fit)

    def button(self, layout, text, callback, tip):
        button = Qt.QPushButton(text)
        button.setToolTip(tip)
        button.setWhatsThis(tip)
        button.setAccessibleDescription(tip)
        self._help[button] = (text, tip)
        button.installEventFilter(self)
        button.clicked.connect(lambda: self.safe(callback))
        menu = Qt.QMenu(button)
        menu.addAction('Help', lambda: Qt.QMessageBox.information(self, text, tip))
        button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda p: menu.exec(button.mapToGlobal(p)))
        layout.addWidget(button)
        return button

    def eventFilter(self, watched, event):
        if watched in self._help and event.type() == QtCore.QEvent.Type.FocusIn:
            text, tip = self._help[watched]
            Qt.QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()), tip, watched)
        if watched in self._help and event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_F1:
            text, tip = self._help[watched]
            Qt.QMessageBox.information(self, text, tip)
            return True
        return super().eventFilter(watched, event)

    def safe(self, callback):
        try:
            callback()
        except Exception as error:
            Qt.QMessageBox.warning(self, 'Specimen operation', str(error))

    def update_status(self):
        a = self.model.atoms
        self.status.setText('{} atoms • {} selected\nPBC: {}\nÅngström coordinates'.format(len(a), len(self.model.selection), ' '.join('yes' if p else 'no' for p in a.pbc)))

    def display_option(self, name, value):
        setattr(self.viewer, name, value)
        self.viewer.refresh()

    def fields(self, title, defaults, help_text):
        dialog = Qt.QDialog(self)
        dialog.setWindowTitle(title)
        layout = Qt.QFormLayout(dialog)
        info = Qt.QLabel(help_text)
        info.setWordWrap(True)
        layout.addRow(info)
        inputs = {}
        for name, value in defaults.items():
            field = Qt.QLineEdit(str(value))
            field.setToolTip(help_text)
            field.setWhatsThis(help_text)
            inputs[name] = field
            layout.addRow(name, field)
        buttons = Qt.QDialogButtonBox(Qt.QDialogButtonBox.StandardButton.Ok | Qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            return {name: field.text().strip() for name, field in inputs.items()}
        return None

    def open_file(self):
        path, _ = Qt.QFileDialog.getOpenFileName(self, 'Open structure', '', 'Structures (*)')
        if path:
            self.model.open(path)
            self.viewer.fit()

    def save_file(self):
        path, _ = Qt.QFileDialog.getSaveFileName(self, 'Save structure', 'specimen.extxyz', 'Extended XYZ (*.extxyz);;All files (*)')
        if path:
            self.model.save(path)

    def add_atom(self):
        v = self.fields('Add atom', {'Element': 'C', 'Position (Å)': '0 0 0'}, 'Cartesian coordinates in Å. The cell and periodicity stay as configured.')
        if v:
            self.model.add(v['Element'], numbers(v['Position (Å)'], 3))

    def edit_atoms(self):
        if not self.model.selection:
            raise ValueError('Select atoms by clicking them first. Ctrl-click selects several.')
        v = self.fields('Edit selected atoms', {'Displacement (Å)': '0 0 0', 'Element (optional)': ''}, 'Displacement moves every selected atom. An element symbol changes every selected atom.')
        if v:
            displacement = numbers(v['Displacement (Å)'], 3)
            symbol = v['Element (optional)']
            number = element_number(symbol) if symbol else None
            selected = sorted(self.model.selection)
            def edit(a):
                a.positions[selected] += displacement
                if number is not None:
                    a.numbers[selected] = number
            self.model.edit('Edit selected atoms', edit)

    def direction(self, plane):
        v = self.fields('Plane normal' if plane else 'Zone axis', {'Indices': '0 0 1'}, 'Enter three integer indices. Plane normals use the reciprocal cell; zone axes use the direct cell.')
        if v:
            (self.model.plane_normal if plane else self.model.zone_axis)(numbers(v['Indices'], 3, True))

    def repeat_dialog(self):
        v = self.fields('Repeat', {'Counts': '2 2 1'}, 'Positive integer counts along a, b, c. ASE repeats atoms and cell; PBC is preserved.')
        if v:
            self.model.repeat(numbers(v['Counts'], 3, True))
            self.viewer.fit()

    def supercell_dialog(self):
        v = self.fields('Supercell', {'Matrix': '2 0 0 0 2 0 0 0 1'}, 'Nine integer entries, row by row. Matrix must be nonsingular.')
        if v:
            self.model.supercell(np.array(numbers(v['Matrix'], 9, True)).reshape(3, 3))
            self.viewer.fit()

    def center_dialog(self):
        v = self.fields('Center / vacuum', {'Vacuum (Å, optional)': '', 'Axes': '0 1 2'}, 'Vacuum is the gap on each side. Use axis 2 for a slab. This does not enable periodicity.')
        if v:
            axes = numbers(v['Axes'], integer=True)
            if not axes or any(i not in (0, 1, 2) for i in axes):
                raise ValueError('Axes must be 0, 1 or 2.')
            self.model.center(float(v['Vacuum (Å, optional)']) if v['Vacuum (Å, optional)'] else None, tuple(axes))
            self.viewer.fit()

    def cell_dialog(self):
        a = self.model.atoms
        v = self.fields('Cell / PBC', {'Cell (Å)': ' '.join(str(x) for x in a.cell.array.ravel()), 'PBC': ' '.join(str(int(p)) for p in a.pbc), 'Scale atoms (0 or 1)': '0'}, 'Nine cell entries row by row in Å. PBC flags are 0 or 1 for a, b, c. Scale atoms preserves fractional coordinates.')
        if v:
            cell = np.array(numbers(v['Cell (Å)'], 9)).reshape(3, 3)
            pbc = numbers(v['PBC'], 3, True)
            scale = numbers(v['Scale atoms (0 or 1)'], 1, True)[0]
            if any(p not in (0, 1) for p in pbc+[scale]):
                raise ValueError('Flags must be 0 or 1.')
            def edit(a):
                a.set_cell(cell, scale_atoms=bool(scale))
                a.set_pbc(pbc)
            self.model.edit('Cell / PBC', edit)

    def matrix_dialog(self):
        v = self.fields('Exact view matrix', {'Matrix': ' '.join(format(x, '.17g') for x in self.model.view.axes.ravel())}, 'Nine values row by row; must be a right-handed orthonormal rotation. This exact matrix is passed to the backend, without Euler reconstruction.')
        if v:
            self.model.orient(np.array(numbers(v['Matrix'], 9)).reshape(3, 3))

    def builder(self):
        kinds = ['bulk', 'fcc111', 'bcc110', 'hcp0001', 'surface', 'graphene', 'mx2', 'icosahedron', 'decahedron', 'octahedron', 'nanotube']
        kind, ok = Qt.QInputDialog.getItem(self, 'ASE builder', 'Structure type', kinds, editable=False)
        if not ok:
            return
        recipes = {
            'bulk': ({'name': 'Si', 'crystalstructure': 'diamond', 'a': '5.43'}, 'Crystal lattice parameter a in Å. ASE uses its standard primitive cell.'),
            'fcc111': ({'symbol': 'Au', 'size': '3 3 4', 'vacuum': '8'}, 'FCC (111) slab. Size is x, y repetitions and layers; vacuum in Å.'),
            'bcc110': ({'symbol': 'Fe', 'size': '3 3 4', 'vacuum': '8'}, 'BCC (110) slab. Size is repetitions and layers; vacuum in Å.'),
            'hcp0001': ({'symbol': 'Ti', 'size': '3 3 4', 'vacuum': '8'}, 'HCP basal slab. Size is repetitions and layers; vacuum in Å.'),
            'surface': ({'lattice': 'Au', 'indices': '1 1 1', 'layers': '4', 'vacuum': '8'}, 'General ASE surface with Miller indices and layer count. ASE selects the conventional bulk lattice.'),
            'graphene': ({'a': '2.46', 'size': '3 3 1', 'vacuum': '8'}, 'Graphene lattice parameter and vacuum in Å; in-plane periodicity.'),
            'mx2': ({'formula': 'MoS2', 'kind': '2H', 'a': '3.18', 'thickness': '3.19', 'size': '3 3 1', 'vacuum': '8'}, 'Transition-metal dichalcogenide. a, thickness and vacuum in Å.'),
            'icosahedron': ({'symbol': 'Pt', 'noshells': '3'}, 'Finite icosahedral particle; shell count includes the center atom.'),
            'decahedron': ({'symbol': 'Pt', 'p': '3', 'q': '2', 'r': '0'}, 'ASE decahedron: p atoms on perpendicular edges, q on parallel edges, r Marks re-entrance depth.'),
            'octahedron': ({'symbol': 'Pt', 'length': '4', 'cutoff': '1'}, 'Finite FCC octahedron: edge length in atoms and truncation cutoff.'),
            'nanotube': ({'n': '6', 'm': '0', 'length': '2', 'bond': '1.42', 'symbol': 'C'}, 'Chiral indices n,m; axial unit repetitions; bond length in Å. ASE makes the tube periodic along its axis.')}
        defaults, tip = recipes[kind]
        v = self.fields('Build '+kind, defaults, tip)
        if v:
            integer = {'layers', 'noshells', 'p', 'q', 'r', 'cutoff', 'n', 'm'}
            strings = {'name', 'symbol', 'crystalstructure', 'lattice', 'formula', 'kind'}
            parameters = {}
            for key, value in v.items():
                if key in strings:
                    parameters[key] = value
                elif key in {'size', 'indices'}:
                    parameters[key] = tuple(numbers(value, 3, True))
                elif key in integer or key == 'length':
                    parameters[key] = int(value)
                else:
                    parameters[key] = float(value)
            self.model.replace(build_specimen(kind, **parameters))
            self.viewer.fit()


def main():
    application = Qt.QApplication.instance() or Qt.QApplication(sys.argv)
    application.setStyle('Fusion')
    editor = SpecimenEditor()
    editor.show()
    return application.exec()


if __name__ == '__main__':
    sys.exit(main())
