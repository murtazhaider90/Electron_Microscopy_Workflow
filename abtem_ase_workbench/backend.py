"""abtem_tem_backend.py -- reusable TEM simulation backend (abTEM).

Front-end-agnostic. No Qt, no Tkinter, no ASE-GUI imports, so it can be used
from the ASE GUI tool, a plain script, or the old standalone app unchanged.

Pipeline:  copy atoms -> optional rigid rotation -> PlaneWave -> Potential
           -> multislice -> CTF -> intensity -> Poisson noise -> safe
           normalization -> (optional) grayscale PNG + JSON metadata.

Principle: ROTATE THE STRUCTURE, NOT THE CAMERA. abTEM always simulates along
+z; orientation is a rigid rotation of a *copy* of the atoms. The caller's
Atoms object is never mutated.

For ASE-GUI driven runs, the canonical orientation input is the GUI's exact
3x3 ``gui.axes`` view matrix.  ASE projects coordinates as ``positions @
gui.axes``; applying that same matrix to a copied structure therefore makes
abTEM's +z propagation axis see exactly the projection that was on screen.
Euler X/Y/Z rotations are retained only as a backwards-compatible API.

Written against the probed API of abTEM 1.x (top-level `abtem.Potential /
PlaneWave / CTF`, lazy `Images` measurements that must be `.compute()`-d, and
aberrations passed as polar aliases through CTF's kwargs).
"""

import os
import json
import inspect
import datetime
import importlib
import importlib.util
try:
    from importlib import metadata as _importlib_metadata
except Exception:  # pragma: no cover
    _importlib_metadata = None

import numpy as np

from ase.io import read as _ase_read

try:
    import ase
    ASE_VERSION = getattr(ase, "__version__", None)
except Exception:
    ASE_VERSION = None

# IMPORTANT FOR GUI STARTUP SPEED:
# Do not import abTEM at module import time. Importing the full scientific stack
# (abTEM/dask/numba/scipy/...) can dominate Windows/PyInstaller startup.  We
# only detect whether the package exists here, then import it on the first real
# simulation request.
abtem = None
try:
    HAVE_ABTEM = importlib.util.find_spec("abtem") is not None
except Exception:
    HAVE_ABTEM = False
try:
    ABTEM_VERSION = (_importlib_metadata.version("abtem")
                     if HAVE_ABTEM and _importlib_metadata is not None else None)
except Exception:
    ABTEM_VERSION = None


def _load_abtem():
    """Import abTEM lazily on first simulation, not when the GUI starts."""
    global abtem, HAVE_ABTEM, ABTEM_VERSION
    if abtem is not None:
        return abtem
    if not HAVE_ABTEM:
        raise RuntimeError(
            "abTEM is not installed. Install it with `pip install abtem`."
        )
    try:
        abtem = importlib.import_module("abtem")
    except Exception as exc:
        HAVE_ABTEM = False
        raise RuntimeError(
            "abTEM is installed but could not be imported: {}".format(exc)
        ) from exc
    ABTEM_VERSION = getattr(abtem, "__version__", ABTEM_VERSION)
    return abtem


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _abtem_ctf_supported_keys():
    """Set of CTF/aberration keyword names the *installed* abTEM understands.

    abTEM's CTF quietly accepts unknown ``**kwargs`` without error, so passing
    an unsupported key (e.g. ``gaussian_spread`` on abTEM 1.x) would be
    silently ignored. We filter against this set and report anything dropped
    in the metadata instead of pretending it was applied.
    """
    _load_abtem()
    supported = set()
    try:
        params = inspect.signature(abtem.CTF.__init__).parameters
        supported.update(k for k in params if k not in ("self", "kwargs"))
    except Exception:
        pass
    try:
        from abtem.transfer import polar_aliases, polar_symbols
        supported.update(polar_aliases.keys())
        supported.update(polar_symbols.keys())
    except Exception:
        supported.update({
            "defocus", "Cs", "C5", "astigmatism", "astigmatism_angle",
            "coma", "coma_angle",
        })
    return supported


