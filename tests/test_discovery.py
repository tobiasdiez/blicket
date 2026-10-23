"""Discovery: globbing, importing Blick modules, locating their errors, purging modules."""

import sys
from pathlib import Path

import pytest

import blicket as bk
from blicket.errors import SKIPPED
from tests.support import PROJECTS, discover_clean, make_project, one_blick


def decorated(name: str) -> str:
    """A Blick module with one decorated Blick, whose id derives from the group."""
    return (
        "import blicket as bk\n\n@bk.blick(plot=bk.plots.line(x='a', y='b'))\n"
        f"def {name}(run):\n    return run\n"
    )


def error_at(root: Path) -> tuple[str, str | None, str]:
    """The single error of a project: its kind, location and message."""
    (error,) = bk.discover(root).errors
    return error.kind, error.location(root), error.message


# ---------------------------------------------------------------------------------------------
# Blicks and groups


def test_module_source_and_description() -> None:
    blicks = bk.discover(PROJECTS / "minimal").blicks
    steel = blicks["flows/steel_by_process"]
    assert steel.module == "blicks.flows"
    assert steel.source == ((PROJECTS / "minimal" / "blicks" / "flows.py").resolve(), 6)
    assert steel.description == "Steel flows split by production process."
    # A family built in a loop keeps each loop variable.
    assert blicks["flows/slag"].transform("run") == ("run", "slag")


def test_nested_group_and_explicit_id_outside_it(tmp_path: Path) -> None:
    source = (
        "import blicket as bk\nbk.group('flows/steel', tags=['mfa'])\n"
        + decorated("production").partition("\n")[2]
        + "bk.register(id='steel/share', plot=bk.plots.line(x='a', y='b'), transform=len)\n"
    )
    registry = discover_clean(make_project(tmp_path, {"blicks/flows.py": source}))
    assert registry.blicks["flows/steel/production"].group == "flows/steel"
    assert registry.blicks["steel/share"].group == "flows/steel"
    assert registry.tags_of("steel/share") == ("mfa",)


def test_group_after_the_decorators(tmp_path: Path) -> None:
    source = decorated("in_use") + "bk.group('inventories')\n"
    assert list(discover_clean(make_project(tmp_path, {"blicks/stocks.py": source})).blicks) == [
        "inventories/in_use"
    ]


def test_group_from_init_modules(tmp_path: Path) -> None:
    files = {
        "blicks/__init__.py": decorated("overview"),
        "blicks/stocks/__init__.py": decorated("total"),
        "blicks/stocks/detail.py": decorated("by_region"),
    }
    registry = discover_clean(make_project(tmp_path, files))
    assert {blick.id: blick.module for blick in registry.blicks.values()} == {
        "blicks/overview": "blicks",
        "stocks/total": "blicks.stocks",
        "detail/by_region": "blicks.stocks.detail",
    }


def test_families_through_helpers_and_project_package(tmp_path: Path) -> None:
    family = (
        "import blicket as bk\n\ndef family(prefix, names):\n    for name in names:\n"
        "        bk.register(id=f'{prefix}/{bk.slug(name)}', plot=bk.plots.line(x='a', y='b'),\n"
        "                    transform=lambda run, n=name: (run, n))\n"
    )
    files = {
        "blicks/_helpers.py": family,
        "famproject/__init__.py": "",
        "famproject/factory.py": family,
        "blicks/families.py": (
            "from blicks._helpers import family\nimport famproject.factory\n\n"
            "family('materials', ['Steel'])\n"
            "famproject.factory.family('regions', ['Rest of World'])\n"
        ),
    }
    registry = discover_clean(make_project(tmp_path, files))
    assert set(registry.groups) == {"families"}  # _helpers.py is no Blick module
    for blick_id in ["materials/steel", "regions/rest-of-world"]:
        blick = registry.blicks[blick_id]
        assert (blick.module, blick.group) == ("blicks.families", "families")
        assert blick.source is not None
        assert blick.source.file.name == "families.py"


def test_imported_blick_module_keeps_its_blicks(tmp_path: Path) -> None:
    # combined.py imports parts.py, which sorts after it, while it executes.
    files = {
        "blicks/combined.py": "import blicks.parts  # noqa: F401\n" + one_blick("combined/x"),
        "blicks/parts.py": one_blick("parts/y"),
    }
    registry = discover_clean(make_project(tmp_path, files))
    assert registry.blicks["parts/y"].module == "blicks.parts"
    assert registry.blicks["combined/x"].module == "blicks.combined"


