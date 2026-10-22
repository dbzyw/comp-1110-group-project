# Basketball shot model validation results - Tentative 3D supplied-component dataset

> Historical snapshot from before the NBA geometry/ball-parameter alignment.
> Its per-shot predictions and metrics have not been rerun for the current
> physics constants; the input axes, units, and assumed labels remain unverified.

- Input: `data_validation/valid_data_3D.csv` (35 records).
- Validation implementation: `validation.py` calling the existing `simulate_shot()` model; model constants were not tuned.
- Prediction target: binary made/miss agreement. Generic `made` labels do not invent a made-shot subtype.
- Data caveat: Rows 301-335 contain supplied position and velocity components. Positive source `x_m` was negated, `z_m` was tentatively mapped to release height, and `y_m` to lateral position. Labels, backspin, axes, origin, and velocity units remain unverified.

## Executive result

The model predicted **0 made** and **35 miss**. It agreed with 0/35 labels (**0.00%**, Wilson 95% CI **[0.00%, 9.89%]**). This is not an empirical model-performance estimate.

## Validation checks

| Check | Result |
|---|---|
| Required nine-column schema; 35 records | PASS |
| Unique shot IDs | PASS (301-335) |
| Physical fields finite and outcomes accepted | PASS |
| Simulation parameter errors | 0 |
| Outcome counts | 35 made / 0 miss |

## Binary metrics

| Metric | Result |
|---|---:|
| Agreement / accuracy | 0/35 = 0.00% |
| Wilson 95% CI | [0.00%, 9.89%] |
| Disagreement | 100.00% |
| Precision (made) | 0.00% |
| Recall / sensitivity (made) | 0.00% |
| Specificity | 0.00% |
| F1 (made) | 0.000 |
| Matthews correlation coefficient | 0.000 |
| Cohen's kappa | 0.000 |
| Chance agreement | 0.00% |
| No-information rate | 100.00% |

### Binary confusion matrix

| Actual \ Predicted | Made | Miss |
|---|---:|---:|
| Made | TP 0 | FN 35 |
| Miss | FP 0 | TN 0 |

## Four-class outcome results

Only **0/35** records enter the four-class matrix; generic `made` labels do not identify swish, rim-in, or board-in.

| Actual \ Predicted | swish | rim-in | board-in | miss |
|---|---:|---:|---:|---:|
| swish | 0 | 0 | 0 | 0 |
| rim-in | 0 | 0 | 0 | 0 |
| board-in | 0 | 0 | 0 | 0 |
| miss | 0 | 0 | 0 | 0 |

## Per-shot validation data

