# The version comes from pyproject.toml; meson-python prefers it over project(version:).
project('blicket', meson_version: '>= 1.5')

py = import('python').find_installation(pure: true)

# Explicit file lists: install_subdir would also pick up nested __pycache__ and editor files.
# tests/test_packaging.py checks that every file under src/blicket is listed here.
py.install_sources(
  'src/blicket/__init__.py',
  'src/blicket/_validation.py',
  'src/blicket/assembly.py',
  'src/blicket/cli.py',
  'src/blicket/config.py',
  'src/blicket/definitions.py',
  'src/blicket/discovery.py',
  'src/blicket/errors.py',
  'src/blicket/model.py',
  'src/blicket/py.typed',
  subdir: 'blicket',
)

py.install_sources(
  'src/blicket/plots/__init__.py',
  'src/blicket/plots/_base.py',
  'src/blicket/plots/bar.py',
  'src/blicket/plots/line.py',
  'src/blicket/plots/stacked_area.py',
  subdir: 'blicket/plots',
)
