# Independent scientific validation

Reviewed 2026-10-08 against task baseline `0c2d2cf` (included in main
`3a2cf27`). This is an audit, not scientific certification. Production code,
GUI design, and all pre-existing assertions are unchanged. Confirmed defects
are represented by ordinary failing regression tests, not skips or xfails.

## Resolution update (2026-10-08)

The following audit text and its regression tests preserve the original findings.
Production fixes and the supported/rejected scientific policies are now detailed
in [SCIENTIFIC_RESOLUTION.md](SCIENTIFIC_RESOLUTION.md). QA-01 through QA-08
have implementation changes, with a conservative exact-periodic limitation.
The unchanged independent QA suite now has 174 passes and four visible
contract conflicts; the complete slow/GUI suite has 285 passes, six failures
and one existing CIF skip. Two failures are original baseline success-path
fixtures incompatible with the stricter geometry policy. All 46 added
resolution checks pass. This is **not an all-green validation result**.
No QA or baseline assertion was changed or suppressed. Human review is required
for the six documented test/policy conflicts before treating this as merge-ready.

## Result

The exact matrix adapter preserves species-labelled geometry, handedness, cell
policy, and source structures. Tested orthogonal finite/crystal TEM and native
MoS2 TEM agree with independently assembled abTEM calculations. Tested Si
image/diffraction paths and Poisson statistics agree with their independent
oracles. These successes **do not establish exact end-to-end orientation for
arbitrary periodic specimens**: abTEM's preparation can strain the rotated
lattice and this is not recorded by the backend.

Eight findings remain unresolved. The new tests intentionally leave the full
suite red so these issues cannot be mistaken for passing validation.

## Reproduction and environment

Python 3.12.14, ASE 3.29.0, abTEM 1.0.10, CPU; interpreter:
`/workspace/venvs/electron-microscopy/bin/python`. The local abTEM source files
match their installed distribution RECORD hashes. For precise provenance:

| File | SHA-256 |
| --- | --- |
| abtem/atoms.py | 07830b5a6ca83722fbfe86d9cbbd429835bf992564abcf49c721004dd359ca77 |
| abtem/potentials/iam.py | c0b0a0e4491df866463fffa868424d0e78ce7cb55da829c835a024c07859bf2e |

Run from the repository root (with the prepared environment):

```bash
export PATH=/workspace/cloud-setup/x11/usr/bin:/workspace/venvs/electron-microscopy/bin:$PATH
export MPLCONFIGDIR=/tmp/scientific-mpl
export PYTHONPYCACHEPREFIX=/tmp/scientific-pycache
xvfb-run -a python -m pytest --run-slow --run-gui -q -rs
```

The sandbox restricts X11 sockets; the successful full run used the same command
outside that restriction. Earlier sandbox attempts skipped GUI tests and are
not counted as the full verification.

| Run | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Unchanged existing suite, slow and GUI enabled | 67 | 0 | 1 |
| Full suite including new audit tests, slow and GUI enabled | 235 | 10 | 1 |

The existing CIF import test skips because its graphene fixture has a zero
out-of-plane cell vector and the CIF writer rejects it. No assertion or skip
policy was changed. GUI checks execute successfully. The principal warnings
are ASE/NumPy shape-setting deprecations. Default pytest does not run the abTEM
physics gates: use both flags for full validation.

## Independent methods and coverage

`tests/test_scientific_geometry.py` uses a labelled scalene H/He/Li/Be
tetrahedron. Identity, +/-90 and 37 degree x/y/z matrices, an arbitrary
31x/-17y/63z matrix, and 32 deterministic QR-generated proper random matrices
are each tested with finite, 2D, and 3D PBC. Expectations come from Cartesian
row-vector multiplication, ASE active rotations, and ASE cell mathematics;
they do not reconstruct the backend through Euler angles.

`tests/test_scientific_pipeline.py` independently constructs PlaneWave,
Potential, CTF, multislice, image intensity, and diffraction objects. It applies
separate Poisson, cropping, normalization, and presentation arithmetic rather
than calling the corresponding backend helpers for its oracle. Inspection of
`Potential.get_transformed_atoms()` checks beyond the adapter boundary.

