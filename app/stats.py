"""Experiment statistics shared by the notebooks and the app."""
import math

from scipy.stats import chi2, norm


def n_per_arm(baseline, relative_mde, alpha=0.05, power=0.8):
    """Users per arm for a two-sided two-proportion z-test (pooled variance under H0)."""
    p1 = baseline
    p2 = baseline * (1 + relative_mde)
    if not 0 < p1 < 1 or not 0 < p2 < 1:
        raise ValueError('Rates must be between 0 and 1')
    z_a = norm.ppf(1 - alpha / 2)
    z_b = norm.ppf(power)
    p_bar = (p1 + p2) / 2
    n = (z_a * math.sqrt(2 * p_bar * (1 - p_bar)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p2 - p1) ** 2
    return math.ceil(n)


def weeks_needed(n_arm, weekly_users, arms=2, min_weeks=2):
    """Full weeks to enrol n_arm users in every arm, never fewer than min_weeks."""
    return max(min_weeks, math.ceil(n_arm * arms / weekly_users))


def srm_check(observed, expected_shares=None, threshold=0.001):
    """Chi-square sample-ratio-mismatch test. Returns (p_value, mismatch)."""
    total = sum(observed)
    shares = expected_shares or [1 / len(observed)] * len(observed)
    expected = [total * s for s in shares]
    stat = sum((o - e) ** 2 / e for o, e in zip(observed, expected))
    p_value = float(chi2.sf(stat, len(observed) - 1))
    return p_value, p_value < threshold


def proportion_ci(successes, n, z=1.96):
    """Rate and normal-approximation 95% margin of error."""
    p = successes / n
    return p, z * math.sqrt(p * (1 - p) / n)


if __name__ == '__main__':
    # Textbook check: 10% -> 12% needs about 3,840 per arm at alpha 0.05, power 0.8.
    assert 3800 < n_per_arm(0.10, 0.20) < 3900
    assert srm_check([5000, 5000])[1] is False and srm_check([5000, 5400])[1] is True
    print('ok')