def poisson_noise(measurement, dose, rng):
    """Apply physically correct Poisson shot noise to an abTEM image measurement.

    Expected electron count per pixel is ``intensity * dose * pixel_area``;
    values are clipped non-negative before ``rng.poisson`` (which rejects
    negative lambda). Returns a plain float numpy array rather than mutating in
    place, so it is safe even when the backing array is read-only.
    """
    sx, sy = measurement.sampling
    pixel_area = float(sx) * float(sy)
    expected = np.asarray(measurement.array, dtype=float) * float(dose) * pixel_area
    expected = np.clip(expected, 0.0, None)
    return rng.poisson(expected).astype(float)


def safe_normalize(img):
    """Normalize to [0, 1] without dividing by zero on a flat image."""
    img = np.asarray(img, dtype=float)
    mn = float(img.min())
    mx = float(img.max())
    if mx > mn:
        return (img - mn) / (mx - mn)
    return np.zeros_like(img)


def save_gray_png(img01, path):
    """Save a [0, 1] float image as 8-bit grayscale PNG (matplotlib, else PIL).

    Uses matplotlib's non-interactive Agg ``imsave`` (no pyplot windowing, so
    it never touches any GUI event loop). Falls back to Pillow.
    """
    try:
        import matplotlib
        from matplotlib import image as mpimg
        from matplotlib import cm
        # imsave via matplotlib.image avoids pyplot entirely
        mpimg.imsave(path, img01, cmap="gray", vmin=0.0, vmax=1.0)
        return "matplotlib"
    except Exception:
        pass
    try:
        from PIL import Image
        arr8 = np.clip(np.asarray(img01) * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(arr8, mode="L").save(path)
        return "PIL"
    except Exception as e:
        raise RuntimeError(
            "Could not save PNG: neither matplotlib nor Pillow is available "
            f"({e})."
        )


# ---------------------------------------------------------------------------
# main entry points
# ---------------------------------------------------------------------------
def resolve_rotate_cell(atoms, rotate_cell):
    """Resolve the rotate_cell policy (single source of truth).

    ``None`` -> Auto: rotate the cell only for periodic structures. A finite
    particle / cluster / nanoparticle (no PBC) keeps its vacuum box fixed so
    abTEM does not tile skewed periodic copies. Explicit True/False overrides.
    Returns a plain ``bool``.
    """
    if rotate_cell is None:
        return bool(np.any(atoms.pbc))
    return bool(rotate_cell)


def rotation_mode_name(rotate_cell_bool):
    return "periodic_crystal" if rotate_cell_bool else "finite_particle"


def _validated_view_axes(view_axes):
    """Return ``view_axes`` as a validated proper 3x3 rotation matrix.

    ASE GUI stores its current camera/view orientation in ``gui.axes`` and
    projects Cartesian row-vectors with ``positions @ gui.axes``.  The GUI
    matrix should therefore be orthonormal with determinant +1.  Rejecting a
    malformed matrix here is substantially safer than silently feeding a
    shear/reflection into the simulation geometry.
    """
    axes = np.asarray(view_axes, dtype=float)
    if axes.shape != (3, 3):
        raise ValueError("ASE view matrix must have shape (3, 3).")
    if not np.all(np.isfinite(axes)):
        raise ValueError("ASE view matrix contains non-finite values.")
    if not np.allclose(axes.T @ axes, np.eye(3), atol=1e-6, rtol=0.0):
        raise ValueError("ASE view matrix is not orthonormal.")
    det = float(np.linalg.det(axes))
    if not np.isclose(det, 1.0, atol=1e-6, rtol=0.0):
        raise ValueError(
            "ASE view matrix must be a right-handed rotation (determinant +1)."
        )
    return axes.copy()


def apply_view_rotation(atoms, view_axes, recenter=True, rotate_cell=None):
    """Orient a copied structure using ASE GUI's *exact* current view matrix.

    This is the canonical ASE -> abTEM adapter.  ASE draws/project coordinates
    using ``positions @ gui.axes``.  abTEM propagates along +z, so applying the
    very same matrix to the copied atom coordinates makes the simulation x/y
    projection equal to ASE's current x/y projection, without reconstructing
    the orientation through Euler angles.

    The chemistry/species does not matter; this transform is universal.  The
    only policy branch concerns the simulation cell:

    * finite particle (``rotate_cell=False``): transform atoms only, preserve
      the original vacuum box/PBC, then recenter;
    * periodic crystal/slab (``rotate_cell=True``): transform both atoms and
      lattice vectors by the same matrix.

    The input ``atoms`` is never mutated.
    """
    axes = _validated_view_axes(view_axes)
    work = atoms.copy()
    rotate_cell = resolve_rotate_cell(work, rotate_cell)

    original_cell = work.cell.copy()
    original_pbc = work.pbc.copy()

    # ASE uses row-vector coordinates and displays X @ axes.  Keep exactly
    # that convention here so the transformed structure is the ASE view made
    # physical under abTEM's fixed +z beam.
    work.set_positions(np.asarray(work.get_positions(), dtype=float) @ axes)

    if rotate_cell:
        work.set_cell(np.asarray(original_cell.array, dtype=float) @ axes,
                      scale_atoms=False)
    else:
        # Finite-particle anti-tiling rule: the vacuum box is not a specimen
        # orientation and must remain fixed/orthogonal.
        work.set_cell(original_cell, scale_atoms=False)
        work.set_pbc(original_pbc)

    if recenter:
        try:
            work.center()
        except Exception:
            pass
    return work


def abtem_array_to_ase_screen(array):
    """Convert an abTEM x-first array to a normal image matching ASE GUI.

    abTEM stores 2D arrays as ``array[x, y]`` and its documented projection
    convention differs from ASE's viewer.  A standard image array is
    ``image[row=y_from_top, col=x]``.  Transpose x/y and flip the vertical
    direction so saving/displaying with ordinary top-left image conventions
    preserves the same left/right and up/down orientation the user saw in
    ASE.

    This is a *presentation* transform only; it never changes the physics or
    the structure sent to abTEM.
    """
    arr = np.asarray(array)
    if arr.ndim != 2:
        raise ValueError("Expected a 2D abTEM array.")
    return np.flipud(arr.T).copy()


def apply_xyz_rotation(atoms, x_deg, y_deg, z_deg, recenter=True,
                       rotate_cell=None):
    """Legacy helper: rotate a copied structure in fixed X -> Y -> Z order.

    ``rotate_cell`` policy (single source of truth via :func:`resolve_rotate_cell`):
      * None  -> Auto: rotate the cell for periodic crystals, keep the vacuum
                 box fixed for finite particles.
      * True  -> rotate atoms and cell together (periodic crystal).
      * False -> rotate atoms only; the original orthogonal vacuum/simulation
                 box and PBC are restored so a finite particle stays a single
                 particle in one fixed box (fixes the tiled-copies bug).

    New ASE-GUI runs use :func:`apply_view_rotation` with the exact ``gui.axes``
    matrix instead; this function remains for backwards-compatible scripts and
    explicit Euler workflows. The input ``atoms`` is never mutated.
    """
    work = atoms.copy()
    rotate_cell = resolve_rotate_cell(work, rotate_cell)

    original_cell = work.cell.copy()
    original_pbc = work.pbc.copy()

    work.rotate(float(x_deg), "x", rotate_cell=rotate_cell)
    work.rotate(float(y_deg), "y", rotate_cell=rotate_cell)
    work.rotate(float(z_deg), "z", rotate_cell=rotate_cell)

    # For particles, keep the original orthogonal vacuum/simulation box.
    if not rotate_cell:
        work.set_cell(original_cell, scale_atoms=False)
        work.set_pbc(original_pbc)

    if recenter:
        try:
            work.center()
        except Exception:
            pass
    return work


def simulate_tem_from_atoms(
    atoms,
    output_file=None,
    rotation_angle=0.0,
    rotation_axis="z",
    pre_rotation=None,
    rotate_cell=None,
    view_axes=None,
    voltage=80e3,
    defocus=-3.0,
    sampling=0.05,
    dose=5e4,
    image_size=512,
    wave_resolution=512,
    Cs=0.0,
    C5=0.0,
    astigmatism=0.5,
    astigmatism_angle=0.0,
    coma=5.0,
    coma_angle=0.0,
    focal_spread=8.0,
    angular_spread=1.2e-3,
    gaussian_spread=None,
    rng_seed=12345,
    extra_metadata=None,
):
    """Run a normal-mode TEM simulation from an already-loaded ASE ``Atoms``.

    Orientation of the (copied) structure, in priority order:
      * ``view_axes=gui.axes`` -- exact ASE GUI view matrix (preferred).  This
        is the canonical GUI pathway and avoids Euler reconstruction errors.
      * ``pre_rotation=(x, y, z)`` -- legacy fixed X -> Y -> Z degrees.
      * else single-axis ``rotation_angle`` about ``rotation_axis`` (legacy).

    Returns ``(image_array, metadata)`` -- a normalized [0, 1] grayscale image
    and a JSON-serializable metadata dict. The input ``atoms`` is never mutated.
    """
    _load_abtem()  # lazy: first physics request pays the abTEM import cost
    if atoms is None or len(atoms) == 0:
        raise ValueError("No atoms to simulate.")

    # 1/2) Orient a copy -- never touch the caller's object.
    resolved_rotate_cell = resolve_rotate_cell(atoms, rotate_cell)
    rotation_mode = rotation_mode_name(resolved_rotate_cell)
    rotation_applied = False
    xyz_rotation = None
    ase_view_axes = None
    orientation_transform = "none"
    use_xyz = (pre_rotation is not None
               and any(float(a) != 0.0 for a in pre_rotation))
    if view_axes is not None:
        axes = _validated_view_axes(view_axes)
        work = apply_view_rotation(
            atoms, axes, recenter=True, rotate_cell=resolved_rotate_cell)
        ase_view_axes = axes.tolist()
        rotation_applied = not np.allclose(axes, np.eye(3), atol=1e-12)
        orientation_transform = "ase_view_matrix"
    elif use_xyz:
        x, y, z = (float(a) for a in pre_rotation)
        work = apply_xyz_rotation(atoms, x, y, z, recenter=True,
                                  rotate_cell=resolved_rotate_cell)
        xyz_rotation = [x, y, z]
        rotation_applied = True
        orientation_transform = "legacy_xyz"
    elif rotation_angle and float(rotation_angle) != 0.0:
        work = atoms.copy()
        original_cell = work.cell.copy()
        original_pbc = work.pbc.copy()
        work.rotate(float(rotation_angle), rotation_axis,
                    rotate_cell=resolved_rotate_cell)
        if not resolved_rotate_cell:
            work.set_cell(original_cell, scale_atoms=False)
            work.set_pbc(original_pbc)
        try:
            work.center()
        except Exception:
            pass
        rotation_applied = True
        orientation_transform = "legacy_axis_angle"
    else:
        work = atoms.copy()

    # 3) PlaneWave (sampling only -> avoids overspecified-grid warning).
    wave = abtem.PlaneWave(energy=float(voltage), sampling=float(sampling))


    # 4/5) Potential (gpts only) + multislice, with orthogonalize fallback for
    #      non-axis-aligned cells (mirrors ASE-GUI/abTEM orthogonal-box needs).
    orthogonalized = False

    def _build_and_propagate(a):
        potential = abtem.Potential(atoms=a, gpts=int(wave_resolution))
        return wave.multislice(potential)

    try:
        exit_wave = _build_and_propagate(work)
    except Exception:
        result = abtem.orthogonalize_cell(work)
        work = result[0] if isinstance(result, tuple) else result
        orthogonalized = True
        exit_wave = _build_and_propagate(work)

    # 6) CTF -- pass only keys the installed abTEM actually supports.
    supported = _abtem_ctf_supported_keys()
    requested_ctf = {
        "defocus": defocus,
        "Cs": Cs,
        "C5": C5,
        "astigmatism": astigmatism,
        "astigmatism_angle": astigmatism_angle,
        "coma": coma,
        "coma_angle": coma_angle,
        "focal_spread": focal_spread,
        "angular_spread": angular_spread,
    }
    if gaussian_spread is not None:
        requested_ctf["gaussian_spread"] = gaussian_spread

    ctf_kwargs, unsupported_ctf = {}, {}
    for k, v in requested_ctf.items():
        if v is None:
            continue
        (ctf_kwargs if k in supported else unsupported_ctf)[k] = v

    ctf = abtem.CTF(energy=float(voltage), **ctf_kwargs)
    image_wave = exit_wave.apply_ctf(ctf)

    # 7) Intensity (compute the lazy measurement into real numpy).
    intensity = image_wave.intensity()
    if hasattr(intensity, "compute"):
        intensity = intensity.compute()

    # 8) Poisson noise from electron dose + pixel area.
    noise_applied = False
    try:
        noisy_arr = poisson_noise(intensity, dose, np.random.default_rng(rng_seed))
        noise_applied = True
    except Exception:
        noisy_arr = np.asarray(intensity.array, dtype=float)

    # 9) Crop to image_size.
    n = int(image_size)
    img = noisy_arr[:n, :n]

    # 10) Safe normalization.
    img = safe_normalize(img)

    # abTEM's array is x-first, while ordinary image files/matplotlib are
    # row(y)-first.  For exact ASE-GUI driven runs, return/save a standard
    # image array whose visual orientation matches the ASE canvas.  Keep the
    # legacy array behavior for legacy angle-only callers.
    image_presentation = "abtem_raw_array"
    if view_axes is not None:
        img = abtem_array_to_ase_screen(img)
        image_presentation = "ase_gui_screen"

    # metadata
    metadata = {
        "input_file": None,
        "output_image": os.path.basename(output_file) if output_file else None,
        "rotation_angle": float(rotation_angle),
        "rotation_axis": str(rotation_axis),
        "xyz_rotation": xyz_rotation,
        "ase_view_axes": ase_view_axes,
        "orientation_transform": orientation_transform,
        "rotate_cell": bool(resolved_rotate_cell),
        "rotation_mode": rotation_mode,
        "rotation_applied": rotation_applied,
        "orthogonalized": orthogonalized,
        "accelerating_voltage": float(voltage),
        "defocus": float(defocus),
        "sampling": float(sampling),
        "electron_dose": float(dose),
        "image_size": int(image_size),
        "wave_resolution": int(wave_resolution),
        "ctf_parameters": {
            "Cs": float(Cs),
            "C5": float(C5),
            "astigmatism": float(astigmatism),
            "astigmatism_angle": float(astigmatism_angle),
            "coma": float(coma),
            "coma_angle": float(coma_angle),
            "focal_spread": float(focal_spread),
            "angular_spread": float(angular_spread),
            "gaussian_spread": (None if gaussian_spread is None
                                else float(gaussian_spread)),
        },
        "ctf_unsupported_ignored": {k: float(v) for k, v in unsupported_ctf.items()},
        "noise_applied": bool(noise_applied),
        "image_presentation": image_presentation,
        "rng_seed": int(rng_seed),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "abtem_version": ABTEM_VERSION,
        "ase_version": ASE_VERSION,
    }

    # Optional caller-supplied orientation/provenance fields (no physics; just
    # merged into the metadata dict so they land in the JSON sidecar too).
    if extra_metadata:
        try:
            metadata.update(dict(extra_metadata))
        except Exception:
            pass

    # 11) Save PNG + JSON sidecar if an output path was given.
    if output_file:
        save_gray_png(img, output_file)
        stem, _ext = os.path.splitext(output_file)
        meta_path = stem + ".json"
        with open(meta_path, "w") as fh:
            json.dump(metadata, fh, indent=2)
        metadata["metadata_file"] = os.path.basename(meta_path)

    return img, metadata


def _center_crop(arr, n):
    """Center-crop a 2D array to n×n (return as-is if already smaller)."""
    h, w = arr.shape
    if n >= h and n >= w:
        return arr
    y0 = max(0, (h - n) // 2)
    x0 = max(0, (w - n) // 2)
    return arr[y0:y0 + n, x0:x0 + n]


def simulate_diffraction_from_atoms(
    atoms,
    output_file=None,
    rotation_angle=0.0,
    rotation_axis="z",
    pre_rotation=None,
    rotate_cell=None,
    view_axes=None,
    voltage=80e3,
    sampling=0.05,
    wave_resolution=512,
    image_size=512,
    max_angle=None,
    block_direct=False,
    log_scale=True,
    extra_metadata=None,
):
    """Compute a plane-wave (SAED-style) diffraction pattern from ASE ``Atoms``.

    Same orientation handling as :func:`simulate_tem_from_atoms` (a rotated
    *copy*; the input is never mutated) — the beam travels along the current
    view direction. Instead of forming an image with a CTF, this returns the
    exit-wave diffraction pattern (reciprocal space). No imaging physics is
    changed; this is an independent pathway.

    Returns ``(image_array, metadata)``. ``max_angle`` is in mrad (None -> the
    grid antialiasing cutoff). ``log_scale`` compresses the large dynamic range
    for display.
    """
    _load_abtem()  # lazy: first physics request pays the abTEM import cost
    if atoms is None or len(atoms) == 0:
        raise ValueError("No atoms to simulate.")

    # Orient a copy (identical policy to the imaging path).
    resolved_rotate_cell = resolve_rotate_cell(atoms, rotate_cell)
    rotation_mode = rotation_mode_name(resolved_rotate_cell)
    rotation_applied = False
    xyz_rotation = None
    ase_view_axes = None
    orientation_transform = "none"
    if view_axes is not None:
        axes = _validated_view_axes(view_axes)
        work = apply_view_rotation(
            atoms, axes, recenter=True, rotate_cell=resolved_rotate_cell)
        ase_view_axes = axes.tolist()
        rotation_applied = not np.allclose(axes, np.eye(3), atol=1e-12)
        orientation_transform = "ase_view_matrix"
    elif pre_rotation is not None and any(float(a) != 0.0 for a in pre_rotation):
        x, y, z = (float(a) for a in pre_rotation)
        work = apply_xyz_rotation(atoms, x, y, z, recenter=True,
                                  rotate_cell=resolved_rotate_cell)
        xyz_rotation = [x, y, z]
        rotation_applied = True
        orientation_transform = "legacy_xyz"
    elif rotation_angle and float(rotation_angle) != 0.0:
        work = atoms.copy()
        oc, op = work.cell.copy(), work.pbc.copy()
        work.rotate(float(rotation_angle), rotation_axis,
                    rotate_cell=resolved_rotate_cell)
        if not resolved_rotate_cell:
            work.set_cell(oc, scale_atoms=False)
            work.set_pbc(op)
        try:
            work.center()
        except Exception:
            pass
        rotation_applied = True
        orientation_transform = "legacy_axis_angle"
    else:
        work = atoms.copy()

    wave = abtem.PlaneWave(energy=float(voltage), sampling=float(sampling))
    orthogonalized = False

    def _build(a):
        potential = abtem.Potential(atoms=a, gpts=int(wave_resolution))
        return wave.multislice(potential)

    try:
        exit_wave = _build(work)
    except Exception:
        result = abtem.orthogonalize_cell(work)
        work = result[0] if isinstance(result, tuple) else result
        orthogonalized = True
        exit_wave = _build(work)

    ma = 'cutoff' if max_angle is None else float(max_angle)  # abTEM: mrad
    dp = exit_wave.diffraction_patterns(max_angle=ma,
                                        block_direct=bool(block_direct))
    if hasattr(dp, "compute"):
        dp = dp.compute()
    arr = np.asarray(dp.array, dtype=float)
    if log_scale:
        arr = np.log1p(np.clip(arr, 0.0, None))

    img = _center_crop(arr, int(image_size))
    img = safe_normalize(img)
    image_presentation = "abtem_raw_array"
    if view_axes is not None:
        img = abtem_array_to_ase_screen(img)
        image_presentation = "ase_gui_screen"

    metadata = {
        "mode": "diffraction",
        "input_file": None,
        "output_image": os.path.basename(output_file) if output_file else None,
        "rotation_angle": float(rotation_angle),
        "rotation_axis": str(rotation_axis),
        "xyz_rotation": xyz_rotation,
        "ase_view_axes": ase_view_axes,
        "orientation_transform": orientation_transform,
        "rotate_cell": bool(resolved_rotate_cell),
        "rotation_mode": rotation_mode,
        "rotation_applied": rotation_applied,
        "orthogonalized": orthogonalized,
        "accelerating_voltage": float(voltage),
        "sampling": float(sampling),
        "wave_resolution": int(wave_resolution),
        "image_size": int(image_size),
        "max_angle_mrad": (None if max_angle is None else float(max_angle)),
        "block_direct": bool(block_direct),
        "log_scale": bool(log_scale),
        "image_presentation": image_presentation,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "abtem_version": ABTEM_VERSION,
        "ase_version": ASE_VERSION,
    }
    if extra_metadata:
        try:
            metadata.update(dict(extra_metadata))
        except Exception:
            pass

    if output_file:
        save_gray_png(img, output_file)
        stem, _ext = os.path.splitext(output_file)
        meta_path = stem + ".json"
        with open(meta_path, "w") as fh:
            json.dump(metadata, fh, indent=2)
        metadata["metadata_file"] = os.path.basename(meta_path)

    return img, metadata


def simulate_tem_from_file(
    input_file,
    output_file,
    rotation_angle=0.0,
    rotation_axis="z",
    pre_rotation=None,
    rotate_cell=None,
    view_axes=None,
    voltage=80e3,
    defocus=-3.0,
    sampling=0.05,
    dose=5e4,
    image_size=512,
    wave_resolution=512,
    Cs=0.0,
    C5=0.0,
    astigmatism=0.5,
    astigmatism_angle=0.0,
    coma=5.0,
    coma_angle=0.0,
    focal_spread=8.0,
    angular_spread=1.2e-3,
    gaussian_spread=None,
    rng_seed=12345,
    extra_metadata=None,
):
    """Load a structure from ``input_file`` (any ASE-readable format, including
    VASP POSCAR) and run :func:`simulate_tem_from_atoms`."""
    atoms = _ase_read(input_file)
    img, metadata = simulate_tem_from_atoms(
        atoms,
        output_file=output_file,
        rotation_angle=rotation_angle,
        rotation_axis=rotation_axis,
        pre_rotation=pre_rotation,
        view_axes=view_axes,
        rotate_cell=rotate_cell,
        voltage=voltage,
        defocus=defocus,
        sampling=sampling,
        dose=dose,
        image_size=image_size,
        wave_resolution=wave_resolution,
        Cs=Cs,
        C5=C5,
        astigmatism=astigmatism,
        astigmatism_angle=astigmatism_angle,
        coma=coma,
        coma_angle=coma_angle,
        focal_spread=focal_spread,
        angular_spread=angular_spread,
        gaussian_spread=gaussian_spread,
        rng_seed=rng_seed,
        extra_metadata=extra_metadata,
    )
    metadata["input_file"] = os.path.basename(input_file)
    if output_file:
        stem, _ext = os.path.splitext(output_file)
        with open(stem + ".json", "w") as fh:
            json.dump(metadata, fh, indent=2)
    return img, metadata
