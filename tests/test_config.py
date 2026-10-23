from pathlib import Path

import pytest
from pydantic import ValidationError

import blicket as bk
from blicket.config import check_tolerance
from tests.support import make_project


def test_defaults_and_values(tmp_path: Path) -> None:
    assert bk.load_config(make_project(tmp_path, {}, name="empty")) == bk.Config()
    assert bk.Config().blicks == ["blicks/**/*.py"]
    root = make_project(tmp_path, {}, 'blicks = ["views/*.py"]\ndigits = 8\nloader = "m:f"\n')
    config = bk.load_config(root)
    assert (config.blicks, config.digits, config.loader) == (["views/*.py"], 8, "m:f")


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ("blick = []", "unknown key 'blick' in [tool.blicket]; did you mean 'blicks'?"),
        ("zzz = 1", "unknown key 'zzz' in [tool.blicket]; valid keys: blicks"),
        ('blicks = "blicks/*.py"', "blicks must be a list of glob strings"),
        ('tolerance = "x"', "tolerance must be a number"),
        ("tolerance = -1e-5", "tolerance must be a positive number"),
        ("tolerance = nan", "tolerance must be a positive number"),
        ("digits = 1.5", "digits must be a whole number"),
        ('digits = "6"', "digits must be a whole number"),
        ('tolerance = "6"', "tolerance must be a number"),
        ("digits = 0", "digits must be between 1 and 17, got 0"),
        ("digits = 18", "digits must be between 1 and 17, got 18"),
        ("tolerance = 1e-9", "tolerance 1e-09 is finer than 6 significant digits can express"),
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
        bk.load_config(make_project(tmp_path, {}, "blick = 1\ndigits = 30\n"))
    assert "digits must be between" in str(info.value)
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


def test_tolerance_must_fit_digits() -> None:
    with pytest.raises(ValidationError, match="raise digits \\(now 6\\) to 8"):
        bk.Config(tolerance=1e-7)
    assert bk.Config(tolerance=1e-7, digits=8).tolerance == 1e-7
    assert bk.Config(tolerance=1.0, digits=1).digits == 1
    assert check_tolerance(1e-5, 6) is None  # the defaults sit exactly on the bound
    # No digits setting can express 1e-20, so the hint names only the tolerance.
    assert str(check_tolerance(1e-20, 6)).endswith("can express; use tolerance >= 1e-05")
