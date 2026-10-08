"""abtem_tem.py -- ASE GUI tool: "abTEM TEM Simulation".

A surgical tool window that plugs into ASE GUI. It reads the *currently edited*
Atoms object from the running GUI (``gui.atoms``), copies it, applies the exact
current ASE view matrix (``gui.axes``) to that copy, and runs an abTEM
multislice TEM simulation on that copy. The user's edited structure is never
mutated.

Layout
------
The controls are organised into a ``ttk.Notebook`` (tabs: Orientation + Run,
Microscope, Preview, Benchmark). Each tab is a scrollable ``tk.Canvas`` frame so
the window stays laptop-sized and the mouse wheel / trackpad / scrollbar can
reach every control. A fixed bottom action bar (Run TEM / Update Preview / Run
Benchmark / Close) is always visible.

Live view <-> fields two-way sync
---------------------------------
ASE GUI stores the current view as a 3x3 matrix ``gui.axes`` (built by
``ase.utils.rotate`` and updated live on mouse-drag). Projection is
``positions @ gui.axes`` so **column 2 is the screen-depth / beam axis**.
  * Mouse rotates the ASE view -> a Tk ``after(...)`` poll reads
    ``ase.utils.irotate(gui.axes)`` and writes the X/Y/Z fields.
  * User edits an X/Y/Z field -> ``gui.axes = ase.utils.rotate('{x}x,{y}y,{z}z')``
    and ``gui.draw()`` rotate the *existing* ASE GUI canvas in place.
Guard flags plus a keyboard-focus check break the feedback loop and avoid
clobbering a field mid-typing. Reading/writing the view never mutates the
atoms and never runs abTEM; at run time the exact ``gui.axes`` matrix itself
is sent to the backend. X/Y/Z are only a human-friendly editor/readout for
that same orientation.

Front end    : ASE GUI (Tkinter) via ``ase.gui.ui``.
Backend      : ``abtem_tem_backend`` (Qt-free / Tk-free).
Image display: matplotlib embedded in a Tk widget via FigureCanvasTkAgg -- no
               ``plt.show()``, so it never starts a competing mainloop.
"""

import os

import numpy as np

import ase.gui.ui as ui
from ase.gui.i18n import _
from ase.utils import irotate, rotate

# Tolerant backend import: works whether the backend lives inside the ase.gui
# package (fork) or sits on sys.path next to a user script.
# Backend / database: prefer the package module, fall back to top-level
# modules (installed next to the GUI inside ase.gui, or on sys.path).
try:
    from abtem_ase_workbench.backend import (
        simulate_tem_from_atoms, simulate_diffraction_from_atoms,
        apply_view_rotation, HAVE_ABTEM,
    )
except Exception:
    try:
        from ase.gui.abtem_tem_backend import (
            simulate_tem_from_atoms, simulate_diffraction_from_atoms,
            apply_view_rotation, HAVE_ABTEM,
        )
    except Exception:
        try:
            from abtem_tem_backend import (
                simulate_tem_from_atoms, simulate_diffraction_from_atoms,
                apply_view_rotation, HAVE_ABTEM,
            )
        except Exception:
            simulate_tem_from_atoms = None
            simulate_diffraction_from_atoms = None
            apply_view_rotation = None
            HAVE_ABTEM = False

# 2D-materials database helper (optional; import-tolerant).
try:
    from abtem_ase_workbench import database_2d as db2d
except Exception:
    try:
        from ase.gui import abtem_2d_database as db2d
    except Exception:
        try:
            import abtem_2d_database as db2d
        except Exception:
            db2d = None

from abtem_ase_workbench.orientation import (
    set_view_axes as _ori_set_view_axes,
    reduced_triples as _ori_reduced_triples,
    nearest_zone_axis as _ori_nearest_zone_axis,
)
from abtem_ase_workbench.presets import INSTRUMENT_PRESETS as _PRESETS
from abtem_ase_workbench.validators import validate_run as _validate_run
from abtem_ase_workbench.export import build_repro_script as _build_repro_script_fn


class _Panel:
    """Packs ASE ``ui`` widgets into a given frame (mirrors ui.Window.add).

    Lets us reuse the exact same ``ui`` widget objects (so ``.value`` and the
    sync/run/benchmark code are untouched) while placing them inside our own
    scrollable tab frames instead of one tall column.
    """

    def __init__(self, frame):
        self.frame = frame

    def add(self, stuff, anchor='w'):
        if isinstance(stuff, str):
            stuff = ui.Label(stuff)
        elif isinstance(stuff, list):
            stuff = ui.Row(stuff)
        stuff.pack(self.frame, anchor=anchor)
        return stuff