def test_invalid_definitions_are_recorded_during_discovery(tmp_path: Path) -> None:
    source = """
        import blicket as bk

        @bk.blick(plot=bk.plots.line(x="year", y="value"), controls={"r": "facet"})
        def steel(run):
            return run

        @bk.blick(plot=bk.plots.line(x="year", y="value"))
        def fine(run):
            return run
    """
    registry = bk.discover(make_project(tmp_path, {"blicks/flows.py": source}))
    assert (registry.errors, list(registry.blicks)) == ((), ["flows/fine"])
    (steel,) = registry.failed
    assert (steel.id, steel.source and steel.source.line) == ("flows/steel", 4)


# ---------------------------------------------------------------------------------------------
# Errors while Blick modules execute


def test_broken_module_is_captured(tmp_path: Path) -> None:
    files = {"blicks/broken.py": "import nothere\n", "blicks/ok.py": one_blick("ok/x")}
    root = make_project(tmp_path, files)
    registry = bk.discover(root)
    (error,) = registry.errors
    assert (error.kind, error.location(root), error.module) == (
        "import",
        "blicks/broken.py:1",
        "blicks.broken",
    )
    assert error.message.splitlines() == [
        "ModuleNotFoundError: No module named 'nothere'",
        f"is 'nothere' installed in {sys.prefix}?",
        SKIPPED,
    ]
    assert error.traceback is not None
    assert "importlib" not in error.traceback
    assert list(registry.blicks) == ["ok/x"]
    assert registry.incomplete


def test_syntax_error_from_inside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_project(tmp_path, {"blicks/a.py": "x = 1\ndef broken(:\n"})
    monkeypatch.chdir(root)
    (error,) = bk.discover(root).errors
    assert (error.location(root), error.traceback) == ("blicks/a.py:2", None)


@pytest.mark.parametrize(
    ("source", "kind", "location", "phrase"),
    [
        ("import sys\nsys.exit(3)\n", "import", "blicks/flows.py:2", "SystemExit: 3"),
        (
            "import blicket as bk\nbk.plots.line(x='y', y='v', color='y')\n",
            "invalid_definition",
            "blicks/flows.py:2",
            "column 'y' is bound to both 'x' and 'color'",
        ),
        (
            "import blicket as bk\n@bk.blick\ndef f(run): ...\n",
            "invalid_definition",
            "blicks/flows.py:2",
            "with parentheses",
        ),
        (
            "import blicket as bk\nbk.group(title='')\n",
            "group",
            "blicks/flows.py:2",
            "needs the group name",
        ),
        (
            "import blicket as bk\nbk.group('Bad Group')\n",
            "group",
            "blicks/flows.py:2",
            "is not valid",
        ),
    ],
)
def test_file_level_errors(
    tmp_path: Path, source: str, kind: str, location: str, phrase: str
) -> None:
    found_kind, found_location, message = error_at(
        make_project(tmp_path, {"blicks/flows.py": source})
    )
    assert (found_kind, found_location) == (kind, location)
    assert phrase in message
    assert message.endswith(SKIPPED)


def test_error_raised_in_a_helper(tmp_path: Path) -> None:
    files = {
        "blicks/_helpers.py": "import blicket as bk\n\ndef bad():\n    return bk.slug('!!')\n",
        "blicks/flows.py": "from blicks._helpers import bad\n\nbad()\n",
    }
    _, location, message = error_at(make_project(tmp_path, files))
    assert location == "blicks/flows.py:3"
    assert "(raised at blicks/_helpers.py:4)" in message


def test_package_init_raising_is_reported_once(tmp_path: Path) -> None:
    files = {
        "blicks/__init__.py": "VALUE = 1\nraise RuntimeError('init broke')\n",
        "blicks/flows.py": one_blick("flows/x"),
        "blicks/stocks.py": one_blick("stocks/x"),
    }
    _, location, message = error_at(make_project(tmp_path, files))
    assert location == "blicks/__init__.py:2"
    assert message.startswith("RuntimeError: init broke")


# ---------------------------------------------------------------------------------------------
# Files and globs


def test_bad_file_names(tmp_path: Path) -> None:
    files = {"__init__.py": "", "blicks/steel-flows.py": "", "blicks/ok.py": one_blick("ok/x")}
    root = make_project(tmp_path, files, 'blicks = ["*.py", "blicks/*.py"]\n')
    registry = bk.discover(root)
    assert [(e.kind, e.location(root)) for e in registry.errors] == [
        ("bad_filename", "__init__.py"),
        ("bad_filename", "blicks/steel-flows.py"),
    ]
    assert "rename it to 'steel_flows'" in registry.errors[1].message
    assert list(registry.blicks) == ["ok/x"]


