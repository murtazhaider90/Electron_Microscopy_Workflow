"""Pre-run validation for simulation requests.

Returns (hard_errors, soft_warnings) lists of readable strings so the GUI can
display them as a modal error or a confirm dialog, respectively. No Tk and no
abTEM import at module load time — the caller passes a ``have_abtem`` flag.
"""
from typing import List, Tuple

import numpy as np

Lists = Tuple[List[str], List[str]]


def validate_run(
    atoms,
    *,
    kind: str = "image",
    have_abtem: bool = True,
    rotate_cell_effective,
    image_size: int = 512,
    wave_resolution: int = 512,
    sampling: float = 0.05,
    sweep_total: int = 0,
) -> Lists:
    """Collect readable error/warning strings for the current request.

    Parameters
    ----------
    atoms : ase.Atoms or None
    kind : one of ``"image"``, ``"diffraction"``, ``"sweep"``, ``"preview"``.
    have_abtem : whether abTEM is importable (the caller already knows).
    rotate_cell_effective : the resolved rotate_cell choice (True / False /
        None for Auto); only used to warn about finite-particle mix-ups.
    image_size, wave_resolution, sampling : current grid/sampling settings.
    sweep_total : for ``kind="sweep"``, the number of combinations.
    """
    hard: List[str] = []
    soft: List[str] = []

    if not have_abtem:
        hard.append("abTEM is not installed (pip install abtem).")

    if atoms is None or len(atoms) == 0:
        hard.append("No structure is loaded.")
        return hard, soft

    try:
        vol = float(abs(np.linalg.det(np.asarray(atoms.cell.array, float))))
    except Exception:
        vol = 0.0
    if vol < 1e-9:
        hard.append("The cell has zero volume — abTEM needs a valid box.")

    is_periodic = bool(np.any(atoms.pbc))
    if (not is_periodic) and rotate_cell_effective is True:
        soft.append(
            'Finite particle with "periodic crystal" rotation selected — '
            "this can tile copies. Consider Auto or Finite particle.")

    if atoms.pbc.tolist() == [True, True, False]:
        try:
            if float(atoms.cell.lengths()[2]) < 2.0:
                soft.append("2D slab has little/no vacuum along z.")
        except Exception:
            pass

    try:
        isz = int(image_size)
        wres = int(wave_resolution)
        if kind != "preview" and (isz > 2048 or wres > 2048):
            soft.append(
                "Large grid ({}×{} / {} gpts) — this may be slow and "
                "memory-heavy.".format(isz, isz, wres))
        s = float(sampling)
        if s > 0.3:
            soft.append(
                "Sampling {:.3g} Å/pixel is coarse — high angles may alias."
                .format(s))
        elif s < 0.01:
            soft.append(
                "Sampling {:.3g} Å/pixel is very fine — slow.".format(s))
    except Exception:
        pass

    if kind == "diffraction" and not is_periodic:
        soft.append(
            "Diffraction of a non-periodic structure gives a diffuse pattern "
            "rather than sharp spots.")

    if kind == "sweep" and sweep_total > 200:
        soft.append(
            "Sweep will produce {} images — this may take a long time."
            .format(sweep_total))

    return hard, soft


__all__ = ["validate_run"]
