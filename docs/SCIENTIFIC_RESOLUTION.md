# Scientific QA resolution

Validated on 2026-10-08 using Python 3.12.14, ASE 3.29.0 and abTEM 1.0.10
on CPU. QA commit `493ddfb` was cherry-picked before production changes.
The original production resolution retained all baseline/QA assertions. The
2026-10-09 reconciliation below updates their success/rejection contracts without
changing production code, numeric tolerances, skip policy or scientific coverage.
GUI, viewer and installer code are unchanged.

**Product limitation:** arbitrary periodic viewer orientations are not universally
supported. Simulation now stops before constructing a Potential when an exact
axis-aligned commensurate cell is unavailable within abTEM's bounded search.
Finite specimens retain arbitrary proper rotations when their box contains them.

**Review status (2026-10-09):** all six documented test-contract conflicts are
resolved under the approved exact-geometry and requested/realized sampling
policies. The complete slow/GUI suite passes: 294 passed, 0 failed, one existing
CIF skip. No tests were deleted, skipped or xfailed to reconcile the contracts.

## Finding-by-finding resolution

| Finding | Root cause | Adopted fix and behavior |
| --- | --- | --- |
| QA-01 | Potential `gpts` controls the matched grid, overriding PlaneWave sampling. | Record measurement-derived x/y sampling, crop shape, FOV, pixel area, axes and output shape. Diffraction records actual reciprocal/angular spacing, offset and reciprocal crop extent separately from real-space request/grid. Preserve legacy scalar `sampling` as an explicitly labelled request. |
| QA-02 | Negative dose was clipped; an exception could silently substitute noiseless intensity. | Validate finite nonnegative scalar dose before loading the engine and inside the noise helper. Remove noiseless exception fallback. Zero dose intentionally produces zero electron counts and a black normalized display. |
| QA-03 | Unrestricted dictionary merge replaced authoritative fields. | Put all annotations under `user_metadata`. Mirror only seven known legacy descriptive GUI fields. Engine, cell, PBC, dose, seed, exact matrix and calibration fields cannot be overwritten. |
| QA-04 | Script template omitted the stochastic seed and optional settings. | Export `rng_seed`, `gaussian_spread`, and legacy axis/angle parameters, in addition to all previously documented helper parameters. Unsupported Gaussian spread remains reported as ignored by the engine; the export does not claim it has a physical effect. |
| QA-05 | abTEM implicitly strains an integer cut to fit its orthogonal box. | Request abTEM's unstrained cut; accept only a positive axis-aligned exact integer supercell with correct atom count. Reject inexact periodic orientations and tilted/nonstandard slabs. Preserve exact matrix and rigid coordinates. Never fall back to strained preparation on engine errors. |
| QA-06 | The old boolean recorded only an exception fallback, missing internal preparation. | Record validated preparation method, whether preparation/orthogonalization occurred, oriented and prepared cells, atom counts, actual PBC, exact-geometry preservation, grid and slice settings. Inspect actual `Potential.get_transformed_atoms()` before propagation and reject unexpected engine changes. |
| QA-07 | A fixed box can be too small after a rigid rotation. | Reject insufficient finite boxes after centering; require explicit vacuum expansion. Reject skewed finite calculation boxes instead of tiling them. Preserve source Atoms and PBC=False. |
| QA-08 | Negative slicing and integer coercion implicitly defined image size. | Validate positive integral scalar image size and wave resolution in both entry points before entering the numerical pipeline. Reject zero, negative, fractional, nonfinite, Boolean, string and nonscalar sizes. Integral numeric values such as 32.0 are accepted. |

## Exact-orientation preparation policy

| Specimen type | Orientation case | Exact geometry supported? | Preparation policy |
| --- | --- | --- | --- |
| Finite, PBC=False | Any validated proper matrix; positive fixed orthogonal box contains oriented atoms | Yes | Keep one particle, recenter when requested, set Potential periodic=False; reject insufficient vacuum. |
| Finite, PBC=False | Explicitly rotated/skewed calculation box | No | Reject at simulation boundary; geometry/export helpers can still return the rigidly rotated structure. |
| 2D periodic | PBC=[True,True,False], periodic vectors in xy, positive vacuum vector along z; exact in-plane commensurate cell | Yes | Unstrained abTEM/ASE cut; forbid replication/mixing of the vacuum vector. Native hexagonal MoS2 is supported. |
| 2D periodic | Tilted periodic plane, negative/nonaligned vacuum vector or other partial-PBC conventions | No in this policy | Reject with explanation. No implicit slab thickening, vacuum replication, finite conversion or affine deformation. |
| 3D periodic | Axis-aligned cells and exact commensurate rotated cells found by abTEM | Yes | Unstrained abTEM/ASE integer cut; exact geometry and beam direction retained. |
| 3D periodic | Arbitrary rotation whose bounded cut is not axis aligned | No in this policy | Reject before Potential construction; choose an exact commensurate orientation or explicitly construct a finite specimen. |
| 1D periodic | Any | Unsupported | Reject explicitly as an unsupported partial-periodicity convention. |