@pytest.mark.parametrize(
    ("files", "config", "phrase"),
    [
        ({}, "", 'blicks = ["blicks/**/*.py"] (the default) matches no files'),
        (
            {"views/_helpers.py": ""},
            'blicks = ["views/**/*.py"]\n',
            "files starting with '_' are helpers",
        ),
    ],
)
def test_zero_matches_is_an_error(
    tmp_path: Path, files: dict[str, str], config: str, phrase: str
) -> None:
    kind, location, message = error_at(make_project(tmp_path, files, config))
    assert (kind, location) == ("no_match", "pyproject.toml")
    assert phrase in message


def test_name_clash_with_a_shadowing_package() -> None:
    sys.path.append(str(PROJECTS / "name_clash" / "shadow"))
    root = PROJECTS / "name_clash" / "project"
    kind, location, message = error_at(root)
    assert (kind, location) == ("name_clash", "blicks")
    assert str((PROJECTS / "name_clash" / "shadow" / "blicks").resolve()) in message
    assert "add blicks/__init__.py or rename the blicks directory" in message


def test_package_and_module_of_one_name(tmp_path: Path) -> None:
    files = {"blicks/flows.py": one_blick("f/m"), "blicks/flows/__init__.py": one_blick("f/p")}
    root = make_project(tmp_path, files)
    registry = bk.discover(root)
    (error,) = registry.errors
    assert (error.kind, error.location(root)) == ("name_clash", "blicks/flows.py")
    assert "rename one of them" in error.message
    assert list(registry.blicks) == ["f/p"]


def test_helpers_and_hidden_files_are_skipped(tmp_path: Path) -> None:
    files = ["blicks/_helper.py", "blicks/.hidden/x.py", "blicks/b/z.py", "blicks/a.py"]
    root = make_project(tmp_path, {path: one_blick(f"t/{Path(path).stem}") for path in files})
    # POSIX-sorted: blicks/a.py before blicks/b/z.py.
    assert list(discover_clean(root).blicks) == ["t/a", "t/z"]


def test_files_outside_the_root_and_explicit_config(tmp_path: Path) -> None:
    make_project(tmp_path, {"blicks/x.py": one_blick("x/x")}, name="other")
    root = make_project(tmp_path, {"blicks/y.py": one_blick("y/y"), "blicks/z.py": ""})
    registry = bk.discover(root, bk.Config(blicks=["../other/blicks/*.py", "blicks/y.py"]))
    assert [error.kind for error in registry.errors] == ["bad_filename"]
    assert "outside the project root" in registry.errors[0].message
    assert list(registry.blicks) == ["y/y"]


# ---------------------------------------------------------------------------------------------
# Imports, processes and the purge


def test_project_root_goes_first_on_sys_path() -> None:
    root = str((PROJECTS / "minimal").resolve())
    sys.path.append(root)
    bk.discover(PROJECTS / "minimal")
    assert (sys.path[0], sys.path.count(root)) == (root, 1)


def test_module_imported_before_discovery_is_not_lost() -> None:
    sys.path.insert(0, str(PROJECTS / "minimal"))
    __import__("blicks.flows")
    assert "flows/steel_by_process" in bk.discover(PROJECTS / "minimal").blicks


def test_two_projects_in_one_process(tmp_path: Path) -> None:
    # Both have a module blicks.flows; the second run of minimal executes it afresh.
    minimal = discover_clean(PROJECTS / "minimal")
    other = discover_clean(make_project(tmp_path, {"blicks/flows.py": one_blick("other/x")}))
    assert list(other.blicks) == ["other/x"]
    assert list(discover_clean(PROJECTS / "minimal").blicks) == list(minimal.blicks)


def test_changed_file_is_picked_up(tmp_path: Path) -> None:
    root = make_project(tmp_path, {"blicks/stocks.py": one_blick("stocks/old")})
    assert list(bk.discover(root).blicks) == ["stocks/old"]
    (root / "blicks" / "stocks.py").write_text(one_blick("stocks/renamed"))
    assert list(bk.discover(root).blicks) == ["stocks/renamed"]


def test_standard_library_modules_are_never_dropped(tmp_path: Path) -> None:
    import colorsys

    files = {"colorsys.py": one_blick("shadow/colorsys")}
    registry = bk.discover(make_project(tmp_path, files, 'blicks = ["*.py"]\n'))
    assert sys.modules["colorsys"] is colorsys
    assert [error.kind for error in registry.errors] == ["name_clash"]
