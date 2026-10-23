"""blicket: Storybook for scientific model outputs.

Blick modules use this package as ``import blicket as bk``::

    bk.group("flows", title="Material flows", tags=["mfa"])

    @bk.blick(title="Steel flows", plot=bk.plots.stacked_area(x="year", y="value", color="process"))
    def steel_by_process(run): ...
"""

from blicket import plots
from blicket.config import Config, find_project_root, load_config
from blicket.definitions import blick, group, register, slug
from blicket.discovery import discover
from blicket.errors import ConfigError, DefinitionError, Problem
from blicket.model import Blick, FailedBlick, Group, Registry
from blicket.plots import Channel, PlotSpec, PlotType

__all__ = [
    "Blick",
    "Channel",
    "Config",
    "ConfigError",
    "DefinitionError",
    "FailedBlick",
    "Group",
    "PlotSpec",
    "PlotType",
    "Problem",
    "Registry",
    "blick",
    "discover",
    "find_project_root",
    "group",
    "load_config",
    "plots",
    "register",
    "slug",
]