`rotate_cell=False` with a nonidentity physical rotation of a periodic specimen
is also rejected: detaching the atoms from their lattice changes the material.
The physical orientation helpers keep their existing general geometry behavior;
simulation is the stricter engine boundary.

The preparation uses established abTEM `orthogonalize_cell` and ASE `cut`, not a
new crystallographic construction algorithm. `allow_transform=False` leaves the
integer cut unstrained. `return_transform_matrix=True` also avoids the installed
source's alternate nonorthogonal early-return path. Acceptance checks the actual
cell, not an Euler readout or a suggested affine transform. Numerical zeros may
be rounded only within 1e-8 Å. The cell must reconstruct from integer multiples
of the original oriented lattice within this tolerance. Prepared atom count must
match the determinant of this replication matrix. For slabs, the nonperiodic
vector must be unchanged and cannot contribute to the in-plane vectors.

The default abTEM search has `max_repetitions=5`; it is a bounded search, not a
proof that a rejected direction has no possible exact larger cell. This is a
conservative support boundary. No nearest-zone approximation is substituted.

## Direct engine evidence for rejection

For the original QA matrix `ase.utils.rotate('31x,-17y,63z')`, independently
rotate positions and cell, then center with ASE. In installed abTEM:

```python
cut, affine = abtem.orthogonalize_cell(
    oriented.copy(), allow_transform=False, return_transform_matrix=True)
```

| Specimen | max(abs(affine - identity)) | Max off-diagonal unstrained cell component (Å) |
| --- | ---: | ---: |
| Si diamond conventional cell | 0.0598210705 | 1.99337909 |
| MoS2 native slab | 0.3343788491 | 7.43900842 |

Those unstrained cells are not Cartesian boxes. The direct Potential default
path applies the affine map, as demonstrated by the retained audit and its
nearest-site residuals. `periodic=False` would instead cut a box that may break
periodicity; it is not an exact periodic solution and is not used to make these
requests pass. Increasing approximate replication without proving exactness
would also not satisfy the product invariant.

## Metadata contract and retained behavior

- `sampling` remains the scalar real-space **request**, matching legacy GUI
  session export (`gui.py` uses it as an input parameter). Every result includes
  `sampling_semantics="legacy_requested_real_space_sampling"`,
  `requested_sampling_angstrom`, and `grid_control="potential_gpts"`.
- TEM calibration is `actual_sampling_angstrom=[sx,sy]`,
  `pixel_area_angstrom2`, and `field_of_view_angstrom=[nx*sx,ny*sy]` for the raw
  crop. Poisson counts use the same measured pixel area and dose in electrons/Å².
- `measurement_shape_xy`, `crop_shape_xy`, `crop_origin_xy_pixels`,
  `returned_array_shape`, `measurement_axis_order` and `returned_axis_order`
  distinguish raw x-first coordinates from screen row/column order. FOV is
  pixel-count times spacing, not the separation of the first and last centers.
- Diffraction adds `reciprocal_sampling_inverse_angstrom`,
  `angular_sampling_mrad`, `reciprocal_crop_offset_inverse_angstrom`,
  `reciprocal_crop_extent_inverse_angstrom` and
  `actual_real_space_sampling_angstrom`. These come from measurement/Potential
  properties; no unmeasured reciprocal calibration is invented.
- `preparation` records specimen type, method, cells, atom counts, PBC,
  Potential periodicity, slice thicknesses, actual grid and explicit potential
  settings (Lobato, infinite projection, xy plane, zero origin, device).
  `orthogonalized` now reflects cell/replication changes. `preparation_occurred`
  separately records periodic preparation, even if it only wraps coordinates.
- Physical provenance cannot be replaced. All caller keys survive under
  `user_metadata`; known descriptive orientation-source, indices and structure
  source/formula identifiers retain top-level compatibility. `structure_pbc` is
  generated from the source instead of trusted from annotations.
- Exact-view screen transpose/vertical flip remains a presentation operation.
  TEM retains low-index cropping; diffraction retains central cropping.
  Min/max normalization, seed default 12345, CTF filtering and file behavior
  remain unchanged. Normalized images are not raw calibrated intensity/count
  exports. Sidecars remain concise and do not serialize large atom arrays.

## Historical validation before test-contract reconciliation

Commands used the supplied virtual environment, Xvfb and writable cache paths.
No application or test assertions were changed to produce these results.

| Run | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Original baseline before fixes: pytest | 44 | 0 | 24 |
| Original baseline before fixes: pytest --run-slow | 53 | 0 | 15 |
| Original baseline before fixes: Xvfb, slow + GUI | 67 | 0 | 1 |
| Original independent QA before fixes: slow | 168 | 10 | 0 |
| Original independent QA after fixes: slow | 174 | 4 | 0 |
| Added resolution tests: slow | 46 | 0 | 0 |
| Final full suite: pytest | 227 | 0 | 65 |
| Final full suite: pytest --run-slow | 271 | 6 | 15 |
| Final full suite: Xvfb, slow + GUI | 285 | 6 | 1 |

