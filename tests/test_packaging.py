"""meson.build lists the package files one by one; a forgotten file would miss the wheel."""

import re
from pathlib import Path

REPOSITORY = Path(__file__).parent.parent
PACKAGE = REPOSITORY / "src" / "blicket"


def installed_sources() -> dict[str, str]:
    """Every file named in a ``py.install_sources`` call of meson.build, with its ``subdir``."""
    text = (REPOSITORY / "meson.build").read_text()
    listed: dict[str, str] = {}
    for call in re.findall(r"py\.install_sources\((.*?)\)", text, flags=re.DOTALL):
        subdir = re.search(r"subdir:\s*'([^']*)'", call)
        assert subdir is not None, f"install_sources without subdir: {call}"
        for file in re.findall(r"^\s*'([^']+)',", call, flags=re.MULTILINE):
            listed[file] = subdir.group(1)
    return listed


def test_every_package_file_is_listed_in_meson_build() -> None:
    listed = installed_sources()
    on_disk = {
        path.relative_to(REPOSITORY).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed")
    }
    assert "src/blicket/py.typed" in on_disk
    assert sorted(on_disk - set(listed)) == [], "add these files to meson.build"
    assert sorted(set(listed) - on_disk) == [], "meson.build lists missing files"
    for file, subdir in listed.items():
        expected = Path(file).parent.relative_to("src").as_posix()
        assert subdir == expected, f"{file} is installed into {subdir}, expected {expected}"
