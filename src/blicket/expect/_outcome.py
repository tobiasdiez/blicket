"""``Outcome``: what the evaluation of an expectation on a table gave."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# The results of an evaluation, the first three in the order of how bad they are; ``error`` says
# that the expectation could not be evaluated.
type Result = Literal["met", "warning", "failed", "error"]
_RANK = {"met": 0, "warning": 1, "failed": 2}


def rank(result: Result) -> int:
    """How bad a result other than ``error`` is: met 0, warning 1, failed 2."""
    return _RANK[result]


class Outcome(BaseModel):
    """What the evaluation of an expectation on a table gave.

    ``result`` is ``met`` when no row offends, ``warning`` when rows offend and the level is
    ``warn`` or all of them lie within ``warn_within``, ``failed`` when one offends beyond it at
    level ``error``, and ``error`` when the expectation could not be evaluated, which ``message``
    says why. ``expectation`` is the expectation in words, with the measure resolved.
    ``evaluated`` counts the rows a bound was applied to, those with a value, and is ``None`` for
    ``no_rows``; ``offending`` the rows that offend, ``within`` those of them inside
    ``warn_within``. ``worst`` is the value of the row with the largest distance and ``distance``
    that distance, both ``None`` when nothing ranks the rows; ``where`` the dimension values of
    that row, or of the first offending row, without the null ones.
    """

    model_config = ConfigDict(frozen=True)

    result: Result
    expectation: str
    evaluated: int | None = None
    offending: int = 0
    within: int = 0
    worst: float | None = None
    distance: float | None = None
    where: dict[str, Any] | None = None
    message: str | None = None

    @property
    def met(self) -> bool:
        return self.result == "met"

    @property
    def offends(self) -> bool:
        """Whether rows offend: the result is ``warning`` or ``failed``."""
        return self.result in ("warning", "failed")
