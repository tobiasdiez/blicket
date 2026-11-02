"""blicket: Storybook for scientific model outputs.

Blick modules use this package as ``import blicket as bk``::

    bk.group("flows", title="Material flows", tags=["mfa"])

    @bk.blick(title="Steel flows", plot=bk.plots.stacked_area(x="year", y="value", color="process"))
    def steel_by_process(run): ...
"""

from blicket import plots
from blicket.builder import Build, NothingToBuild, build
from blicket.comparison import Comparison
from blicket.config import Config, find_project_root, load_config
from blicket.dataset import Dataset, Frames, Quantity
from blicket.definitions import blick, group, register, slug
from blicket.discovery import discover
from blicket.errors import BlicketError, ConfigError, DefinitionError, LoaderError, Problem, Skip
from blicket.loader import RunSelection, fingerprint
from blicket.manifest import Manifest, RunInfo
from blicket.model import Blick, BlickEntry, Group, Registry
from blicket.plots import Channel, PlotSpec, PlotType
from blicket.schema import Change, Control, Dimension

__all__ = [
    "Blick",
    "BlickEntry",
    "BlicketError",
    "Build",
    "Change",
    "Channel",
    "Comparison",
    "Config",
    "ConfigError",
    "Control",
    "Dataset",
    "DefinitionError",
    "Dimension",
    "Frames",
    "Group",
    "LoaderError",
    "Manifest",
    "NothingToBuild",
    "PlotSpec",
    "PlotType",
    "Problem",
    "Quantity",
    "Registry",
    "RunInfo",
    "RunSelection",
    "Skip",
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
