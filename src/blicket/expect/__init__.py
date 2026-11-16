"""Expectations on a table, ``bk.expect``: properties a Blick's or a check's table must have.

An expectation says which rows of a table offend, and by how much, their distance. ``no_rows`` lets
no row offend: without a function every row of the table offends, which is what a check returns;
with one, the function picks the offending rows. ``at_most``, ``at_least`` and ``between`` bound a
measure, the bounds included, and a row offends by as much as its value lies outside; a null value
never offends. ``warn_within`` makes a row whose distance is at most that a warning rather than a
failure.

``on=`` and ``by=`` name the measure; left out, it is the table's only measure. A bound on a table
of several measures needs ``on=``; ``no_rows`` with several and no ``by=`` ranks nothing.

A table without rows meets every expectation. The column ``on=`` or ``by=`` names must still be
one of its columns, when it has any, whatever their roles; a ``rows`` function is not called, and
nothing is looked up for it.

A build evaluates the expectations and records each ``Outcome``; there is no other way to run them.
"""

from blicket.expect._outcome import Outcome
from blicket.expect._vocabulary import Expectation, at_least, at_most, between, no_rows

__all__ = ["Expectation", "Outcome", "at_least", "at_most", "between", "no_rows"]