| Requested area | Evidence and practical limit |
| --- | --- |
| Identity and pure x/y/z rotations | Exact coordinates and cells; comparison to ASE `Atoms.rotate` and `ase.utils.rotate`. |
| Arbitrary and randomized proper rotations | 43 matrices across three PBC modes; proper determinant and Gram matrix preservation. Random seed 20261008. |
| Asymmetric handedness | Labelled tetrahedron signed volume and pairwise geometry; a reflected or transposed nontrivial matrix cannot pass. |
| Exact projected coordinates | Absolute `positions @ axes` without recentering; all relative coordinates with recentering. Uniform translation is allowed. Actual periodic preparation fails QA-05. |
| Finite anti-tiling | Existing Pt13 border-contrast gate retained; tilted asymmetric particle retains one set of four labels and the fixed cell at the Potential boundary. Undersized box fails QA-07. |
| 2D periodicity and vacuum | Graphene/MoS2 existing image and diffraction gates; direct MoS2 TEM equivalence; native MoS2 prepared PBC, thickness, z extrema and vacuum retained. Arbitrary tilted slab fails QA-05. |
| 3D periodic crystal | Si rotated-cell math, direct TEM and cropped diffraction; arbitrary tilted periodic lattice fails QA-05. |
| Source Atoms immutability | Positions, every array, cell, PBC and info checked after geometry and actual TEM/diffraction, including downstream engine failure. This does not test adversarial mutable objects nested in `Atoms.info`. |
| Si diamond selection rules | Independent structure-factor sum over ASE fractional coordinates for all 729 indices in [-4,4]^3; analytic parity/diamond conditions. Existing direct multislice [001] extinction gate retained. |
| TEM sampling and FOV | Actual abTEM measurement sampling compared with reported metadata; mismatch fails QA-01. Rectangular cell exposes anisotropic sampling. |
| Poisson statistics | Absolute mean within five standard errors, variance within 2.5%, integer counts, no input mutation at three doses; independent area and sqrt(dose) SNR scaling over 262144 pixels. |
| Dose/SNR | 9x dose produces 9x counts and 3x SNR; doubling pixel area doubles counts. This concerns raw electron counts, not the min/max-normalized display. |
| Metadata reproducibility | Same seed reproduces identical pixels and stable metadata except timestamp/output names; JSON fields agree where present; versions and exact matrix recorded. QA-01/03/06 limit truthful reconstruction. |
| Exported oriented structures | Same ASE writer as GUI; extxyz roundtrip preserves labels, PBC, rotated cell and relative exact coordinates for all three modes. Export precedes abTEM preparation, so periodic simulation equality fails QA-05. File-dialog integration is not newly exercised. |
| Reproducible scripts | Execute exported code with supplied `atoms` and compare actual image with an independent backend invocation for GUI-default seed; nondefault seed fails QA-04. |
| Presentation versus physics | Non-square coordinate-labelled image verifies right/up mapping, no aliasing, and dimensionality errors; TEM/diffraction presentation arithmetic checked separately. Structure rotation is never inferred from a displayed image. |
| Invalid inputs/errors | Six malformed matrices, both backend reflection rejection paths, existing empty/missing-engine/path gates, invalid dose regressions and negative image sizes. This is representative coverage, not exhaustive validation of every numeric input. |

The pre-existing orientation tests include replicas of some helper functions.
New tests call the public helpers and compare with ASE arithmetic; those older
tests remain unchanged. A passing direct-abTEM comparison establishes adapter
agreement with the installed engine, not independent validation of all abTEM
physics. Kinematic selection rules, geometry and counting statistics provide
separate mathematical checks. Thick-crystal dynamical scattering need not obey
all kinematic extinctions universally; the retained [001] test is a specific
fixture, not a claim for every thickness or zone axis.

## Findings and failing regressions

### QA-01 — Reported sampling does not describe the matched grid

`PlaneWave(sampling=...)` is matched to `Potential(gpts=wave_resolution)`.
For a 16 x 18 Angstrom cell, 48 grid points and requested 0.2 Angstrom sampling,
the actual intensity sampling is (1/3, 0.375) Angstrom/pixel. Metadata reports
0.2. A 32 x 32 raw crop covers (10.6667, 12) Angstrom, not (6.4, 6.4).
Poisson counts correctly use the actual intensity pixel area, making the
metadata inconsistency especially consequential for dose interpretation.
Diffraction metadata also records the requested real-space sampling without
actual reciprocal pixel spacing or returned grid dimensions.

Regression: `test_sampling_metadata_matches_actual_abtem_grid`.
A focused future resolution should distinguish requested and realized sampling,
record axis order and physical FOV, and clarify which grid control is authoritative.

### QA-02 — Invalid doses silently produce plausible output

Negative dose is clipped into zero expected counts and gives a black normalized
image. NaN dose raises inside NumPy Poisson but the broad exception handler
silently substitutes noiseless intensity. Neither simulation raises ValueError;
NaN can also enter a non-standard JSON sidecar. This is not validation.

Regressions: `test_invalid_dose_must_raise[-1]` and `[nan]`.
Validate finite nonnegative physical dose and propagate meaningful failures.

### QA-03 — Caller annotations can falsify physical provenance

`metadata.update(extra_metadata)` permits replacing RNG seed, sampling, exact
matrix, and any other physical field after simulation. An image computed with
seed 567 can claim seed 999. Both simulation entry points have this merge pattern.