In the final full run, the original baseline accounts for **65 passed, 2 failed,
1 skipped**; original independent QA for **174 passed, 4 failed**; added
resolution tests for **46 passed**. All fourteen GUI checks pass. Five of six
original backend physics tests pass; the remaining test's unsafe comparison
case is explicitly blocked. The fast baseline remains 44 passed.

## Test-contract reconciliation (2026-10-09)

Work starts at PR #9 head `6c5403b15251383e8bf6c902cdcd291a5f0246e5`.
Production code is unchanged. The historical six failures above were resolved as
follows; numeric tolerances and independent scientific oracles remain intact.

1. QA `test_sampling_metadata_matches_actual_abtem_grid` now checks legacy
   `sampling` and explicit `requested_sampling_angstrom` against the request,
   and `actual_sampling_angstrom` against direct abTEM measurement sampling
   with the original 1e-12 absolute tolerance. It also checks actual pixel
   area, crop FOV, grid/crop/returned shapes, origin and raw x/y axis ordering.
   The rectangular fixture still exposes anisotropic realized sampling.
2. QA `test_abtem_preparation_preserves_exact_periodic_geometry` now covers
   both safe rejection of the original arbitrary Si/MoS2 tilt and successful
   aligned preparations. Rejection checks the documented ValueError before
   any real Potential construction and full source immutability. Supported
   cases still use the real Potential and the original same-species fractional
   lattice residual oracle, forbidding translations through slab vacuum.
3. QA `test_hidden_abtem_orthogonalization_is_recorded` now uses an exact
   rational 3:4:5 rotation of a labelled non-cubic periodic specimen. It compares
   captured real Potential atoms/cell/species against direct unstrained abTEM
   preparation, independently checks integer lattice/count equivalence and
   source immutability, and verifies method, prepared cell/count, oriented
   cell/count, preparation/orthogonalization status and exact rigid geometry.
   Unsupported tilted preparation remains covered by the preceding rejection
   cases and the unchanged resolution rejection tests for both pipelines.
4. Baseline `test_image_metadata_schema` uses identity Si [001], with matching
   descriptive zone indices; every existing key/value, matrix, image and
   sidecar assertion remains. Added `test_metadata_unsupported_orientation_rejected`
   checks the original 10x/5y fixture's clear error, no Potential creation and
   source immutability separately.
5. Baseline `test_anti_tiling_finite_particle` retains the original Pt13
   featureless-border threshold (std < 0.03). It replaces the unsafe skew-box
   image comparison with explicit pre-Potential rejection, while checking
   nonperiodic Potential/PBC, unchanged atom count and all source arrays,
   cell, PBC and info. No invalid finite configuration is required to propagate.

## Final validation after reconciliation

Python 3.12.14, ASE 3.29.0, abTEM 1.0.10, CPU, supplied virtual environment.
The full GUI and baseline group runs used Xvfb with local X11 socket access.

| Run | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `pytest` | 227 | 0 | 68 |
| `pytest --run-slow` | 280 | 0 | 15 |
| `xvfb-run -a pytest --run-slow --run-gui` | 294 | 0 | 1 |
| Original baseline files, slow + GUI | 68 | 0 | 1 |
| Independent QA geometry + pipeline, slow | 180 | 0 | 0 |
| Scientific resolution tests, slow | 46 | 0 | 0 |
| Focused pipeline + metadata + backend physics, slow | 39 | 0 | 0 |

The three added collected cases are two supported periodic QA cases and one
baseline unsupported-orientation regression. This explains the increase from
292 to 295 total cases. There are no xfails and no new skip conditions.

The only full-run skip is the existing CIF writer fixture (`test_import.py`):
its graphene fixture has a zero out-of-plane vector. Slow-only additionally
skips fourteen GUI tests; fast additionally skips fifty-three physics-marked tests.
No new skip or xfail policy was introduced. Warnings are principally existing
ASE/NumPy shape-setting deprecations.

## Independent validation evidence and limits

The retained QA checks still verify labelled scalene geometry for 43 matrices
across finite, slab and crystal PBC, direct abTEM TEM/diffraction equivalence,
Poisson means/variance/SNR and source immutability. Added tests independently
check actual prepared atoms against same-species ASE fractional-lattice sites,
integer cell replication, atom counts, positive handedness, unchanged slab
vacuum and explicit beam direction. Fixtures include a non-cubic orthorhombic
cell, tetragonal exact 3:4:5 rotations (including a change of beam), native MoS2,
and asymmetric finite particles at several rotations. Other added tests verify
engine-boundary rejection before Potential creation, actual output calibration,
annotation protection and input rejection before engine loading.

Supported direct-abTEM image oracles still pass after explicitly setting finite
Potential periodic=False. No scattering formula is reimplemented. The checks
establish agreement with this installed engine and geometric/counting oracles;
they are not universal validation of abTEM physics or every engine version.
Input atomic coordinates are still needed to reproduce a run. Metadata does
not serialize full specimen coordinates or guarantee identical images across
versions/devices. Frozen-phonon ensembles and other unsupported public inputs
are not added. Partial periodicity beyond aligned xy slabs remains unsupported.
