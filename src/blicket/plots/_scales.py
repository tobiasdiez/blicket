"""Axis scales: how the axis of a channel maps values to positions."""

from typing import Literal, get_args

# ``linear`` is every axis's default.
Scale = Literal["linear", "log"]
SCALES: tuple[Scale, ...] = get_args(Scale)
