"""Generate the viewer into a directory, for meson's viewer target.

``python generate.py PNPM VIEWER_DIR OUTPUT_DIR`` installs the locked dependencies, generates the
static site and copies it to ``OUTPUT_DIR``.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def main(pnpm: str, source: Path, output: Path) -> None:
    subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=source, check=True)
    subprocess.run([pnpm, "generate"], cwd=source, check=True)
    shutil.rmtree(output, ignore_errors=True)
    shutil.copytree(source / ".output" / "public", output)


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