| ID | release_x | release_y | release_z | v0x | v0y | v0z | backspin | Actual | Predicted | Match |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 301 | -14.207000 | 2.534000 | 7.718000 | 0.500000 | 0.200000 | 0.500000 | 14.137167 | made | miss | no |
| 302 | -4.492000 | 2.559000 | 10.833000 | 1.550000 | 0.050000 | 1.525000 | 14.137167 | made | miss | no |
| 303 | -24.363000 | 2.640000 | 8.565000 | 1.750000 | 0.100000 | 5.275000 | 14.137167 | made | miss | no |
| 304 | -5.665000 | 2.505000 | 7.731000 | 1.175000 | 0.450000 | 0.121000 | 14.137167 | made | miss | no |
| 305 | -5.599000 | 2.593000 | 7.730000 | 2.800000 | 0.225000 | 0.131000 | 14.137167 | made | miss | no |
| 306 | -14.207000 | 2.534000 | 7.718000 | 0.400000 | 0.325000 | 4.350000 | 14.137167 | made | miss | no |
| 307 | -6.366000 | 2.495000 | 7.597000 | 2.800000 | 1.100000 | 1.875000 | 14.137167 | made | miss | no |
| 308 | -27.358000 | 2.525000 | 9.005000 | 1.900000 | 1.500000 | 4.275000 | 14.137167 | made | miss | no |
| 309 | -27.299000 | 2.518000 | 9.159000 | 1.175000 | 0.750000 | 1.650000 | 14.137167 | made | miss | no |
| 310 | -4.430000 | 2.498000 | 10.835000 | 1.275000 | 2.025000 | 3.425000 | 14.137167 | made | miss | no |
| 311 | -24.407000 | 2.496000 | 0.663000 | 4.275000 | 3.250000 | 3.500000 | 14.137167 | made | miss | no |
| 312 | -1.221000 | 2.528000 | 10.734000 | 0.325000 | 0.300000 | 2.775000 | 14.137167 | made | miss | no |
| 313 | -3.088000 | 2.500000 | 8.343000 | 3.000000 | 1.850000 | 3.575000 | 14.137167 | made | miss | no |
| 314 | -22.916000 | 2.501000 | 11.947000 | 4.800000 | 9.025000 | 3.500000 | 14.137167 | made | miss | no |
| 315 | -20.918000 | 2.520000 | 11.749000 | 0.775000 | 1.875000 | 2.950000 | 14.137167 | made | miss | no |
| 316 | -1.817000 | 2.488000 | 0.658000 | 0.450000 | 1.125000 | 2.375000 | 14.137167 | made | miss | no |
| 317 | -3.767000 | 2.467000 | 4.736000 | 1.025000 | 0.450000 | 2.500000 | 14.137167 | made | miss | no |
| 318 | -27.197000 | 2.519000 | 13.055000 | 1.000000 | 1.175000 | 3.925000 | 14.137167 | made | miss | no |
| 319 | -6.426000 | 2.466000 | 1.878000 | 0.300000 | 1.675000 | 1.650000 | 14.137167 | made | miss | no |
| 320 | -4.647000 | 2.502000 | 7.457000 | 1.475000 | 0.325000 | 5.250000 | 14.137167 | made | miss | no |
| 321 | -7.619000 | 2.491000 | 4.567000 | 1.050000 | 3.550000 | 4.300000 | 14.137167 | made | miss | no |
| 322 | -2.503000 | 2.485000 | 14.248000 | 0.150000 | 3.075000 | 1.950000 | 14.137167 | made | miss | no |
| 323 | -6.628000 | 2.470000 | 13.298000 | 1.750000 | 0.825000 | 2.975000 | 14.137167 | made | miss | no |
| 324 | -7.268000 | 2.482000 | 8.690000 | 1.150000 | 0.775000 | 2.900000 | 14.137167 | made | miss | no |
| 325 | -1.564000 | 2.494000 | 6.561000 | 3.000000 | 1.450000 | 4.375000 | 14.137167 | made | miss | no |
| 326 | -5.711000 | 2.462000 | 7.721000 | 0.550000 | 0.550000 | 2.200000 | 14.137167 | made | miss | no |
| 327 | -5.665000 | 2.505000 | 7.731000 | 1.175000 | 0.450000 | 3.025000 | 14.137167 | made | miss | no |
| 328 | -25.129000 | 2.486000 | 9.136000 | 1.125000 | 0.275000 | 4.925000 | 14.137167 | made | miss | no |
| 329 | -1.880000 | 2.496000 | 7.040000 | 1.700000 | 0.050000 | 1.325000 | 14.137167 | made | miss | no |
| 330 | -27.303000 | 2.473000 | 0.684000 | 0.100000 | 1.800000 | 4.125000 | 14.137167 | made | miss | no |
| 331 | -26.616000 | 2.464000 | 5.639000 | 0.375000 | 2.225000 | 2.425000 | 14.137167 | made | miss | no |
| 332 | -26.599000 | 2.523000 | 5.452000 | 0.525000 | 1.975000 | 1.325000 | 14.137167 | made | miss | no |
| 333 | -4.756000 | 2.534000 | 4.570000 | 0.975000 | 1.325000 | 3.200000 | 14.137167 | made | miss | no |
| 334 | -5.830000 | 2.521000 | 8.349000 | 0.450000 | 1.925000 | 2.925000 | 14.137167 | made | miss | no |
| 335 | -5.525000 | 2.518000 | 7.767000 | 3.900000 | 0.250000 | 5.825000 | 14.137167 | made | miss | no |