class ABTEMSimulation:
    """Tool window: live view readout + X/Y/Z rotation + abTEM TEM simulation."""

    VIEW_POLL_MS = 150   # live-readout refresh interval
    PREVIEW_PX = 192     # interactive-preview image size (kept small on purpose)

    def __init__(self, gui):
        import tkinter as tk
        from tkinter import ttk

        self.gui = gui
        self._image_windows = []   # keep refs so canvases are not GC'd
        self._last_view_angles = (0.0, 0.0, 0.0)
        # Guard flags to break the two-way sync feedback loop.
        self._syncing_from_view = False
        self._syncing_from_fields = False
        self._tab_scrollers = []          # [(canvas, inner_frame), ...]
        self._preview_canvas = None
        self._preview_fig = None
        self._preview_ax = None
        self._preview_after_id = None
        self._sliders = {}          # key -> (scale, value_label, field, fmt)
        self._syncing_sliders = False
        self._notebook = None
        self._preview_tab = None
        self._diff_tab = None
        self._diff_canvas = None
        self._diff_fig = None
        self._diff_ax = None
        self._image_tab = None
        self._image_canvas = None
        self._image_fig = None
        self._image_ax = None
        self._results_tab = None
        self._session_outputs = []        # (path, kind) written this session
        self._last_meta = None
        self.lbl_structure = None

        # Miller / orientation provenance (recorded in the run's JSON).
        self.orientation_source = 'mouse_view'   # manual_angles/zone_axis/
        self.zone_axis_uvw = None                #   plane_normal/mouse_view
        self.plane_hkl = None
        self.nearest_zone_axis = None
        self.nearest_zone_axis_error_deg = None
        self._last_axes = None            # last axes we observed/set (mouse detect)
        self._last_beam = None            # last beam dir used for zone readout
        self._triples_cache = None        # cached reduced [uvw] list
        self._triples_cache_n = None

        # 2D-materials database provenance (recorded in the run's JSON).
        self.structure_source = None      # 2dmatpedia_json/c2db/local_file/...
        self.structure_database_id = None
        self.structure_formula = None
        self.structure_name = None
        self.structure_metadata = {}
        self.structure_pbc = None
        self._db_entries = []             # all loaded Entry objects
        self._db_filtered = []            # currently shown (filtered) entries

        win = self.win = ui.Window(_('ASE Electron Microscopy Workbench'))
        top = win.win

        # Sane default size, capped to the screen height (laptop-friendly and
        # robust to Windows display scaling, since content scrolls).
        try:
            top.update_idletasks()
            screen_h = top.winfo_screenheight()
            height = min(800, max(420, screen_h - 120))
            top.geometry('680x{}'.format(int(height)))
            top.minsize(520, 440)
        except Exception:
            pass

        # ---- Fixed bottom action bar (packed first -> always visible) ----
        action = tk.Frame(top)
        action.pack(side='bottom', fill='x', padx=6, pady=(2, 6))
        tk.Button(action, text=_('Run TEM / HRTEM Image'),
                  command=self.run).pack(side='left', padx=3)
        tk.Button(action, text=_('Run Diffraction Pattern'),
                  command=self.run_diffraction).pack(side='left', padx=3)
        tk.Button(action, text=_('Update Quick Preview'),
                  command=self.update_preview).pack(side='left', padx=3)
        tk.Button(action, text=_('Close'),
                  command=self.win.close).pack(side='right', padx=3)

        # ---- Status line (just above the action bar, always visible) -----
        self.status = ui.Label('')
        self.status.pack(top, side='bottom', anchor='w')

        # ---- Title + subtitle (always visible) ---------------------------
        ui.Label(_('ASE Electron Microscopy Workbench'),
                 color='#003366').pack(top, side='top', anchor='w')
        ui.Label(_('ASE structure → abTEM simulation pipeline. Runs on a COPY '
                   'of the current structure; your edited structure is not '
                   'modified.'), color='gray').pack(top, side='top', anchor='w')
        if not HAVE_ABTEM:
            ui.Label(_('abTEM is not installed — `pip install abtem` to enable '
                       'simulation.'), color='red').pack(
                           top, side='top', anchor='w')

        # ---- Tabbed, scrollable body -------------------------------------
        nb = self._notebook = ttk.Notebook(top)
        nb.pack(side='top', fill='both', expand=True, padx=4, pady=4)

        p_struct, _a = self._make_tab(nb, _('Structure & Orientation'))
        p_prep, _b = self._make_tab(nb, _('Sample Preparation'))
        p_scope, _c = self._make_tab(nb, _('Microscope Setup'))
        p_image, self._image_tab = self._make_tab(nb, _('TEM / HRTEM Image'))
        p_diff, self._diff_tab = self._make_tab(nb, _('Diffraction'))
        p_pb, self._preview_tab = self._make_tab(nb, _('Preview & Sweep'))
        p_db, _d = self._make_tab(nb, _('2D Materials'))
        p_res, self._results_tab = self._make_tab(nb, _('Results & Export'))
        p_help, _e = self._make_tab(nb, _('Help / About'))

        # Build order matters: Microscope creates self.defocus etc. that the
        # Preview sliders and other tabs read.
        self._build_microscope_tab(p_scope)
        self._build_orientation_tab(p_struct)
        self._build_sample_prep_tab(p_prep)
        self._build_image_tab(p_image)
        self._build_diffraction_tab(p_diff)
        self._build_preview_benchmark_tab(p_pb)
        self._build_database_tab(p_db)
        self._build_results_tab(p_res)
        self._build_help_tab(p_help)

        # ---- Mouse-wheel scrolling for every tab -------------------------
        for canvas, inner in self._tab_scrollers:
            self._bind_wheel_recursive(canvas, canvas)
            self._bind_wheel_recursive(inner, canvas)

        # Keep preview sliders in step with the Microscope fields when the
        # Preview tab is opened.
        try:
            nb.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        except Exception:
            pass

        # ---- Start the live readout loop ---------------------------------
        self._update_view_readout()

    # ---------------------------------------------------- layout helpers
    def _make_tab(self, notebook, title):
        """Add a vertically-scrollable tab; return (panel, outer_frame)."""
        import tkinter as tk
        outer = tk.Frame(notebook)
        notebook.add(outer, text=title)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vbar = tk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        inner = tk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor='nw')

        def _on_inner_configure(event, c=canvas):
            c.configure(scrollregion=c.bbox('all'))
        inner.bind('<Configure>', _on_inner_configure)

        def _on_canvas_configure(event, c=canvas, wid=window_id):
            c.itemconfigure(wid, width=event.width)   # inner tracks canvas width
        canvas.bind('<Configure>', _on_canvas_configure)

        self._tab_scrollers.append((canvas, inner))
        return _Panel(inner), outer

    def _bind_wheel_recursive(self, widget, canvas):
        """Bind wheel/trackpad scroll on a widget and all its descendants."""
        try:
            widget.bind('<MouseWheel>', lambda e, c=canvas: self._wheel(e, c))
            widget.bind('<Button-4>', lambda e, c=canvas: self._wheel(e, c))
            widget.bind('<Button-5>', lambda e, c=canvas: self._wheel(e, c))
        except Exception:
            pass
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self._bind_wheel_recursive(child, canvas)

    @staticmethod
    def _wheel(event, canvas):
        num = getattr(event, 'num', None)
        if num == 4:                       # Linux wheel up
            canvas.yview_scroll(-3, 'units')
        elif num == 5:                     # Linux wheel down
            canvas.yview_scroll(3, 'units')
        else:                              # Windows / macOS
            delta = getattr(event, 'delta', 0)
            canvas.yview_scroll(-3 if delta > 0 else 3, 'units')
        return 'break'

    # ------------------------------------------------------- tab builders
    def _build_orientation_tab(self, p):
        p.add(ui.Label(_('Current structure'), color='#0055aa'))
        self.lbl_structure = ui.Label(_('(no structure)'), justify='left')
        p.add(self.lbl_structure)

        p.add(ui.Label(_('Current ASE view orientation (live)'),
                       color='#0055aa'))
        p.add(_('Rotate the structure in the ASE view with the mouse, or type '
                'X/Y/Z angles below — the two stay in sync.'))
        self.lbl_dir = ui.Label(_('View / beam direction:  --'))
        self.lbl_matrix = ui.Label(_('View matrix:  --'), justify='left')
        p.add(self.lbl_dir)
        p.add(self.lbl_matrix)

        p.add(ui.Label(_('Rotation angles (applied order X → Y → Z)'),
                       color='#0055aa'))
        p.add(_('Editing a field rotates the ASE view in the same window.'))
        p.add(_('Rotation cell mode (how the simulation box is treated):'))
        self.rot_mode = ui.RadioButtons(
            [_('Auto (follow periodic boundary conditions)'),
             _('Finite particle: rotate atoms only (keep box fixed)'),
             _('Periodic crystal: rotate atoms + cell together')],
            values=['auto', 'finite', 'periodic'], vertical=True)
        try:
            is_periodic = bool(np.any(self.gui.atoms.pbc)) \
                if self.gui.atoms is not None else False
        except Exception:
            is_periodic = False
        self.rot_mode.value = 'periodic' if is_periodic else 'finite'
        p.add(self.rot_mode)

        # SpinBox `callback` fires on arrow-clicks and on Enter; <FocusOut>
        # (bound below) commits a typed value when the field loses focus.
        self.rx = ui.SpinBox(0.0, -360.0, 360.0, 1.0, self._on_field_changed,
                             rounding=3, width=8)
        self.ry = ui.SpinBox(0.0, -360.0, 360.0, 1.0, self._on_field_changed,
                             rounding=3, width=8)
        self.rz = ui.SpinBox(0.0, -360.0, 360.0, 1.0, self._on_field_changed,
                             rounding=3, width=8)
        p.add([_('X rotation (degrees):'), self.rx])
        p.add([_('Y rotation (degrees):'), self.ry])
        p.add([_('Z rotation (degrees):'), self.rz])
        for f in (self.rx, self.ry, self.rz):
            try:
                f.widget.bind('<FocusOut>',
                              lambda event: self._on_field_changed())
            except Exception:
                pass

        # ---- Miller indices / zone axis ---------------------------------
        p.add(ui.Label(_('Crystallographic orientation (Miller indices)'),
                       color='#0055aa'))
        p.add(_('Zone axis [u v w] = beam direction through the crystal.  '
                'Plane (h k l) = direction of the plane normal.'))
        p.add(_('Selecting Miller indices only changes the view and the X/Y/Z '
                'fields; abTEM still rotates the atoms, not a screenshot.'))
        try:
            finite = not bool(np.any(self.gui.atoms.pbc)) \
                if self.gui.atoms is not None else True
        except Exception:
            finite = True
        if finite:
            p.add(ui.Label(_('Note: Miller indices are most meaningful for '
                             'crystalline periodic cells.'), color='gray'))

        self.lbl_zone = ui.Label(_('Nearest zone axis:  --'))
        p.add(self.lbl_zone)
        self.zone_max_index = ui.SpinBox(4, 1, 12, 1, width=5)
        self.zone_tol = ui.SpinBox(5.0, 0.0, 90.0, 0.5, rounding=1, width=6)
        p.add([_('Max Miller index (for readout):'), self.zone_max_index,
               _('  Tolerance (degrees):'), self.zone_tol])

        self.uvw_u = ui.SpinBox(1, -20, 20, 1, width=4)
        self.uvw_v = ui.SpinBox(0, -20, 20, 1, width=4)
        self.uvw_w = ui.SpinBox(0, -20, 20, 1, width=4)
        p.add([_('Zone axis [u v w]:'), self.uvw_u, self.uvw_v, self.uvw_w])
        p.add(ui.Button(_('Set View to Zone Axis [u v w]'),
                        self._on_set_zone_axis))
        p.add([ui.Button('[100]', self._on_set_zone_axis, (1, 0, 0)),
               ui.Button('[010]', self._on_set_zone_axis, (0, 1, 0)),
               ui.Button('[001]', self._on_set_zone_axis, (0, 0, 1)),
               ui.Button('[110]', self._on_set_zone_axis, (1, 1, 0)),
               ui.Button('[111]', self._on_set_zone_axis, (1, 1, 1))])

        self.hkl_h = ui.SpinBox(1, -20, 20, 1, width=4)
        self.hkl_k = ui.SpinBox(0, -20, 20, 1, width=4)
        self.hkl_l = ui.SpinBox(0, -20, 20, 1, width=4)
        p.add([_('Plane normal (h k l):'), self.hkl_h, self.hkl_k, self.hkl_l])
        p.add(ui.Button(_('Set View Normal to Plane (h k l)'),
                        self._on_set_plane_normal))
        p.add([ui.Button('(100)', self._on_set_plane_normal, (1, 0, 0)),
               ui.Button('(110)', self._on_set_plane_normal, (1, 1, 0)),
               ui.Button('(111)', self._on_set_plane_normal, (1, 1, 1))])

    def _build_sample_prep_tab(self, p):
        import tkinter as tk
        p.add(ui.Label(_('Sample preparation'), color='#0055aa'))
        p.add(_('Set boundary conditions and vacuum before simulating. 2D '
                'materials use periodic x/y and vacuum along z.'))

        p.add(ui.Label(_('Vacuum & centering'), color='#0055aa'))
        self.vacuum = ui.SpinBox(18.0, 0.0, 100.0, 1.0, rounding=1, width=6)
        p.add([_('Vacuum along z (Å):'), self.vacuum])
        p.add(ui.Button(_('Center Structure in Box'), self.on_center_only))

        p.add(ui.Label(_('Boundary conditions'), color='#0055aa'))
        p.add([ui.Button(_('Set as Finite Particle (no PBC)'),
                         self.on_set_flake),
               ui.Button(_('Set as Fully Periodic Crystal'),
                         self.on_set_periodic)])
        p.add(ui.Button(_('Center Slab + Set 2D PBC (periodic x/y, vacuum z)'),
                        self.on_center_slab_2d))
        p.add(ui.Button(_('Set as 2D Slab (periodic x/y) without recentering'),
                        self.on_set_2d_slab))

        p.add(ui.Label(_('Supercell / repeat'), color='#0055aa'))
        self.rep_x = ui.SpinBox(1, 1, 20, 1, width=4)
        self.rep_y = ui.SpinBox(1, 1, 20, 1, width=4)
        self.rep_z = ui.SpinBox(1, 1, 20, 1, width=4)
        p.add([_('Repeat (nx, ny, nz):'), self.rep_x, self.rep_y, self.rep_z])
        p.add(ui.Button(_('Apply Repeat / Build Supercell'),
                        self.on_apply_repeat))
        p.add(ui.Label(_('Tip: a few unit cells of thickness along the beam '
                         'give clearer diffraction spots.'), color='gray'))

    def _build_image_tab(self, p):
        p.add(ui.Label(_('TEM / HRTEM image simulation'), color='#0055aa'))
        p.add(_('Full multislice image using the current orientation and the '
                'Microscope Setup parameters.'))
        self.out_path = ui.Entry('', width=32)
        p.add([_('Output image (PNG), optional:'), self.out_path,
               ui.Button(_('Choose Output File'), self.browse_output)])
        self.save_meta = ui.CheckButton(
            _('Also save metadata JSON sidecar'), value=True)
        p.add(self.save_meta)
        p.add(ui.Button(_('Run TEM / HRTEM Image'), self.run))

        frame = p.frame
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self._image_fig = Figure(figsize=(3.4, 3.4), dpi=90)
            self._image_ax = self._image_fig.add_subplot(111)
            self._image_ax.set_xticks([])
            self._image_ax.set_yticks([])
            self._image_ax.text(0.5, 0.5, _('(no image yet)'),
                                ha='center', va='center', fontsize=9)
            self._image_canvas = FigureCanvasTkAgg(self._image_fig,
                                                   master=frame)
            w = self._image_canvas.get_tk_widget()
            w.configure(width=320, height=320)
            w.pack(anchor='w', padx=4, pady=4)
            self._image_canvas.draw()
        except Exception:
            self._image_canvas = None
            p.add(ui.Label(_('matplotlib unavailable — image display '
                             'disabled.'), color='gray'))

    def _build_diffraction_tab(self, p):
        import tkinter as tk
        p.add(ui.Label(_('Diffraction pattern (SAED-style)'), color='#0055aa'))
        p.add(_('Plane-wave diffraction from the oriented structure; the beam '
                'travels along the current view direction.'))
        self.diff_max_angle = ui.SpinBox(0.0, 0.0, 500.0, 5.0, rounding=1,
                                        width=8)
        p.add([_('Maximum collection angle (mrad, 0 = automatic):'),
               self.diff_max_angle])
        self.diff_block_direct = ui.CheckButton(
            _('Block the direct (central) beam'), value=False)
        p.add(self.diff_block_direct)
        self.diff_log = ui.CheckButton(
            _('Logarithmic intensity scale (recommended)'), value=True)
        p.add(self.diff_log)
        p.add(_('Voltage, sampling and grid come from Microscope Setup.'))
        self.diff_out_path = ui.Entry('', width=32)
        p.add([_('Output image (PNG), optional:'), self.diff_out_path,
               ui.Button(_('Choose Output File'), self.browse_diff_output)])
        p.add(ui.Button(_('Run Diffraction Pattern'), self.run_diffraction))

        frame = p.frame
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self._diff_fig = Figure(figsize=(3.2, 3.2), dpi=90)
            self._diff_ax = self._diff_fig.add_subplot(111)
            self._diff_ax.set_xticks([])
            self._diff_ax.set_yticks([])
            self._diff_ax.text(0.5, 0.5, _('(no diffraction yet)'),
                               ha='center', va='center', fontsize=9)
            self._diff_canvas = FigureCanvasTkAgg(self._diff_fig, master=frame)
            wdg = self._diff_canvas.get_tk_widget()
            wdg.configure(width=300, height=300)
            wdg.pack(anchor='w', padx=4, pady=4)
            self._diff_canvas.draw()
        except Exception:
            self._diff_canvas = None
            p.add(ui.Label(_('matplotlib unavailable — diffraction display '
                             'disabled.'), color='gray'))

    def _build_microscope_tab(self, p):
        p.add(ui.Label(_('Instrument presets'), color='#0055aa'))
        p.add(_('Pick a preset to fill the voltage and coherence fields for a '
                'typical instrument, then adjust as needed.'))
        self.preset_box = ui.ComboBox(
            [_('— choose a preset —'),
             _('Low-voltage TEM (80 kV)'),
             _('HRTEM 200 kV (Cs-corrected)'),
             _('HRTEM 300 kV (Cs-corrected)'),
             _('Conventional 300 kV')],
            values=['none', 'lv80', 'hr200', 'hr300', 'conv300'])
        p.add([_('Preset:'), self.preset_box,
               ui.Button(_('Apply Preset'), self.on_apply_preset)])

        p.add(ui.Label(_('Beam & detector'), color='#0055aa'))
        self.voltage = ui.SpinBox(80.0, 10.0, 1000.0, 10.0, rounding=1, width=8)
        p.add([_('Accelerating voltage (kV):'), self.voltage])
        self.defocus = ui.SpinBox(-3.0, -100000.0, 100000.0, 1.0,
                                  rounding=2, width=8)
        p.add([_('Defocus (Å, negative = underfocus):'), self.defocus])
        self.sampling = ui.SpinBox(0.05, 0.005, 2.0, 0.01, rounding=3, width=8)
        p.add([_('Real-space sampling (Å/pixel):'), self.sampling])
        self.dose = ui.SpinBox(50000.0, 1.0, 1.0e9, 1000.0, rounding=0, width=10)
        p.add([_('Electron dose (e⁻/Å²):'), self.dose])

        p.add(ui.Label(_('Simulation grid'), color='#0055aa'))
        self.image_size = ui.SpinBox(512, 16, 4096, 64, width=8)
        p.add([_('Output image size (pixels):'), self.image_size])
        self.wave_res = ui.SpinBox(512, 16, 4096, 64, width=8)
        p.add([_('Wavefunction resolution (grid points):'), self.wave_res])

        p.add(ui.Label(_('Lens aberrations (CTF)'), color='#0055aa'))
        self.cs = ui.SpinBox(0.0, -1e6, 1e6, 1.0, rounding=3, width=10)
        p.add([_('Spherical aberration Cs (Å):'), self.cs])
        self.c5 = ui.SpinBox(0.0, -1e6, 1e6, 1.0, rounding=3, width=10)
        p.add([_('Fifth-order aberration C5 (Å):'), self.c5])
        self.astigmatism = ui.SpinBox(0.5, -1e6, 1e6, 0.1, rounding=3, width=10)
        p.add([_('Two-fold astigmatism (Å):'), self.astigmatism])
        self.astigmatism_angle = ui.SpinBox(0.0, -1e6, 1e6, 0.1,
                                            rounding=3, width=10)
        p.add([_('Astigmatism angle (radians):'), self.astigmatism_angle])
        self.coma = ui.SpinBox(5.0, -1e6, 1e6, 0.5, rounding=3, width=10)
        p.add([_('Coma (Å):'), self.coma])
        self.coma_angle = ui.SpinBox(0.0, -1e6, 1e6, 0.1, rounding=3, width=10)
        p.add([_('Coma angle (radians):'), self.coma_angle])

        p.add(ui.Label(_('Partial coherence'), color='#0055aa'))
        self.focal_spread = ui.SpinBox(8.0, 0.0, 1e6, 0.5, rounding=3, width=10)
        p.add([_('Focal spread / chromatic (Å):'), self.focal_spread])
        self.angular_spread = ui.SpinBox(1.2e-3, 0.0, 1.0, 1e-4,
                                        rounding=6, width=10)
        p.add([_('Angular spread / source size (radians):'),
               self.angular_spread])
        self.gaussian_spread = ui.SpinBox(0.0, 0.0, 1e6, 0.1,
                                         rounding=4, width=10)
        p.add([_('Gaussian spread (unitless):'), self.gaussian_spread])
        p.add(ui.Label(
            _('Note: Gaussian spread is not supported by abTEM 1.x; if set, it '
              'is recorded in the metadata as ignored rather than applied.'),
            color='gray'))

    def _build_preview_benchmark_tab(self, p):
        import tkinter as tk
        # Suppress slider side effects (field writes / auto-preview) while we
        # construct and seed the sliders from the current field values.
        self._syncing_sliders = True

        p.add(ui.Label(_('Quick preview'), color='#0055aa'))
        p.add(_('Move a slider to pick one parameter combination and preview a '
                'small image; the sliders also update the Microscope fields.'))

        frame = p.frame

        self.auto_preview = ui.CheckButton(
            _('Auto-update preview (~500 ms after a slider settles)'),
            value=False)
        p.add(self.auto_preview)
        p.add(ui.Button(_('Update Quick Preview'), self.update_preview))

        self.preview_image_size = ui.SpinBox(192, 16, 2048, 32, width=8)
        p.add([_('Preview image size (pixels):'), self.preview_image_size])
        self.preview_wave_res = ui.SpinBox(192, 16, 2048, 32, width=8)
        p.add([_('Preview resolution (grid points):'), self.preview_wave_res])

        # Sliders for the three sweep variables (+ dose), linked to the fields.
        self._add_preview_slider(frame, 'defocus', _('Defocus (Å):'),
                                 -30.0, 10.0, 0.5, self.defocus, '{:g} Å')
        self._add_preview_slider(frame, 'focal', _('Focal spread (Å):'),
                                 0.0, 30.0, 0.5, self.focal_spread, '{:g} Å')
        self._add_preview_slider(frame, 'angular',
                                 _('Angular spread (rad):'),
                                 0.0, 3.0e-3, 1.0e-4, self.angular_spread,
                                 '{:g} rad')
        self._add_preview_slider(frame, 'dose', _('Electron dose (e⁻/Å²):'),
                                 1000.0, 500000.0, 1000.0, self.dose, '{:g}')

        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self._preview_fig = Figure(figsize=(2.9, 2.9), dpi=90)
            self._preview_ax = self._preview_fig.add_subplot(111)
            self._preview_ax.set_xticks([])
            self._preview_ax.set_yticks([])
            self._preview_ax.text(0.5, 0.5, _('(no preview yet)'),
                                  ha='center', va='center', fontsize=9)
            self._preview_canvas = FigureCanvasTkAgg(self._preview_fig,
                                                     master=frame)
            wdg = self._preview_canvas.get_tk_widget()
            wdg.configure(width=self.PREVIEW_PX + 60,
                          height=self.PREVIEW_PX + 60)
            wdg.pack(anchor='w', padx=4, pady=4)
            self._preview_canvas.draw()
        except Exception:
            self._preview_canvas = None
            p.add(ui.Label(_('matplotlib unavailable — preview disabled.'),
                           color='gray'))

        self._syncing_sliders = False

        # ---- Parameter sweep (same tab) ----------------------------------
        p.add(ui.Label(_('Parameter sweep (batch export)'), color='#0055aa'))
        p.add(_('Sweeps defocus × focal spread × angular spread over the value '
                'lists below, saving one PNG + JSON per combination and a CSV '
                'index. Uses the current orientation, cell mode and settings.'))
        self.bench_folder = ui.Entry('', width=32)
        p.add([_('Output folder:'), self.bench_folder,
               ui.Button(_('Choose Output Folder'), self.browse_bench_folder)])
        self.bench_prefix = ui.Entry('sweep', width=16)
        p.add([_('Filename prefix:'), self.bench_prefix])
        self.bench_defocus = ui.Entry('-1, -2, -3, -5', width=32)
        self.bench_focal = ui.Entry('2.0, 4.0, 6.0, 8.0', width=32)
        self.bench_angular = ui.Entry('0.2e-3, 0.5e-3, 0.8e-3, 1.2e-3',
                                     width=32)
        for ent in (self.bench_defocus, self.bench_focal, self.bench_angular):
            try:
                ent.widget.bind('<KeyRelease>',
                                lambda e: self._update_sweep_count())
            except Exception:
                pass
        p.add([_('Defocus values (Å):'), self.bench_defocus])
        p.add([_('Focal spread values (Å):'), self.bench_focal])
        p.add([_('Angular spread values (rad):'), self.bench_angular])
        self.lbl_sweep_count = ui.Label('')
        p.add(self.lbl_sweep_count)
        p.add(ui.Button(_('Run Parameter Sweep'), self.run_benchmark))
        self._update_sweep_count()

    def _add_preview_slider(self, parent, key, label, frm, to, res, field, fmt):
        """A labelled tk.Scale linked to a normal Microscope ``field``."""
        import tkinter as tk
        row = tk.Frame(parent)
        row.pack(anchor='w', fill='x', pady=1)
        tk.Label(row, text=label, width=22, anchor='w').pack(side='left')
        scale = tk.Scale(row, from_=frm, to=to, resolution=res,
                         orient='horizontal', length=220, showvalue=False,
                         command=lambda _v, k=key: self._on_preview_slider(k))
        val = tk.Label(row, text='', width=12, anchor='w')
        # Register before .set so the command callback can find the entry.
        self._sliders[key] = (scale, val, field, fmt)
        try:
            scale.set(float(field.value))
        except Exception:
            scale.set(frm)
        val.configure(text=fmt.format(float(scale.get())))
        scale.pack(side='left', padx=4)
        val.pack(side='left')

    def _build_database_tab(self, p):
        import tkinter as tk
        p.add(ui.Label(_('2D Materials Database'), color='#0055aa'))
        p.add(_('2DMatPedia and C2DB provide real computed 2D material '
                'structures. Download the database/structure files, then '
                'import them here. This avoids fake template structures.'))
        p.add(_('2D materials usually use PBC in x/y and vacuum in z. Use '
                '"Center slab + set 2D PBC" before simulation.'))
        if db2d is None:
            p.add(ui.Label(_('Database helper module not available.'),
                           color='red'))
            return

        self.db_source = ui.ComboBox(
            [_('Local structure file (CIF/POSCAR/XYZ/…)'),
             _('2DMatPedia JSON / JSONL'),
             _('C2DB folder of structures'),
             _('Materials Project API (later)')],
            values=['local', '2dmatpedia', 'c2db', 'mp'])
        p.add([_('Database source:'), self.db_source])

        self.db_path = ui.Entry('', width=34)
        p.add([_('Path:'), self.db_path,
               ui.Button(_('Browse…'), self.on_db_browse)])
        p.add(ui.Button(_('Load database file/folder'), self.on_load_database))

        self.db_search = ui.Entry('', width=34)
        p.add([_('Search:'), self.db_search])
        try:
            self.db_search.widget.bind('<KeyRelease>',
                                       lambda e: self._refresh_results())
        except Exception:
            pass

        # Results list (raw Tk listbox + scrollbar) inside the scrollable tab.
        frame = p.frame
        lb_row = tk.Frame(frame)
        lb_row.pack(anchor='w', fill='x', pady=2)
        self.db_listbox = tk.Listbox(lb_row, height=8, width=46,
                                     exportselection=False)
        lb_sb = tk.Scrollbar(lb_row, orient='vertical',
                             command=self.db_listbox.yview)
        self.db_listbox.configure(yscrollcommand=lb_sb.set)
        self.db_listbox.pack(side='left')
        lb_sb.pack(side='left', fill='y')
        self.db_listbox.bind('<<ListboxSelect>>',
                             lambda e: self._on_result_select())

        self.db_details = ui.Label(_('Material details:  (none selected)'),
                                   justify='left')
        p.add(self.db_details)

        p.add(ui.Button(_('Load Selected Structure into ASE'),
                        self.on_load_selected))
        p.add(ui.Label(_('After loading, use the Sample Preparation tab to '
                         'center the slab and set 2D boundary conditions.'),
                       color='gray'))

        # Materials Project (future / disabled)
        p.add(ui.Label(_('Materials Project (planned — not yet enabled)'),
                       color='gray'))
        self.mp_api_key = ui.Entry('', width=28)
        p.add([_('API key:'), self.mp_api_key])
        self.mp_formula = ui.Entry('', width=16)
        p.add([_('Formula:'), self.mp_formula])
        p.add(ui.Button(_('Fetch from Materials Project (disabled)'),
                        self._on_mp_disabled))

    # --------------------------------------------------- database handlers
    def on_db_browse(self):
        try:
            from tkinter import filedialog
            src = self.db_source.value
            if src == 'c2db':
                path = filedialog.askdirectory(
                    parent=self.win.win, title=_('Choose structure folder'))
            else:
                path = filedialog.askopenfilename(
                    parent=self.win.win, title=_('Choose database / structure '
                                                 'file'))
            if path:
                self.db_path.value = path
        except Exception as err:
            ui.error(_('Could not open dialog'), str(err))

    def on_load_database(self):
        if db2d is None:
            ui.error(_('Unavailable'), _('Database helper not available.'))
            return
        src = self.db_source.value
        path = self.db_path.value.strip()
        if src == 'mp':
            ui.error(_('Not enabled'),
                     _('Materials Project import is not enabled yet. It needs '
                       '`mp-api` and an API key.'))
            return
        if not path or not os.path.exists(path):
            ui.error(_('No path'), _('Choose an existing file or folder.'))
            return
        try:
            if src == 'local':
                atoms = db2d.load_local_file(path)
                if isinstance(atoms, list):
                    atoms = atoms[-1]
                entries = [db2d.Entry(
                    id=os.path.basename(path),
                    formula=atoms.get_chemical_formula(),
                    name=os.path.basename(path), atoms=atoms,
                    source='local_file', path=path)]
            elif src == '2dmatpedia':
                entries = db2d.load_2dmatpedia(path)
            elif src == 'c2db':
                entries = db2d.load_c2db_folder(path)
            else:
                entries = []
        except Exception as err:
            ui.error(_('Load failed'), str(err))
            return
        self._db_entries = entries
        self._refresh_results()
        self.status.text = _('Loaded {} entr{} from {}.').format(
            len(entries), 'y' if len(entries) == 1 else 'ies',
            os.path.basename(path))

    def _refresh_results(self):
        if db2d is None:
            return
        term = self.db_search.value if hasattr(self, 'db_search') else ''
        self._db_filtered = db2d.filter_entries(self._db_entries, term)
        try:
            self.db_listbox.delete(0, 'end')
            for e in self._db_filtered:
                label = '  '.join(str(x) for x in (e.id, e.formula, e.name)
                                  if x)
                self.db_listbox.insert('end', label or '(unnamed)')
        except Exception:
            pass

    def _selected_entry(self):
        try:
            sel = self.db_listbox.curselection()
            if not sel:
                return None
            return self._db_filtered[sel[0]]
        except Exception:
            return None

    def _on_result_select(self):
        e = self._selected_entry()
        if e is None:
            return
        lines = [_('Material details:'),
                 'id: {}'.format(e.id), 'formula: {}'.format(e.formula)]
        if e.name:
            lines.append('name: {}'.format(e.name))
        if e.source:
            lines.append('source: {}'.format(e.source))
        for k, v in (e.metadata or {}).items():
            lines.append('{}: {}'.format(k, v))
        self.db_details.text = '\n'.join(lines)

    def on_load_selected(self):
        e = self._selected_entry()
        if e is None:
            ui.error(_('No selection'), _('Select a material in the list.'))
            return
        try:
            atoms = e.to_atoms()
        except db2d.PymatgenRequired as err:
            ui.error(_('pymatgen required'), str(err))
            return
        except Exception as err:
            ui.error(_('Could not build structure'), str(err))
            return
        self._load_structure_into_gui(atoms, e)

    def _load_structure_into_gui(self, atoms, entry=None):
        """Replace the current ASE GUI structure (verified: gui.new_atoms)."""
        try:
            self.gui.new_atoms(atoms)
            try:
                self.gui.clear_history()
            except Exception:
                pass
        except Exception as err:
            ui.error(_('Could not load into ASE GUI'), str(err))
            return
        # Record provenance.
        if entry is not None:
            self.structure_source = entry.source
            self.structure_database_id = entry.id
            self.structure_formula = entry.formula
            self.structure_name = entry.name
            self.structure_metadata = dict(entry.metadata or {})
        self.structure_pbc = self.gui.atoms.pbc.tolist()
        self.status.text = _('Loaded {} into ASE GUI ({} atoms).').format(
            entry.formula if entry else self.gui.atoms.get_chemical_formula(),
            len(self.gui.atoms))

    def _apply_pbc(self, pbc, center_z=False, label=''):
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            ui.error(_('No structure'), _('Load a structure first.'))
            return
        a = atoms.copy()
        try:
            a.set_pbc(list(pbc))
            if center_z:
                a.center(vacuum=float(self.vacuum.value), axis=2)
        except Exception as err:
            ui.error(_('Could not update cell'), str(err))
            return
        try:
            self.gui.new_atoms(a)
            try:
                self.gui.clear_history()
            except Exception:
                pass
        except Exception as err:
            ui.error(_('Could not apply'), str(err))
            return
        self.structure_pbc = self.gui.atoms.pbc.tolist()
        self.status.text = _('{} — pbc now {}.').format(
            label, self.structure_pbc)

    def on_center_slab_2d(self):
        self._apply_pbc([True, True, False], center_z=True,
                        label=_('Centered slab + 2D PBC'))

    def on_set_2d_slab(self):
        self._apply_pbc([True, True, False], center_z=False,
                        label=_('Set as 2D slab'))

    def on_set_flake(self):
        self._apply_pbc([False, False, False], center_z=False,
                        label=_('Set as finite flake'))

    def on_set_periodic(self):
        self._apply_pbc([True, True, True], center_z=False,
                        label=_('Set as fully periodic crystal'))

    def on_center_only(self):
        self._apply_pbc(self.gui.atoms.pbc.tolist() if self.gui.atoms is not None
                        else [False, False, False],
                        center_z=True, label=_('Centered structure'))

    def on_apply_repeat(self):
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            ui.error(_('No structure'), _('Load a structure first.'))
            return
        try:
            nx = int(self.rep_x.value)
            ny = int(self.rep_y.value)
            nz = int(self.rep_z.value)
        except Exception:
            ui.error(_('Bad repeat'), _('Enter integer repeat counts.'))
            return
        if (nx, ny, nz) == (1, 1, 1):
            self.status.text = _('Repeat (1,1,1) — nothing to do.')
            return
        try:
            self._load_structure_into_gui(atoms.copy() * (nx, ny, nz))
            self.status.text = _('Built {}×{}×{} supercell ({} atoms).').format(
                nx, ny, nz, len(self.gui.atoms))
        except Exception as err:
            ui.error(_('Repeat failed'), str(err))

    def on_apply_preset(self):
        key = getattr(self, 'preset_box', None)
        key = key.value if key is not None else 'none'
        pre = _PRESETS.get(key)
        if not pre:
            self.status.text = _('Choose a preset first.')
            return
        self.voltage.value = pre['voltage']
        self.cs.value = pre['cs']
        self.focal_spread.value = pre['focal_spread']
        self.angular_spread.value = pre['angular_spread']
        self.status.text = _('Applied preset: {} kV.').format(pre['voltage'])

    def _on_mp_disabled(self):
        ui.error(_('Not enabled'),
                 _('Materials Project import is a planned feature. It requires '
                   '`mp-api` and an API key.'))

    # ----------------------------------------------- Results & Export tab
    def _build_results_tab(self, p):
        import tkinter as tk
        p.add(ui.Label(_('Results & export'), color='#0055aa'))
        p.add(_('Files written this session, and tools to reproduce or share '
                'the current setup.'))
        frame = p.frame
        lb_row = tk.Frame(frame)
        lb_row.pack(anchor='w', fill='x', pady=2)
        self.results_listbox = tk.Listbox(lb_row, height=8, width=52,
                                          exportselection=False)
        sb = tk.Scrollbar(lb_row, orient='vertical',
                          command=self.results_listbox.yview)
        self.results_listbox.configure(yscrollcommand=sb.set)
        self.results_listbox.pack(side='left')
        sb.pack(side='left', fill='y')

        p.add(ui.Button(_('Open Output Folder'), self.on_open_output_folder))
        p.add(ui.Button(_('Copy Last-Run Metadata to Clipboard'),
                        self.on_copy_metadata))
        p.add(ui.Label(_('Reproducibility'), color='#0055aa'))
        p.add(ui.Button(_('Export Oriented Structure (.extxyz)'),
                        self.on_export_structure))
        p.add(ui.Button(_('Export Reproducible Python Script (.py)'),
                        self.on_export_script))

    def _record_output(self, path, kind):
        if not path:
            return
        self._session_outputs.append((path, kind))
        try:
            self.results_listbox.insert('end', '[{}]  {}'.format(
                kind, os.path.basename(path)))
        except Exception:
            pass

    def on_open_output_folder(self):
        import subprocess
        import sys as _sys
        folder = None
        if self._session_outputs:
            folder = os.path.dirname(os.path.abspath(self._session_outputs[-1][0]))
        if not folder or not os.path.isdir(folder):
            ui.error(_('No output yet'),
                     _('Run a simulation that saves a file first.'))
            return
        try:
            if _sys.platform.startswith('darwin'):
                subprocess.Popen(['open', folder])
            elif os.name == 'nt':
                os.startfile(folder)  # noqa
            else:
                subprocess.Popen(['xdg-open', folder])
            self.status.text = _('Opened {}').format(folder)
        except Exception as err:
            ui.error(_('Could not open folder'), str(err))

    def on_copy_metadata(self):
        if not self._last_meta:
            ui.error(_('No run yet'),
                     _('Run a TEM image or diffraction first.'))
            return
        import json
        text = json.dumps(self._last_meta, indent=2)
        try:
            self.win.win.clipboard_clear()
            self.win.win.clipboard_append(text)
            self.status.text = _('Copied last-run metadata to clipboard.')
        except Exception as err:
            ui.error(_('Clipboard failed'), str(err))

    def on_export_structure(self):
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            ui.error(_('No structure'), _('Load a structure first.'))
            return
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                parent=self.win.win, title=_('Export oriented structure'),
                defaultextension='.extxyz', initialfile='structure.extxyz',
                filetypes=[('Extended XYZ', '*.extxyz'), ('All files', '*')])
            if not path:
                return
            oriented = apply_view_rotation(
                atoms, self._current_view_axes(),
                rotate_cell=self._rotate_cell_choice())
            from ase.io import write
            write(path, oriented)
            self._record_output(path, 'structure')
            self.status.text = _('Exported oriented structure: {}').format(
                os.path.basename(path))
        except Exception as err:
            ui.error(_('Export failed'), str(err))

    def on_export_script(self):
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                parent=self.win.win, title=_('Export reproducible script'),
                defaultextension='.py', initialfile='reproduce_tem.py',
                filetypes=[('Python', '*.py'), ('All files', '*')])
            if not path:
                return
            with open(path, 'w') as fh:
                fh.write(self._build_repro_script())
            self._record_output(path, 'script')
            self.status.text = _('Exported script: {}').format(
                os.path.basename(path))
        except Exception as err:
            ui.error(_('Export failed'), str(err))

    def _build_repro_script(self):
        """Delegate to :func:`abtem_ase_workbench.export.build_repro_script`
        with the current GUI field values."""
        g = lambda w, d=0.0: (float(w.value) if w is not None else d)
        return _build_repro_script_fn(dict(
            rot=(g(self.rx), g(self.ry), g(self.rz)),
            view_axes=self._current_view_axes().tolist(),
            rc=self._rotate_cell_choice(),
            volt=g(self.voltage) * 1e3,
            defocus=g(self.defocus),
            sampling=g(self.sampling),
            dose=g(self.dose),
            isize=int(g(self.image_size, 512)),
            wres=int(g(self.wave_res, 512)),
            cs=g(self.cs), c5=g(self.c5),
            ast=g(self.astigmatism), asta=g(self.astigmatism_angle),
            coma=g(self.coma), comaa=g(self.coma_angle),
            fs=g(self.focal_spread), angs=g(self.angular_spread)))

    # ------------------------------------------------------ Help / About
    def _build_help_tab(self, p):
        try:
            from ase.gui.abtem_tem_backend import ABTEM_VERSION, ASE_VERSION
        except Exception:
            try:
                from abtem_tem_backend import ABTEM_VERSION, ASE_VERSION
            except Exception:
                ABTEM_VERSION = ASE_VERSION = None
        p.add(ui.Label(_('ASE Electron Microscopy Workbench'), color='#003366'))
        p.add(_('ASE structure → abTEM simulation pipeline.'))
        p.add(_('The exact current ASE view matrix is used for every simulation; '
                'X/Y/Z are only controls/readout for that same view.'))
        p.add(ui.Label(_('Workflow'), color='#0055aa'))
        p.add(_('1. Load/build a structure in ASE (or the 2D Materials tab).'))
        p.add(_('2. Sample Preparation: set boundary conditions and vacuum.'))
        p.add(_('3. Structure & Orientation: choose a zone axis or angles.'))
        p.add(_('4. Microscope Setup: pick a preset and parameters.'))
        p.add(_('5. Run a TEM/HRTEM image or a diffraction pattern; or sweep.'))
        p.add(_('6. Results & Export: reproduce and share.'))
        p.add(ui.Label(_('Terminology'), color='#0055aa'))
        p.add(_('Zone axis [u v w]: crystal direction the beam travels along.'))
        p.add(_('Plane (h k l): a lattice plane; its normal sets the view.'))
        p.add(_('Defocus: lens focus offset (negative = underfocus).'))
        p.add(_('Cs: spherical aberration; sampling: Å per pixel.'))
        p.add(ui.Label(_('Citation'), color='#0055aa'))
        p.add(_('abTEM: Madsen & Susi, Open Research Europe (2021).'))
        p.add(_('ASE: Larsen et al., J. Phys. Condens. Matter (2017).'))
        p.add(ui.Label(_('Versions'), color='#0055aa'))
        p.add(ui.Label(_('abTEM {}   ASE {}').format(
            ABTEM_VERSION or _('not installed'),
            ASE_VERSION or '?')))

    # ------------------------------------------- live structure summary
    def _update_structure_summary(self):
        if self.lbl_structure is None:
            return
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            self.lbl_structure.text = _('(no structure loaded)')
            return
        try:
            cell = atoms.cell.lengths()
            ang = atoms.cell.angles()
            txt = _(
                'Atoms: {n}   Formula: {f}\n'
                'PBC: {pbc}\n'
                'Cell (Å): a={a:.3f} b={b:.3f} c={c:.3f}\n'
                'Angles (°): α={al:.1f} β={be:.1f} γ={ga:.1f}'
            ).format(n=len(atoms), f=atoms.get_chemical_formula(),
                     pbc=atoms.pbc.tolist(), a=cell[0], b=cell[1], c=cell[2],
                     al=ang[0], be=ang[1], ga=ang[2])
        except Exception:
            txt = _('Atoms: {n}   Formula: {f}').format(
                n=len(atoms), f=atoms.get_chemical_formula())
        self.lbl_structure.text = txt

    def _update_sweep_count(self):
        if getattr(self, 'lbl_sweep_count', None) is None:
            return
        try:
            nd = len(self._parse_float_list(self.bench_defocus.value))
            nf = len(self._parse_float_list(self.bench_focal.value))
            na = len(self._parse_float_list(self.bench_angular.value))
            total = nd * nf * na
            self.lbl_sweep_count.text = _(
                'Estimated simulations: {} × {} × {} = {} images').format(
                    nd, nf, na, total)
        except Exception:
            self.lbl_sweep_count.text = _('Estimated simulations: —')

    # --------------------------------------------- pre-run validation
    def _validate_before(self, kind):
        """Collect readable error/warning strings for the current request.

        Thin wrapper over :func:`abtem_ase_workbench.validators.validate_run`:
        reads the current GUI field values, calls the pure validator, and
        returns its ``(hard, soft)`` lists unchanged.
        """
        sweep_total = 0
        if kind == "sweep":
            try:
                nd = len(self._parse_float_list(self.bench_defocus.value))
                nf = len(self._parse_float_list(self.bench_focal.value))
                na = len(self._parse_float_list(self.bench_angular.value))
                sweep_total = nd * nf * na
            except Exception:
                sweep_total = 0
        try:
            isz = int(self.image_size.value)
        except Exception:
            isz = 0
        try:
            wres = int(self.wave_res.value)
        except Exception:
            wres = 0
        try:
            samp = float(self.sampling.value)
        except Exception:
            samp = 0.0
        return _validate_run(
            self.gui.atoms, kind=kind, have_abtem=HAVE_ABTEM,
            rotate_cell_effective=self._rotate_cell_choice(),
            image_size=isz, wave_resolution=wres, sampling=samp,
            sweep_total=sweep_total,
        )

    def _passes_validation(self, kind):
        hard, soft = self._validate_before(kind)
        if hard:
            ui.error(_('Cannot run'), '\n'.join('• ' + h for h in hard))
            return False
        if soft:
            msg = (_('Please check:') + '\n'
                   + '\n'.join('• ' + s for s in soft) + '\n\n'
                   + _('Run anyway?'))
            try:
                return bool(ui.ask_question(_('Warning'), msg))
            except Exception:
                return True
        return True


    # ------------------------------------------------------- live readout
    def _update_view_readout(self):
        """Poll gui.axes -> refresh direction/matrix labels and X/Y/Z fields.

        Read-only with respect to the atoms; never runs abTEM.
        """
        if not getattr(self.win, 'exists', False):
            return  # window closed -> stop the loop
        try:
            axes = np.asarray(self.gui.axes, dtype=float)
            x, y, z = irotate(axes)
            self._last_view_angles = (x, y, z)
            beam = axes[:, 2]
            n = float(np.linalg.norm(beam))
            if n > 0:
                beam = beam / n
            self.lbl_dir.text = _(
                'View direction (beam):  [{:6.3f}, {:6.3f}, {:6.3f}]'
            ).format(*beam)
            self.lbl_matrix.text = self._format_matrix(axes)

            # Provenance: if the view changed outside our own setters, it was a
            # mouse drag -> mark mouse_view and drop any Miller selection.
            if self._last_axes is None:
                self._last_axes = np.array(axes)
            elif not np.allclose(axes, self._last_axes, atol=1e-6):
                self.orientation_source = 'mouse_view'
                self.zone_axis_uvw = None
                self.plane_hkl = None
                self._last_axes = np.array(axes)

            # Live approximate zone-axis readout (Miller).
            self._update_zone_readout(beam)

            # A. Live view -> fields (the reason the Copy button is gone).
            self._sync_fields_from_view(x, y, z)
            self._update_structure_summary()
        except Exception:
            pass  # never let a transient error kill the loop
        try:
            self.win.win.after(self.VIEW_POLL_MS, self._update_view_readout)
        except Exception:
            pass

    def _current_focus_widget(self):
        try:
            return self.win.win.focus_get()
        except Exception:
            return None

    def _sync_fields_from_view(self, x, y, z):
        """Write the view angles into the X/Y/Z fields, guarded & focus-aware.

        The guard flag stops any field callback fired during this write from
        looping back to the view. We also skip a field the user is currently
        editing (has keyboard focus) so we never clobber mid-typing, and only
        rewrite a field whose value actually changed (avoids flicker).
        """
        focused = self._current_focus_widget()
        fields = ((self.rx, x), (self.ry, y), (self.rz, z))
        if any(f.widget is focused for f, _ in fields):
            return
        self._syncing_from_view = True
        try:
            for f, val in fields:
                val = round(float(val), 3)
                try:
                    cur = float(f.value)
                except Exception:
                    cur = None
                if cur is None or abs(cur - val) > 1e-4:
                    f.value = val
        finally:
            self._syncing_from_view = False

    @staticmethod
    def _format_matrix(a):
        lines = [_('View matrix (rows = crystal x,y,z; col 2 = beam):')]
        for r in a:
            lines.append('  [{: .3f} {: .3f} {: .3f}]'.format(r[0], r[1], r[2]))
        return '\n'.join(lines)

    def _extra_metadata(self):
        """Provenance dict merged into the simulation JSON (no physics):
        orientation source + 2D-materials database source."""
        try:
            pbc = (self.gui.atoms.pbc.tolist()
                   if self.gui.atoms is not None else None)
        except Exception:
            pbc = None
        try:
            axes = self._current_view_axes().tolist()
        except Exception:
            axes = None
        try:
            angles = [float(self.rx.value), float(self.ry.value),
                      float(self.rz.value)]
        except Exception:
            angles = None
        return {
            'orientation_source': self.orientation_source,
            'ase_view_axes': axes,
            'ase_view_angles_display_xyz': angles,
            'zone_axis_uvw': self.zone_axis_uvw,
            'plane_hkl': self.plane_hkl,
            'nearest_zone_axis': self.nearest_zone_axis,
            'nearest_zone_axis_error_deg': self.nearest_zone_axis_error_deg,
            'structure_source': self.structure_source,
            'structure_database_id': self.structure_database_id,
            'structure_formula': self.structure_formula,
            'structure_name': self.structure_name,
            'structure_pbc': pbc,
            'structure_metadata': self.structure_metadata or {},
        }

    def _current_view_axes(self):
        """Return a defensive copy of ASE GUI's exact current view matrix.

        This matrix is the single source of truth for every simulation/export.
        The X/Y/Z controls are only an editable representation of this matrix.
        """
        axes = np.asarray(self.gui.axes, dtype=float)
        if axes.shape != (3, 3) or not np.all(np.isfinite(axes)):
            raise ValueError(_('ASE view matrix is invalid.'))
        return np.array(axes, dtype=float, copy=True)

    # ----------------------------------------------------------------- slots
    def _rotate_cell_choice(self):
        """Map the selected mode to a rotate_cell value for the backend.

        'auto' -> None (backend resolves from pbc), 'finite' -> False,
        'periodic' -> True. Used by BOTH preview and Run so they agree.
        """
        return {'auto': None, 'finite': False, 'periodic': True}[
            self.rot_mode.value]

    def _on_field_changed(self, *args):
        """B. User edited an X/Y/Z field -> rotate the CURRENT ASE GUI view.

        Sets gui.axes with ASE's own convention (ase.utils.rotate, matrix =
        Rx.Ry.Rz -- identical to ASE's Rotate tool) and redraws the same
        canvas. No preview window is opened, and the atoms are not touched.
        """
        if self._syncing_from_view:
            return  # this change was our own poll-write; ignore it
        try:
            x = float(self.rx.value)
            y = float(self.ry.value)
            z = float(self.rz.value)
        except Exception:
            return
        self._syncing_from_fields = True
        try:
            self.gui.axes = rotate('{}x,{}y,{}z'.format(x, y, z))
            self.gui.draw()
            # Provenance: this view change came from manual angle entry.
            self.orientation_source = 'manual_angles'
            self.zone_axis_uvw = None
            self.plane_hkl = None
            self._last_axes = np.array(self.gui.axes, dtype=float)
            self.status.text = _('ASE view updated from X/Y/Z fields '
                                 '({:.2f}, {:.2f}, {:.2f})°').format(x, y, z)
        except Exception as err:
            self.status.text = _('Could not update view: {}').format(err)
        finally:
            self._syncing_from_fields = False

    # --------------------------------------------------- Miller / zone axis
    def _valid_cell(self):
        """Return the current cell array if usable for Miller math, else None
        (after showing a clear error)."""
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            ui.error(_('No structure'),
                     _('Load or build a structure in ASE GUI first.'))
            return None
        cell = np.asarray(atoms.cell.array, dtype=float)
        if not np.all(np.isfinite(cell)) or abs(np.linalg.det(cell)) < 1e-9:
            ui.error(_('Invalid cell'),
                     _('Miller indices require a valid crystal cell '
                       '(non-zero volume).'))
            return None
        return cell

    def _set_view_direction(self, direction_cart):
        """Set the ASE view so the beam (gui.axes[:, 2]) is ``direction_cart``.

        Builds an orthonormal, right-handed axes matrix (verified det=+1) whose
        third column is the normalized direction, preserving a sensible
        screen-up. Sets gui.axes + gui.draw(); the existing poll then syncs the
        X/Y/Z fields. Does not mutate atoms and does not run abTEM.
        """
        axes = _ori_set_view_axes(direction_cart)
        self.gui.axes = axes
        self.gui.draw()
        self._last_axes = np.array(self.gui.axes, dtype=float)
        # Immediate field sync for responsiveness (poll also does this).
        try:
            xa, ya, za = irotate(axes)
            self._sync_fields_from_view(xa, ya, za)
        except Exception:
            pass

    def _on_set_zone_axis(self, uvw=None):
        """Set the view so the beam looks along crystal direction [u v w]."""
        if uvw is None:
            uvw = (self.uvw_u.value, self.uvw_v.value, self.uvw_w.value)
        try:
            u, v, w = (float(t) for t in uvw)
        except Exception:
            ui.error(_('Bad zone axis'), _('Enter numeric u, v, w.'))
            return
        cell = self._valid_cell()
        if cell is None:
            return
        if u == 0 and v == 0 and w == 0:
            ui.error(_('Bad zone axis'), _('[0 0 0] is not a direction.'))
            return
        direction = np.array([u, v, w], dtype=float) @ cell   # [uvw] @ cell
        try:
            self._set_view_direction(direction)
        except Exception as err:
            ui.error(_('Could not set view'), str(err))
            return
        self.orientation_source = 'zone_axis'
        self.zone_axis_uvw = [u, v, w]
        self.plane_hkl = None
        self.status.text = _('View set to zone axis '
                             '[{:g} {:g} {:g}].').format(u, v, w)

    def _on_set_plane_normal(self, hkl=None):
        """Set the view along the normal of plane (h k l) via reciprocal cell."""
        if hkl is None:
            hkl = (self.hkl_h.value, self.hkl_k.value, self.hkl_l.value)
        try:
            h, k, l = (float(t) for t in hkl)
        except Exception:
            ui.error(_('Bad plane'), _('Enter numeric h, k, l.'))
            return
        cell = self._valid_cell()
        if cell is None:
            return
        if h == 0 and k == 0 and l == 0:
            ui.error(_('Bad plane'), _('(0 0 0) is not a plane.'))
            return
        # Plane normal in Cartesian = h b1 + k b2 + l b3 (reciprocal vectors).
        recip = np.asarray(self.gui.atoms.cell.reciprocal().array, dtype=float)
        normal = np.array([h, k, l], dtype=float) @ recip
        try:
            self._set_view_direction(normal)
        except Exception as err:
            ui.error(_('Could not set view'), str(err))
            return
        self.orientation_source = 'plane_normal'
        self.plane_hkl = [h, k, l]
        self.zone_axis_uvw = None
        self.status.text = _('View set normal to plane '
                             '({:g} {:g} {:g}).').format(h, k, l)

    def _zone_triples(self, max_index):
        """Cached wrapper around ``orientation.reduced_triples(max_index)``."""
        if self._triples_cache is not None and self._triples_cache_n == max_index:
            return self._triples_cache
        self._triples_cache = _ori_reduced_triples(max_index)
        self._triples_cache_n = max_index
        return self._triples_cache

    def _nearest_zone_axis(self, beam_cart, cell, max_index):
        """Nearest low-index [uvw] to a Cartesian beam direction + angle (deg)."""
        beam = np.asarray(beam_cart, float)
        bn = np.linalg.norm(beam)
        if bn < 1e-12:
            return None, None
        beam = beam / bn
        best, best_ang = None, 1e9
        for tri in self._zone_triples(max_index):
            d = np.array(tri, float) @ cell
            nd = np.linalg.norm(d)
            if nd < 1e-12:
                continue
            cos = abs(float(np.dot(d / nd, beam)))     # allow sign flip
            cos = max(-1.0, min(1.0, cos))
            ang = float(np.degrees(np.arccos(cos)))
            if ang < best_ang:
                best_ang, best = ang, tri
        return best, best_ang

    def _update_zone_readout(self, beam):
        """Refresh the 'Approx zone axis' label from the current beam dir."""
        try:
            maxidx = int(self.zone_max_index.value)
        except Exception:
            maxidx = 4
        try:
            tol = float(self.zone_tol.value)
        except Exception:
            tol = 5.0
        # Recompute only when the beam moved or the max index changed.
        if (self._last_beam is not None
                and np.allclose(beam, self._last_beam, atol=1e-4)
                and self._triples_cache_n == maxidx):
            return
        self._last_beam = np.array(beam)
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            self.lbl_zone.text = _('Approx zone axis:  (load a structure)')
            return
        cell = np.asarray(atoms.cell.array, dtype=float)
        if not np.all(np.isfinite(cell)) or abs(np.linalg.det(cell)) < 1e-9:
            self.lbl_zone.text = _('Approx zone axis:  (needs a valid crystal '
                                  'cell)')
            self.nearest_zone_axis = None
            self.nearest_zone_axis_error_deg = None
            return
        best, err = self._nearest_zone_axis(beam, cell, maxidx)
        if best is None:
            return
        self.nearest_zone_axis = list(best)
        self.nearest_zone_axis_error_deg = round(float(err), 3)
        u, v, w = best
        if err <= tol:
            self.lbl_zone.text = _('Approx zone axis: [{} {} {}]   error: '
                                  '{:.1f}°').format(u, v, w, err)
        else:
            self.lbl_zone.text = _('Approx zone axis: near [{} {} {}]   error: '
                                  '{:.1f}° (not close to low-index zone)'
                                  ).format(u, v, w, err)

    def browse_output(self):
        """Native save dialog (modal; does not disturb the Tk mainloop)."""
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                parent=self.win.win,
                title=_('Save TEM image as'),
                defaultextension='.png',
                initialfile='simulated_image.png',
                filetypes=[('PNG image', '*.png'), ('All files', '*')])
            if path:
                self.out_path.value = path
        except Exception as err:
            ui.error(_('Could not open file dialog'), str(err))

    def run(self):
        """Run TEM from the exact current ASE view on a copy of gui.atoms."""
        if not self._passes_validation('image'):
            return
        atoms = self.gui.atoms

        atoms_copy = atoms.copy()   # safe copy of the currently edited structure
        out = self.out_path.value.strip() or None
        want_meta = bool(self.save_meta.value)

        self.status.text = _('Running… (window may be unresponsive)')
        try:
            self.win.win.update_idletasks()
        except Exception:
            pass

        try:
            img, meta = simulate_tem_from_atoms(
                atoms_copy,
                output_file=out if want_meta else None,
                view_axes=self._current_view_axes(),
                rotate_cell=self._rotate_cell_choice(),
                voltage=float(self.voltage.value) * 1e3,   # kV -> V
                defocus=float(self.defocus.value),
                sampling=float(self.sampling.value),
                dose=float(self.dose.value),
                image_size=int(self.image_size.value),
                wave_resolution=int(self.wave_res.value),
                Cs=float(self.cs.value),
                C5=float(self.c5.value),
                astigmatism=float(self.astigmatism.value),
                astigmatism_angle=float(self.astigmatism_angle.value),
                coma=float(self.coma.value),
                coma_angle=float(self.coma_angle.value),
                focal_spread=float(self.focal_spread.value),
                angular_spread=float(self.angular_spread.value),
                gaussian_spread=float(self.gaussian_spread.value),
                extra_metadata=self._extra_metadata(),
            )
            if out and not want_meta:
                try:
                    from ase.gui.abtem_tem_backend import save_gray_png
                except Exception:
                    from abtem_tem_backend import save_gray_png
                save_gray_png(img, out)
                meta['output_image'] = out
        except Exception as err:
            self.status.text = _('Failed.')
            ui.error(_('TEM simulation failed'), str(err))
            return

        self._show_image_in_tab(img)
        self._last_meta = meta
        if out:
            self._record_output(out, 'image')

        bits = [_('Done.'), _('{}×{} px').format(img.shape[0], img.shape[1])]
        if meta.get('orientation_transform') == 'ase_view_matrix':
            bits.append(_('orientation=exact ASE view'))
        if meta.get('rotation_applied') and meta.get('xyz_rotation'):
            bits.append(_('rot (X,Y,Z)=({:.2f},{:.2f},{:.2f})°').format(
                *meta['xyz_rotation']))
        bits.append(_('mode={} (rotate_cell={})').format(
            meta.get('rotation_mode'), meta.get('rotate_cell')))
        if out:
            bits.append(_('saved {}').format(meta.get('output_image')))
            if want_meta and meta.get('metadata_file'):
                bits.append(meta['metadata_file'])
        ignored = meta.get('ctf_unsupported_ignored') or {}
        if ignored:
            bits.append(_('ignored: {}').format(', '.join(ignored)))
        self.status.text = '  '.join(bits)

    def _show_image_in_tab(self, img):
        """Draw a TEM image into the TEM/HRTEM tab's embedded canvas."""
        if self._image_canvas is None:
            self._show_image(img, {'output_image': None})
            return
        try:
            if self._notebook is not None and self._image_tab is not None:
                self._notebook.select(self._image_tab)
        except Exception:
            pass
        self._image_ax.clear()
        self._image_ax.imshow(img, cmap='gray', vmin=0.0, vmax=1.0,
                              origin='upper')
        self._image_ax.set_xticks([])
        self._image_ax.set_yticks([])
        self._image_ax.set_title(_('TEM / HRTEM image'), fontsize=9)
        self._image_canvas.draw()

    # --------------------------------------------------------- diffraction
    def browse_diff_output(self):
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                parent=self.win.win,
                title=_('Save diffraction image as'),
                defaultextension='.png',
                initialfile='diffraction.png',
                filetypes=[('PNG image', '*.png'), ('All files', '*')])
            if path:
                self.diff_out_path.value = path
        except Exception as err:
            ui.error(_('Could not open file dialog'), str(err))

    def run_diffraction(self):
        """Compute a diffraction pattern from the current oriented structure."""
        if not self._passes_validation('diffraction'):
            return
        atoms = self.gui.atoms
        try:
            if self._notebook is not None and self._diff_tab is not None:
                self._notebook.select(self._diff_tab)
        except Exception:
            pass
        out = self.diff_out_path.value.strip() or None
        try:
            ma = float(self.diff_max_angle.value)
        except Exception:
            ma = 0.0
        max_angle = None if ma <= 0 else ma
        self.status.text = _('Running diffraction…')
        self._pump_events()
        try:
            img, meta = simulate_diffraction_from_atoms(
                atoms.copy(), output_file=out,
                view_axes=self._current_view_axes(),
                rotate_cell=self._rotate_cell_choice(),
                voltage=float(self.voltage.value) * 1e3,
                sampling=float(self.sampling.value),
                wave_resolution=int(self.wave_res.value),
                image_size=int(self.image_size.value),
                max_angle=max_angle,
                block_direct=bool(self.diff_block_direct.value),
                log_scale=bool(self.diff_log.value),
                extra_metadata=self._extra_metadata())
        except Exception as err:
            self.status.text = _('Diffraction failed.')
            ui.error(_('Diffraction failed'), str(err))
            return
        self._show_diffraction(img)
        self._last_meta = meta
        if out:
            self._record_output(out, 'diffraction')
        bits = [_('Diffraction done.'),
                _('{}×{} px').format(img.shape[0], img.shape[1])]
        if out:
            bits.append(_('saved {}').format(meta.get('output_image')))
        self.status.text = '  '.join(bits)

    def _show_diffraction(self, img):
        if self._diff_canvas is None:
            self._show_image(img, {'output_image': None})
            return
        self._diff_ax.clear()
        self._diff_ax.imshow(img, cmap='inferno', origin='upper')
        self._diff_ax.set_xticks([])
        self._diff_ax.set_yticks([])
        self._diff_ax.set_title(_('diffraction'), fontsize=9)
        self._diff_canvas.draw()

    # --------------------------------------------------------- preview
    def _on_preview_slider(self, key):
        """A slider moved: update its value label + linked normal field now,
        then (if Auto preview is on) debounce a preview render."""
        entry = self._sliders.get(key)
        if entry is None:
            return
        scale, val, field, fmt = entry
        try:
            v = float(scale.get())
        except Exception:
            return
        val.configure(text=fmt.format(v))       # immediate value label
        if self._syncing_sliders:
            return                               # programmatic set: no side effects
        try:
            field.value = v                      # immediate linked normal field
        except Exception:
            pass
        try:
            if bool(self.auto_preview.value):
                self._schedule_preview()
        except Exception:
            pass

    def _schedule_preview(self):
        """Cancel any pending preview and schedule one ~500 ms later."""
        try:
            if self._preview_after_id is not None:
                self.win.win.after_cancel(self._preview_after_id)
        except Exception:
            pass
        try:
            self._preview_after_id = self.win.win.after(500, self.update_preview)
        except Exception:
            self._preview_after_id = None

    def _sync_sliders_from_fields(self):
        """Seed each slider from its linked Microscope field (guarded)."""
        if not getattr(self, '_sliders', None):
            return
        self._syncing_sliders = True
        try:
            for _key, (scale, val, field, fmt) in self._sliders.items():
                try:
                    v = float(field.value)
                    scale.set(v)
                    val.configure(text=fmt.format(v))
                except Exception:
                    pass
        finally:
            self._syncing_sliders = False

    def _on_tab_changed(self, *args):
        try:
            if self._notebook.select() == str(self._preview_tab):
                self._sync_sliders_from_fields()
        except Exception:
            pass

    def update_preview(self):
        """Render one preview into the persistent Preview-tab canvas.

        Uses the CURRENT values of the normal Microscope fields (which the
        sliders keep updated) plus the preview grid sizes. Never opens a new
        window; the same embedded canvas is redrawn.
        """
        if self._preview_canvas is None:
            self.status.text = _('Preview needs matplotlib.')
            return
        try:
            if self._notebook is not None and self._preview_tab is not None:
                self._notebook.select(self._preview_tab)
        except Exception:
            pass
        if not HAVE_ABTEM or simulate_tem_from_atoms is None:
            self.status.text = _('Preview needs abTEM installed.')
            return
        atoms = self.gui.atoms
        if atoms is None or len(atoms) == 0:
            self.status.text = _('Load a structure to preview.')
            return

        self.status.text = _('Rendering preview…')
        self._pump_events()
        try:
            img, _meta = simulate_tem_from_atoms(
                atoms.copy(),
                output_file=None,
                view_axes=self._current_view_axes(),
                rotate_cell=self._rotate_cell_choice(),
                voltage=float(self.voltage.value) * 1e3,
                defocus=float(self.defocus.value),
                sampling=float(self.sampling.value),
                dose=float(self.dose.value),
                image_size=int(self.preview_image_size.value),
                wave_resolution=int(self.preview_wave_res.value),
                Cs=float(self.cs.value),
                C5=float(self.c5.value),
                astigmatism=float(self.astigmatism.value),
                astigmatism_angle=float(self.astigmatism_angle.value),
                coma=float(self.coma.value),
                coma_angle=float(self.coma_angle.value),
                focal_spread=float(self.focal_spread.value),
                angular_spread=float(self.angular_spread.value),
                gaussian_spread=float(self.gaussian_spread.value),
            )
            self._preview_ax.clear()
            self._preview_ax.imshow(img, cmap='gray', vmin=0.0, vmax=1.0,
                                    origin='upper')
            self._preview_ax.set_xticks([])
            self._preview_ax.set_yticks([])
            self._preview_ax.set_title(
                _('def {:g} | fs {:g} | ang {:g} | dose {:g}').format(
                    float(self.defocus.value), float(self.focal_spread.value),
                    float(self.angular_spread.value), float(self.dose.value)),
                fontsize=8)
            self._preview_canvas.draw()
            self.status.text = _('Preview updated.')
        except Exception as err:
            self.status.text = _('Preview failed: {}').format(err)

    # --------------------------------------------------------- benchmark
    def browse_bench_folder(self):
        """Native folder chooser for the benchmark output directory."""
        try:
            from tkinter import filedialog
            path = filedialog.askdirectory(
                parent=self.win.win,
                title=_('Choose benchmark output folder'))
            if path:
                self.bench_folder.value = path
        except Exception as err:
            ui.error(_('Could not open folder dialog'), str(err))

    @staticmethod
    def _parse_float_list(text):
        """Parse a comma-separated list of floats (supports 0.2e-3 etc.)."""
        vals = []
        for tok in str(text).replace(';', ',').split(','):
            tok = tok.strip()
            if tok:
                vals.append(float(tok))
        return vals

    @staticmethod
    def _fmt_num(v):
        """Compact, filename-safe number formatting (e.g. -1, 2, 0.0002)."""
        return '%g' % float(v)

    def _bench_row(self, fname, meta):
        """One index row from a returned metadata dict."""
        ctf = meta.get('ctf_parameters', {}) or {}
        xyz = (meta.get('ase_view_angles_display_xyz')
               or meta.get('xyz_rotation') or [None, None, None])
        return {
            'filename': fname,
            'defocus': meta.get('defocus'),
            'focal_spread': ctf.get('focal_spread'),
            'angular_spread': ctf.get('angular_spread'),
            'voltage': meta.get('accelerating_voltage'),
            'sampling': meta.get('sampling'),
            'dose': meta.get('electron_dose'),
            'image_size': meta.get('image_size'),
            'wave_resolution': meta.get('wave_resolution'),
            'Cs': ctf.get('Cs'),
            'C5': ctf.get('C5'),
            'astigmatism': ctf.get('astigmatism'),
            'astigmatism_angle': ctf.get('astigmatism_angle'),
            'coma': ctf.get('coma'),
            'coma_angle': ctf.get('coma_angle'),
            'gaussian_spread': ctf.get('gaussian_spread'),
            'x_rotation': xyz[0],
            'y_rotation': xyz[1],
            'z_rotation': xyz[2],
            'rotate_cell': meta.get('rotate_cell'),
            'rotation_mode': meta.get('rotation_mode'),
        }

    _BENCH_COLS = [
        'filename', 'defocus', 'focal_spread', 'angular_spread', 'voltage',
        'sampling', 'dose', 'image_size', 'wave_resolution', 'Cs', 'C5',
        'astigmatism', 'astigmatism_angle', 'coma', 'coma_angle',
        'gaussian_spread', 'x_rotation', 'y_rotation', 'z_rotation',
        'rotate_cell', 'rotation_mode', 'error',
    ]

    def _write_index_csv(self, path, rows):
        import csv
        with open(path, 'w', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=self._BENCH_COLS,
                                    extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def run_benchmark(self):
        """Sweep defocus × focal_spread × angular_spread; one image per combo.

        Reuses the current atoms, exact ASE view matrix, cell mode, and all
        other settings as the base config. Nothing about orientation/
        rotate_cell logic changes -- only these three CTF parameters vary.
        """
        if not self._passes_validation('sweep'):
            return
        atoms = self.gui.atoms

        folder = self.bench_folder.value.strip()
        if not folder:
            ui.error(_('No output folder'),
                     _('Choose an output folder for the sweep.'))
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as err:
            ui.error(_('Cannot create folder'), str(err))
            return

        try:
            defs = self._parse_float_list(self.bench_defocus.value)
            fss = self._parse_float_list(self.bench_focal.value)
            angs = self._parse_float_list(self.bench_angular.value)
        except Exception as err:
            ui.error(_('Bad sweep values'),
                     _('Could not parse a comma-separated number list: {}')
                     .format(err))
            return
        if not (defs and fss and angs):
            ui.error(_('Empty sweep'),
                     _('Each of defocus / focal spread / angular spread needs '
                       'at least one value.'))
            return

        prefix = self.bench_prefix.value.strip() or 'benchmark'
        import itertools
        combos = list(itertools.product(defs, fss, angs))
        total = len(combos)

        atoms_copy = atoms.copy()  # one safe copy reused for all images
        view_axes = self._current_view_axes()
        rc = self._rotate_cell_choice()
        base = dict(
            voltage=float(self.voltage.value) * 1e3,
            sampling=float(self.sampling.value),
            dose=float(self.dose.value),
            image_size=int(self.image_size.value),
            wave_resolution=int(self.wave_res.value),
            Cs=float(self.cs.value),
            C5=float(self.c5.value),
            astigmatism=float(self.astigmatism.value),
            astigmatism_angle=float(self.astigmatism_angle.value),
            coma=float(self.coma.value),
            coma_angle=float(self.coma_angle.value),
            gaussian_spread=float(self.gaussian_spread.value),
            extra_metadata=self._extra_metadata(),
        )

        rows, n_ok, n_fail = [], 0, 0
        for i, (d, fs, ang) in enumerate(combos, 1):
            fname = '{}_def{}_fs{}_ang{}.png'.format(
                prefix, self._fmt_num(d), self._fmt_num(fs), self._fmt_num(ang))
            path = os.path.join(folder, fname)
            self.status.text = _('Benchmark image {} / {}  (def={}, fs={}, '
                                 'ang={})').format(i, total, self._fmt_num(d),
                                                   self._fmt_num(fs),
                                                   self._fmt_num(ang))
            self._pump_events()
            try:
                _img, meta = simulate_tem_from_atoms(
                    atoms_copy, output_file=path,
                    view_axes=view_axes, rotate_cell=rc,
                    defocus=d, focal_spread=fs, angular_spread=ang, **base)
                rows.append(self._bench_row(fname, meta))
                n_ok += 1
            except Exception as err:
                n_fail += 1
                rows.append({'filename': fname, 'error': str(err)})
                self.status.text = _('Benchmark image {} / {} FAILED: {}').format(
                    i, total, err)
                self._pump_events()

        index_path = os.path.join(folder,
                                  '{}_benchmark_index.csv'.format(prefix))
        try:
            self._write_index_csv(index_path, rows)
            index_note = os.path.basename(index_path)
            self._record_output(index_path, 'sweep-index')
        except Exception as err:
            index_note = _('index FAILED: {}').format(err)

        self.status.text = _('Sweep done: {} images ({} ok, {} failed). '
                             'Index: {}').format(total, n_ok, n_fail, index_note)

    def _pump_events(self):
        """Repaint/flush the Tk window so progress is visible mid-sweep."""
        try:
            self.win.win.update()
        except Exception:
            pass

    # ------------------------------------------------------------- display
    def _show_image(self, img, meta):
        """Display the image in a Tk Toplevel without a second mainloop."""
        title = _('abTEM TEM image')
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = Figure(figsize=(5, 5))
            ax = fig.add_subplot(111)
            ax.imshow(img, cmap='gray', vmin=0.0, vmax=1.0, origin='upper')
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(title)
            fig.tight_layout()

            win = ui.Window(title)
            canvas = FigureCanvasTkAgg(fig, master=win.win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            self._image_windows.append((win, fig, canvas))
            return
        except Exception:
            pass

        png = meta.get('output_image')
        if png:
            try:
                import tkinter as tk
                win = ui.Window(title)
                photo = tk.PhotoImage(master=win.win, file=png)
                lbl = tk.Label(win.win, image=photo)
                lbl.image = photo
                lbl.pack()
                self._image_windows.append((win, photo, lbl))
                return
            except Exception:
                pass

        self.status.text = _('Image computed but could not be displayed; '
                             'save it to a PNG instead.')
