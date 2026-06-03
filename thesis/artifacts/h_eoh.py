"""
h_eoh — the fitness-best heuristic from EoH's final population.

This file is generated. Do not edit directly. Regenerate with:
    python -m thesis.code.incumbents --extract h_eoh

Provenance
----------
Source file  : examples/bp_online/results/pops/population_generation_10.json
Code hash    : 8ca83676ae76 (sha256, first 12 hex)
Objective    : 0.01207 (lower is better)

Reference pool (non-incumbent members of the final population):
        - 62a2846c597e  (objective 0.01308)
        - bea3036f5424  (objective 0.01449)
        - 47d987c33837  (objective 0.01912)

Algorithm description (from EoH's LLM at time of generation):
    This algorithm scores bins by combining best-fit, worst-fit, and harmonic divisibility potentials using a dual-sigmoid weighting scheme based on relative item size.
"""

import numpy as np

def score(item, bins):
    gamma = 4.0
    beta = 0.5
    delta = 6.0
    kappa = 15.0
    t1 = 0.33
    t2 = 0.66
    epsilon = 1e-9

    item_float = float(item)
    
    rem_space = bins - item_float
    
    potential_bf = np.exp(-gamma * np.power(rem_space, 2))
    potential_wf = 1.0 - np.exp(-beta * rem_space)
    
    divisibility_ratio = bins / (item_float + epsilon)
    cosine_term = (np.cos(2.0 * np.pi * divisibility_ratio) + 1.0) / 2.0
    potential_hd = np.power(cosine_term, delta)
    
    relative_fill = item_float / (bins + epsilon)
    
    sig1 = 1.0 / (1.0 + np.exp(-kappa * (relative_fill - t1)))
    sig2 = 1.0 / (1.0 + np.exp(-kappa * (relative_fill - t2)))
    
    w_bf_un = sig2
    w_wf_un = 1.0 - sig1
    w_hd_un = sig1 * (1.0 - sig2)
    
    total_weight = w_bf_un + w_wf_un + w_hd_un + epsilon
    
    weight_bf = w_bf_un / total_weight
    weight_wf = w_wf_un / total_weight
    weight_hd = w_hd_un / total_weight
    
    scores = weight_bf * potential_bf + weight_wf * potential_wf + weight_hd * potential_hd
    
    return scores
