"""The baseline of a build: the build it is compared with.

The candidates are the builds in the store of the build's run profile, except the build itself
and incomplete builds, the newest by ``created_at`` first. The baseline is the first candidate
whose commit is the tip or an ancestor of it in the git repository holding the Blicks; the tip is
the build's own commit, or the commit of a git ref. A candidate without a commit is never the
baseline. Candidates whose commits the clone lacks are skipped with a warning when a baseline is
found, and make the resolution fail when none is, since one of them may be it, as in a shallow
clone. A baseline can also be named directly, by its id in the store or its build directory.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from blicket import manifest
from blicket.errors import BlicketError
from blicket.manifest import Manifest
from blicket.store import Listing, Stored

FETCH_HINT = (
    "fetch the full history: git fetch --unshallow, or fetch-depth: 0 in GitHub Actions, or name "
    "the baseline: --against <id>"
)


@dataclass(frozen=True)
class Resolution:
    """The baseline found, or ``None`` and why there is none in ``reason``.

    ``failed`` when that is an error: the baseline named cannot be found or read, the build
    records no commit while builds of its profile were pushed, or no candidate is on the tip's
    history while the clone lacks the commits of some. ``warning`` names the candidates newer than
    the baseline found whose commits the clone lacks, which were skipped.
    """

    baseline: Stored | None
    reason: str = ""
    failed: bool = False
    warning: str = ""


def candidates(listing: Listing, built: Manifest) -> list[Stored]:
    """The builds of ``listing`` that may be the baseline of ``built``: those of its profile, but
    itself and the incomplete ones, the newest by ``created_at`` first."""
    return sorted(
        (
            stored
            for stored in listing.builds
            if stored.manifest.run.profile == built.run.profile
            and stored.id != built.build.id
            and not stored.manifest.build.incomplete
        ),
        key=lambda stored: (stored.manifest.created_at, stored.id),
        reverse=True,
    )


def resolve(
    listing: Listing, built: Manifest, root: Path, against: str | None = None
) -> Resolution:
    """The baseline of the build ``built`` of the project at ``root`` among the builds of
    ``listing``.

    ``against`` names the baseline as a build directory or the id of a build in ``listing``, of
    any profile, or names the git ref whose commit is the tip. Raises ``BlicketError`` when git
    cannot run or fails other than by answering no.
    """
    tip = built.repository.commit if built.repository is not None else None
    ref = None
    if against is not None:
        directory = Path(against)
        if (directory / manifest.MANIFEST).is_file():
            try:
                named = manifest.read(directory)
            except BlicketError as error:
                return Resolution(None, str(error), failed=True)
            return Resolution(Stored(named.build.id, directory.resolve(), named))
        if (stored := next((s for s in listing.builds if s.id == against), None)) is not None:
            return Resolution(stored)
        result = _git(root, "rev-parse", "--verify", "-q", f"{against}^{{commit}}")
        if result.returncode != 0:
            reason = f"{against} is neither a build directory, a build in the store, nor a git ref"
            if _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
                reason += (
                    f"; this clone is shallow, so a ref it did not fetch is missing: {FETCH_HINT}"
                )
            return Resolution(None, reason, failed=True)
        tip, ref = result.stdout.strip(), against

    profile = built.run.profile
    found = candidates(listing, built)
    if not found:
        reason = f"no other pushed build of profile {profile}"
        # With no candidate, every other build of the profile is incomplete.
        incomplete = sum(
            s.manifest.run.profile == profile and s.id != built.build.id for s in listing.builds
        )
        if incomplete:
            reason += f"; {incomplete} incomplete build{_plural(incomplete)} skipped"
        if listing.other_spec:
            reason += f"; {listing.other_spec} of another spec skipped"
        return Resolution(None, reason)
    if tip is None:
        ids = ", ".join(stored.id for stored in found[:5]) + (", …" if len(found) > 5 else "")
        which = "it" if len(found) == 1 else "one"
        reason = (
            f"the build records no git commit; {_builds(len(found), profile)}: {ids}; pass "
            f"{which} as --against"
        )
        return Resolution(None, reason, failed=True)
    where = f"{ref} ({tip[:7]})" if ref is not None else tip[:7]

    baseline = None
    unknown: list[tuple[str, str]] = []
    for stored in found:
        if (repository := stored.manifest.repository) is None:
            continue
        # cat-file -e exits 1 for an object the clone lacks.
        if _git(root, "cat-file", "-e", repository.commit).returncode != 0:
            unknown.append((stored.id, repository.commit))
        elif _git(root, "merge-base", "--is-ancestor", repository.commit, tip).returncode == 0:
            baseline = stored
            break
    if baseline is not None:
        warning = ""
        if unknown:
            one = len(unknown) == 1
            warning = (
                f"{len(unknown)} newer build{_plural(len(unknown))} at "
                f"{'a commit' if one else 'commits'} this clone lacks {'was' if one else 'were'} "
                f"skipped: {_named(unknown)}; {FETCH_HINT}"
            )
        return Resolution(baseline, warning=warning)
    if unknown:
        commits = "a commit" if len(unknown) == 1 else "commits"
        reason = (
            f"{_builds(len(unknown), profile)} at {commits} this clone lacks: {_named(unknown)}; "
            f"{FETCH_HINT}"
        )
        return Resolution(None, reason, failed=True)
    return Resolution(None, f"{_builds(len(found), profile)}, none at {where} or its ancestors")


def _plural(number: int) -> str:
    return "" if number == 1 else "s"


def _builds(number: int, profile: str) -> str:
    return f"{number} pushed build{_plural(number)} of profile {profile}"


def _named(builds: list[tuple[str, str]]) -> str:
    """The first five builds as ``<id> (<short commit>)``."""
    named = ", ".join(f"{build_id} ({commit[:7]})" for build_id, commit in builds[:5])
    return named + (", …" if len(builds) > 5 else "")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``root``; exit 0 and 1 are its answers, any other exit is git failing."""
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    except OSError as error:
        raise BlicketError(f"git cannot run ({error.strerror})") from error
    if result.returncode not in (0, 1):
        said = result.stderr.strip().splitlines()
        raise BlicketError(f"git {' '.join(args)} failed: {said[0] if said else result.returncode}")
    return result
