# Scientific QA resolution

Validated on 2026-10-08 using Python 3.12.14, ASE 3.29.0 and abTEM 1.0.10
on CPU. QA commit `493ddfb` was cherry-picked before production changes.
No original baseline or independent QA test was edited, skipped, weakened,
xfail-marked or removed. GUI, viewer and installer code are unchanged.

**Product limitation:** arbitrary periodic viewer orientations are not universally
supported. Simulation now stops before constructing a Potential when an exact
axis-aligned commensurate cell is unavailable within abTEM's bounded search.
Finite specimens retain arbitrary proper rotations when their box contains them.

**Review status:** the requested all-green baseline/QA outcome is not achieved.
Four unchanged QA tests and two unchanged baseline tests conflict with the adopted
scientific policy or backward-compatible metadata contract. They remain ordinary
failures for human review. This report does not certify those failures as passing.

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

## Validation results and visible review conflicts

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

The six visible failures requiring review are:

1. `test_sampling_metadata_matches_actual_abtem_grid`: asserts the legacy
   request field is the realized anisotropic spacing. The independent abTEM
   oracle correctly gives (1/3, 0.375) Å/pixel for the 16×18 Å / 48-point
   fixture. The new calibration and FOV checks verify those exact values.
   Another unchanged QA test, `test_metadata_cannot_overwrite_physical_provenance`,
   requires `sampling` to equal the scalar request 0.2 for this same fixture.
   Both contracts cannot hold simultaneously. Preserve the request field for
   legacy export and publish explicit actual calibration. The audit assertion
   is retained for human review.
2. `test_abtem_preparation_preserves_exact_periodic_geometry[si_bulk]`:
   unconditionally requires successful simulation of the inexact QA rotation.
   This does not permit the user's expressly authorized rejection policy C.
3. The same test for `[mos2_slab]`: likewise requires success for a tilted slab
   whose default preparation deforms geometry and can replicate vacuum.
4. `test_hidden_abtem_orthogonalization_is_recorded`: expects metadata from the
   same unsupported tilted Si request. There is now no simulation result to
   annotate. Successful native-slab and commensurate-replication preparation is
   recorded and independently checked in the resolution tests.
5. Baseline `test_image_metadata_schema`: requests tilted periodic Si at 10x/5y;
   the bounded unstrained cut is not axis aligned, so it is rejected instead of
   being strained. Its metadata assertions are left unchanged.
6. Baseline `test_anti_tiling_finite_particle`: its finite safe case succeeds;
   its deliberately forced rotated/skewed finite-box comparison is blocked.
   Keeping this deliberately tiled output would contradict the no-accidental-
   periodic-images requirement. Its border assertions are left unchanged.

This is a conflict between the stricter scientific product invariant and some
existing success-path fixtures, not evidence that the suite is green. Review
must decide the corresponding test contracts; this task does not rewrite them.

The only full-run skip is the existing CIF writer fixture (`test_import.py`):
its graphene fixture has a zero out-of-plane vector. Slow-only additionally
skips fourteen GUI tests; fast additionally skips fifty physics-marked tests.
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
