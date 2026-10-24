from pathlib import Path

import pytest

import blicket as bk
from tests.support import make_project


def test_defaults_and_values(tmp_path: Path) -> None:
    assert bk.load_config(make_project(tmp_path, {}, name="empty")) == bk.Config()
    assert bk.Config().blicks == ["blicks/**/*.py"]
    lines = 'blicks = ["views/*.py"]\ntolerance = 1e-9\nloader = "m.n:C.f"\n'
    config = bk.load_config(make_project(tmp_path, {}, lines))
    assert (config.blicks, config.tolerance, config.loader) == (["views/*.py"], 1e-9, "m.n:C.f")


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ("blick = []", "unknown key 'blick' in [tool.blicket]; did you mean 'blicks'?"),
        ("zzz = 1", "unknown key 'zzz' in [tool.blicket]; valid keys: blicks"),
        ('blicks = "blicks/*.py"', "blicks must be a list of glob strings"),
        ('tolerance = "x"', "tolerance must be a number"),
        ("tolerance = -1e-5", "tolerance must be a positive number below 1, got -1e-05"),
        ("tolerance = nan", "tolerance must be a positive number below 1"),
        ("tolerance = 1.0", "tolerance must be a positive number below 1, got 1.0"),
        ('tolerance = "6"', "tolerance must be a number"),
        ("digits = 6", "unknown key 'digits' in [tool.blicket]; valid keys: blicks"),
        ('loader = "mymodel.load_run"', 'loader must be "package.module:function", got \'mymodel'),
        ('loader = "a b:c"', "loader must be \"package.module:function\", got 'a b:c'"),
        ("loader = 1", 'loader must be a string "package.module:function"'),
        ("[tool.blicket", "invalid TOML"),
    ],
)
def test_invalid_config(tmp_path: Path, lines: str, expected: str) -> None:
    root = make_project(tmp_path, {}, lines + "\n")
    with pytest.raises(bk.ConfigError) as info:
        bk.load_config(root)
    assert str(info.value).startswith(f"{root / 'pyproject.toml'}: ")
    assert expected in str(info.value)


def test_every_config_problem_is_reported(tmp_path: Path) -> None:
    with pytest.raises(bk.ConfigError) as info:
        bk.load_config(make_project(tmp_path, {}, "blick = 1\ntolerance = 2\n"))
    assert "tolerance must be a positive number below 1" in str(info.value)
    assert "unknown key 'blick'" in str(info.value)


def test_missing_section_and_pyproject(tmp_path: Path) -> None:
    with pytest.raises(bk.ConfigError, match=r"has no pyproject\.toml"):
        bk.load_config(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    with pytest.raises(bk.ConfigError, match=r"no \[tool.blicket\] section"):
        bk.load_config(tmp_path)


def test_root_found_by_walking_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The pyproject.toml without the section on the way up is skipped.
    root = make_project(tmp_path, {"inner/pyproject.toml": '[project]\nname = "x"\n'})
    start = root / "inner" / "deep"
    start.mkdir()
    assert bk.find_project_root(start) == root.resolve()
    monkeypatch.chdir(start)
    assert bk.find_project_root() == root.resolve()


def test_no_root(tmp_path: Path) -> None:
    with pytest.raises(bk.ConfigError, match="pass --project"):
        bk.find_project_root(tmp_path)
