# Chapter 4 §4.5.3 — Three-way decomposition analysis
Design doc: `thesis/writing/chapter4_comparative_decomposition_design.md`

## Per-cell Δ_step distribution
| Cell | n | mean | median | p25 | p75 | IQR | trim10 | positive_tail | cat_-50 | cat_-100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full (ch5 stratified_representative L1 k=4) | 60 | -30.389 | 0.000 | -4.458 | 2.967 | 7.425 | -7.490 | 0.350 | 0.133 | 0.117 |
| gap-only (E2) | 59 | -238.932 | -13.400 | -126.800 | -3.950 | 122.850 | -118.478 | 0.153 | 0.322 | 0.254 |
| no-reference (E1) | 56 | -329.326 | -47.417 | -180.233 | -10.200 | 170.033 | -209.630 | 0.089 | 0.446 | 0.375 |

## Matched-pair Δ_step (paired difference)
| Contrast | n_paired | mean_diff | mean CI 95 | median_diff | median CI 95 | excludes_zero (mean) |
|---|---:|---:|---|---:|---|---|
| full vs gap-only | 59 | +207.947 | [+85.255, +351.974] | +13.100 | [+7.167, +18.167] | True |
| gap-only vs no-reference | 56 | +78.632 | [-116.615, +279.660] | +11.567 | [-0.567, +28.750] | False |
| full vs no-reference | 56 | +296.938 | [+150.778, +463.238] | +33.200 | [+13.400, +88.733] | True |

## Cliff's δ on Δ_step distributions
| Contrast | Cliff's δ |
|---|---:|
| full vs gap-only | +0.459 |
| gap-only vs no-reference | +0.229 |
| full vs no-reference | +0.605 |

## Argmax-equivalence rate per cell
| Cell | n_ok | argmax_equivalent | rate |
|---|---:|---:|---:|
| full | 60 | 0 | 0.000 |
| gap-only | 59 | 0 | 0.000 |
| no-reference | 56 | 0 | 0.000 |

## Proposal-hash overlap across cells
| Contrast | distinct A | distinct B | overlap | Jaccard |
|---|---:|---:|---:|---:|
| full vs gap-only | 45 | 57 | 1 | 0.010 |
| gap-only vs no-reference | 57 | 56 | 0 | 0.000 |
| full vs no-reference | 45 | 56 | 0 | 0.000 |

## Regime classification (design doc §7)
**B_code_matters**