Regression: `test_metadata_cannot_overwrite_physical_provenance`.
Reserve physical fields or isolate caller annotations in a separate namespace.

### QA-04 — Exported script omits nondefault stochastic seed

`build_repro_script` accepts a params dictionary but its template never writes
`rng_seed`. A seed of 567 reproduces with backend default 12345. Current GUI
runs use the default, and the actual default-seed script equivalence test passes.
This defect concerns the broader reproducibility helper, not a demonstrated
failure of the current default GUI workflow. The template also omits optional
`gaussian_spread`; no scientific effect is asserted here for an unsupported key.

Regression: `test_repro_script_preserves_nondefault_seed`.

### QA-05 — Exact periodic geometry changes inside abTEM preparation

For a 31x/-17y/63z view, direct `Potential.get_transformed_atoms()` uses periodic
orthogonalization with `allow_transform=True`. Integer lattice cuts can then
receive an affine map to an orthogonal box. A direct abTEM transform-matrix
probe yields maximum deviations from identity of about 0.0598 for Si and 0.3344
for MoS2. This is a deformation, not merely replicating a rigidly oriented
specimen. Same-species nearest-lattice-site residuals are 2.22431 Angstrom for
Si and 13.8825 Angstrom for the tilted MoS2 slab in the audited runs. For slabs,
translations along the nonperiodic vacuum vector are also disallowed by the test.

Regressions: `test_abtem_preparation_preserves_exact_periodic_geometry[si_bulk]`
and `[mos2_slab]`. These capture preparation from the Potential actually created
by the backend; source ASE structures remain unchanged.

The adapter and extxyz export remain rigid and exact. Thus exporting the oriented
structure does not necessarily export the structure that abTEM actually simulates.
Finite periodic-box approximations for an arbitrary crystal direction require an
explicit scientific policy. This audit does not choose a new policy or modify
abTEM physics. Native aligned slabs and tested orthogonal orientations pass.

### QA-06 — Hidden preparation transform is not recorded

`orthogonalized` tracks only the backend's exception fallback. A Potential can
successfully perform its own orthogonalization while the returned metadata says
False. Applied affine transforms, prepared cell, atom count, and prepared
structure are absent, preventing faithful reconstruction from metadata alone.

Regression: `test_hidden_abtem_orthogonalization_is_recorded`.
Record what the engine actually prepared, not just which exception path ran.

### QA-07 — A finite particle can outgrow the fixed box on rotation

An elongated four-marker particle fitting a 12 x 6 x 6 Angstrom box is rotated
90 degrees around z. The adapter keeps the original box, recenters, and returns
y coordinates outside [0,6]. No validation or expansion intervenes. A fixed box
helps avoid skew-cell replication for the tested Pt13 case but cannot guarantee
safe simulation for every finite particle orientation. Out-of-box atoms can lead
to boundary artifacts or lost content downstream; this regression establishes
the invalid geometry, not a universal claim about how every integrator treats it.

Regression: `test_finite_rotation_must_fit_simulation_box`.
It permits either explicit rejection or safe resizing, while requiring containment.

### QA-08 — Negative TEM image size is accepted as a Python slice

TEM with `image_size=-1` returns the array with its last row and column removed
rather than rejecting an invalid requested size. Diffraction currently raises
ValueError later when normalizing an empty crop; its corresponding test passes,
but the error is incidental rather than explicit input validation.

Regression: `test_negative_image_size_must_raise[simulate_tem_from_atoms]`.

## Further limits from source review

- Any preparation/propagation exception triggers orthogonalization, even an
  unrelated engine failure. Recentring errors are swallowed. The audit checks
  source immutability on error but does not endorse these recovery policies.
- TEM crops from the low-index corner; diffraction crops around the center.
  Requested image size can exceed available dimensions. Actual shape, crop
  origin, and coordinate axes are not recorded. The display is min/max normalized
  and is not a calibrated intensity/count export.
- `rotation_mode` calls a 2D slab `periodic_crystal` because Auto uses `any(pbc)`.
  PBC survives the adapter, but Potential's `periodic=True` default and internal
  geometry preparation are separate from ASE's per-axis flags. Native slab
  checks pass; general tilted slab correctness is not established.
- The TEM/diffraction sidecar is written before `metadata_file` is added to the
  returned dictionary. The file wrapper rewrites its sidecar afterward. Tests
  compare stored fields without claiming the dictionaries are identical.
- Results depend on engine versions, implicit potential/slicing defaults, input
  coordinates and prepared geometry. Existing metadata does not fully serialize
  these. Matching pixels in this environment is not a guarantee across versions,
  devices or unspecified input structures.

No broad speculative physics change was made. The immediate review priority is
QA-05/06 (exact periodic specimen contract), followed by calibrated grid metadata
and explicit invalid-input handling. Each finding needs a focused resolution
with its regression retained.
