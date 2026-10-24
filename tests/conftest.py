import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from blicket import definitions, viewer
from tests.support import PROJECTS, make_viewer


def _from(module: ModuleType, bases: tuple[Path, ...]) -> bool:
    file = getattr(module, "__file__", None)
    locations = [file] if isinstance(file, str) else list(getattr(module, "__path__", []))
    return any(Path(item).resolve().is_relative_to(base) for item in locations for base in bases)


@pytest.fixture(autouse=True)
def isolated_imports(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Restore ``sys.modules``, ``sys.path`` and blicket's records after each test.

    Only modules from the fixture projects and temporary directories are removed again: dropping
    a library module imported lazily during a test would give the next import a second copy.
    """
    modules = dict(sys.modules)
    path = list(sys.path)
    records = dict(definitions._records)
    yield
    bases = (PROJECTS.resolve(), tmp_path_factory.getbasetemp().resolve())
    # Decide first, delete afterwards: a namespace package's path needs its parent in place.
    added = [n for n, m in list(sys.modules.items()) if modules.get(n) is not m and _from(m, bases)]
    for name in added:
        del sys.modules[name]
    sys.path[:] = path  # only now: namespace paths recompute from sys.path when read
    for name, module in modules.items():
        sys.modules.setdefault(name, module)
    definitions._records.clear()
    definitions._records.update(records)


@pytest.fixture(autouse=True)
def installed_viewer(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The viewer of every test, named by ``BLICKET_VIEWER``; never the installation's own."""
    monkeypatch.setenv(viewer.VIEWER_ENV, str(make_viewer(tmp_path_factory.mktemp("viewer"))))
    monkeypatch.setattr(viewer, "_bundled", lambda: None)
