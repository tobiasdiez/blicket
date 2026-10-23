"""blicket: Storybook for scientific model outputs.

Blick modules use this package as ``import blicket as bk``::

    bk.group("flows", title="Material flows", tags=["mfa"])

    @bk.blick(title="Steel flows", plot=bk.plots.stacked_area(x="year", y="value", color="process"))
    def steel_by_process(run): ...
"""

from blicket import plots
from blicket.builder import Build, NothingToBuild, build
from blicket.config import Config, find_project_root, load_config
from blicket.definitions import blick, group, register, slug
from blicket.discovery import discover
from blicket.errors import BlicketError, ConfigError, DefinitionError, LoaderError, Problem
from blicket.loader import RunSelection, fingerprint
from blicket.manifest import Manifest, RunInfo
from blicket.model import Blick, BlickEntry, Group, Registry
from blicket.plots import Channel, PlotSpec, PlotType

__all__ = [
    "Blick",
    "BlickEntry",
    "BlicketError",
    "Build",
    "Channel",
    "Config",
    "ConfigError",
    "DefinitionError",
    "Group",
    "LoaderError",
    "Manifest",
    "NothingToBuild",
    "PlotSpec",
    "PlotType",
    "Problem",
    "Registry",
    "RunInfo",
    "RunSelection",
    "blick",
    "build",
    "discover",
    "find_project_root",
    "fingerprint",
    "group",
    "load_config",
    "plots",
    "register",
    "slug",
]
