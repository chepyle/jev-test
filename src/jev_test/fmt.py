"""One rounding rule for every number shown in report.md, RESULTS.md, the Kev-suite tables and
report/findings.html.

Python's `round` and `format` round the binary value, so 0.8425 (stored as
0.84250000000000002665) prints as 0.843 while 84.25 rounds to 84.2, and the same accuracy
showed as 0.843 in one table and 84.2 in another. Here a value is rounded once, from the
shortest decimal that identifies the float (`repr`), half to even.
"""

from decimal import ROUND_HALF_EVEN, Decimal


def rnd(x: float, places: int) -> float:
    """Round `x` to `places` decimals, half to even, from its shortest decimal form."""
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), ROUND_HALF_EVEN))


def pct(x: float, places: int = 1) -> float:
    """A fraction as a percentage, rounded once (half to even)."""
    exact = Decimal(repr(float(x))).scaleb(2)
    return float(exact.quantize(Decimal(1).scaleb(-places), ROUND_HALF_EVEN))


def fixed(x: float, places: int, sign: bool = False) -> str:
    """`rnd` formatted with exactly `places` decimals (and a sign when asked)."""
    value = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), ROUND_HALF_EVEN)
    text = f"{value:.{places}f}"
    if text.startswith("-") and not x:
        text = text[1:]  # an exact -0.0 prints as 0.000; a small negative keeps its sign
    return f"+{text}" if sign and not text.startswith("-") else text
