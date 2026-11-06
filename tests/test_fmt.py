from jev_test.fmt import fixed, pct, rnd


def test_exact_halves_round_to_even_in_every_scale():
    assert rnd(0.8425, 3) == 0.842  # binary 0.8425 is slightly above the half
    assert pct(0.8425) == 84.2
    assert fixed(-0.0075, 3, sign=True) == "-0.008"
    assert pct(-0.0075) == -0.8
    assert pct(0.7605) == 76.0
    assert pct(0.713486) == 71.3  # one rounding, not 71.35 -> 71.4


def test_fixed_signs():
    assert fixed(0.0004, 3, sign=True) == "+0.000"
    assert fixed(-0.0004, 3) == "-0.000"  # below zero, shown as such
    assert fixed(-0.0, 3) == "0.000"
    assert fixed(0.0125, 3, sign=True) == "+0.012"
