import numpy as np

def score(item, bins):
    remainder = bins - item
    utilization_score = item / bins
    small_remainder_incentive = 1.0 / (1.0 + remainder / item)
    steepness_multiple = 20.0
    multiplicity_bonus = np.exp(
        -steepness_multiple * (np.round(remainder / item) - remainder / item) ** 2
    )
    fragment_penalty_term = np.where(
        (remainder > 0) & (remainder < item),
        (1.0 - (remainder / item)) ** 4,
        0.0,
    )
    fragment_penalty_magnitude = 3.1
    combined_score_for_non_perfect_fits = (
        utilization_score
        + 0.5 * small_remainder_incentive
        + 1.15 * multiplicity_bonus
        - fragment_penalty_magnitude * fragment_penalty_term
    )
    scores = np.where(remainder == 0, np.inf, combined_score_for_non_perfect_fits)
    return scores
