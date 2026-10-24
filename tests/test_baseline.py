"""Baseline resolution: candidates by profile and git ancestry, named baselines, and the reasons
why there is none."""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from blicket.baseline import FETCH_HINT, Resolution, resolve
from blicket.errors import BlicketError
from blicket.manifest import BuildConfig, BuildInfo, Manifest, Repository, Run
from blicket.store import Listing, Store
from tests.support import git

UNKNOWN = "f" * 40  # a commit no repository has


def commit(repository: Path, message: str) -> None:
    git(repository, "commit", "-q", "--allow-empty", "-m", message)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A git repository with the commits ``one`` and ``two`` on main and ``side`` on a branch
    from ``one``."""
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    commit(root, "one")
    git(root, "checkout", "-q", "-b", "side")
    commit(root, "side")
    git(root, "checkout", "-q", "main")
    commit(root, "two")
    return root


def head(repository: Path, ref: str) -> str:
    return git(repository, "rev-parse", ref).strip()


def made(
    number: int,
    sha: str | None,
    *,
    profile: str = "test",
    hour: int = 12,
    incomplete: bool = False,
) -> Manifest:
    """The manifest of a build with the id ``number`` at the commit ``sha``, made at ``hour``."""
    repository = None if sha is None else Repository(commit=sha, branch=None, dirty=False)
    return Manifest(
        blicket="0",
        created_at=datetime.fromisoformat(f"2026-10-24T{hour:02}:00:00Z"),
        build=BuildInfo(id=f"{number:016x}", incomplete=incomplete, loader_ms=0),
        config=BuildConfig(tolerance=1e-5),
        run=Run(id=f"run{number}", profile=profile, fingerprint="f", paths=[]),
        repository=repository,
        groups=(),
        blicks=(),
        problems=(),
    )


def stored(tmp_path: Path, *manifests: Manifest) -> Listing:
    """The listing of the store in ``tmp_path/store`` holding the manifests."""
    store = Store(tmp_path / "store")
    for built in manifests:
        directory = store.builds / built.build.id
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(built.model_dump_json())
    return store.list()


def found(listing: Listing, built: Manifest, root: Path, against: str | None = None) -> str | None:
    """The id of the baseline ``resolve`` finds."""
    resolution = resolve(listing, built, root, against)
    return resolution.baseline.id if resolution.baseline else None


def test_the_newest_build_on_the_history_of_the_tip_wins(tmp_path: Path, repository: Path) -> None:
    one, two, side = (head(repository, ref) for ref in ("main~1", "main", "side"))
    listing = stored(tmp_path, made(1, one, hour=1), made(2, two, hour=2), made(3, side, hour=3))
    assert found(listing, made(9, two), repository) == f"{2:016x}"
    assert found(listing, made(9, one), repository) == f"{1:016x}"
    assert found(listing, made(9, side), repository) == f"{3:016x}"


def test_older_builds_at_the_tip_lose_to_newer_ones_at_an_ancestor(
    tmp_path: Path, repository: Path
) -> None:
    one, two = head(repository, "main~1"), head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, one, hour=2))
    assert found(listing, made(9, two), repository) == f"{2:016x}"


def test_each_profile_resolves_its_own(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, two, profile="policy", hour=2))
    assert found(listing, made(9, two), repository) == f"{1:016x}"
    assert found(listing, made(9, two, profile="policy"), repository) == f"{2:016x}"


def test_the_current_build_is_not_its_own_baseline(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, two, hour=2))
    assert found(listing, made(2, two, hour=3), repository) == f"{1:016x}"


def test_incomplete_builds_are_skipped(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, two, hour=2, incomplete=True))
    assert found(listing, made(9, two), repository) == f"{1:016x}"


def test_builds_without_a_commit_are_skipped(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, None, hour=2))
    assert found(listing, made(9, two), repository) == f"{1:016x}"


def test_incomplete_builds_skipped_are_counted_in_the_reason(
    tmp_path: Path, repository: Path
) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, incomplete=True), made(9, two))
    assert resolve(listing, made(9, two), repository) == Resolution(
        None, "no other pushed build of profile test; 1 incomplete build skipped"
    )


def test_builds_off_the_history_are_no_baseline_and_no_error(
    tmp_path: Path, repository: Path
) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, head(repository, "side")))
    assert resolve(listing, made(9, two), repository) == Resolution(
        None, f"1 pushed build of profile test, none at {two[:7]} or its ancestors"
    )


def test_a_ref_without_builds_on_its_history_names_it(tmp_path: Path, repository: Path) -> None:
    side = head(repository, "side")
    listing = stored(tmp_path, made(1, side, hour=1), made(2, side, hour=2))
    assert resolve(listing, made(9, side), repository, "main") == Resolution(
        None,
        f"2 pushed builds of profile test, none at main ({head(repository, 'main')[:7]}) "
        "or its ancestors",
    )


def test_no_build_of_the_profile(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, profile="policy"))
    resolution = resolve(listing, made(9, two), repository)
    assert resolution == Resolution(None, "no other pushed build of profile test")


def test_an_empty_store_is_no_error(tmp_path: Path, repository: Path) -> None:
    listing = Store(tmp_path / "empty").list()
    resolution = resolve(listing, made(9, head(repository, "main")), repository)
    assert resolution == Resolution(None, "no other pushed build of profile test")


def test_against_a_build_in_the_store_of_any_profile(tmp_path: Path, repository: Path) -> None:
    one, two = head(repository, "main~1"), head(repository, "main")
    listing = stored(tmp_path, made(1, one, profile="policy"), made(2, two))
    assert found(listing, made(9, two), repository, f"{1:016x}") == f"{1:016x}"


def test_against_a_build_directory(tmp_path: Path, repository: Path) -> None:
    two = head(repository, "main")
    (built,) = stored(tmp_path, made(1, two)).builds
    resolution = resolve(
        Store(tmp_path / "empty").list(), made(9, two), repository, str(built.path)
    )
    assert resolution.baseline is not None
    assert (resolution.baseline.id, resolution.baseline.path) == (f"{1:016x}", built.path)


def test_against_a_ref_searches_its_history(tmp_path: Path, repository: Path) -> None:
    one, two, side = (head(repository, ref) for ref in ("main~1", "main", "side"))
    listing = stored(tmp_path, made(1, one, hour=1), made(2, two, hour=2), made(3, side, hour=3))
    assert found(listing, made(9, side), repository, "main") == f"{2:016x}"
    assert found(listing, made(9, two), repository, "side") == f"{3:016x}"
    assert found(listing, made(9, two), repository, "main~1") == f"{1:016x}"


def test_against_something_unknown_fails(tmp_path: Path, repository: Path) -> None:
    resolution = resolve(Store(tmp_path / "store").list(), made(9, None), repository, "nope")
    assert resolution == Resolution(
        None, "nope is neither a build directory, a build in the store, nor a git ref", True
    )


def test_a_build_without_a_commit_fails_and_names_the_candidates(
    tmp_path: Path, repository: Path
) -> None:
    listing = stored(tmp_path, made(1, None, hour=1), made(2, None, hour=2))
    assert resolve(listing, made(9, None), repository) == Resolution(
        None,
        f"the build records no git commit; 2 pushed builds of profile test: {2:016x}, {1:016x}; "
        "pass one as --against",
        True,
    )


def test_a_build_without_a_commit_takes_a_named_baseline(tmp_path: Path, repository: Path) -> None:
    listing = stored(tmp_path, made(1, None))
    assert found(listing, made(9, None), repository, f"{1:016x}") == f"{1:016x}"


def test_a_build_without_a_commit_and_no_candidate_is_no_error(
    tmp_path: Path, repository: Path
) -> None:
    resolution = resolve(Store(tmp_path / "empty").list(), made(9, None), repository)
    assert resolution == Resolution(None, "no other pushed build of profile test")


def test_commits_unknown_to_the_clone_fail_without_a_baseline(
    tmp_path: Path, repository: Path
) -> None:
    listing = stored(tmp_path, made(1, UNKNOWN, hour=1), made(2, UNKNOWN, hour=2))
    assert resolve(listing, made(9, head(repository, "main")), repository) == Resolution(
        None,
        f"2 pushed builds of profile test at commits this clone lacks: {2:016x} (fffffff), "
        f"{1:016x} (fffffff); {FETCH_HINT}",
        True,
    )


def test_unknown_commits_newer_than_the_baseline_are_a_warning(
    tmp_path: Path, repository: Path
) -> None:
    two = head(repository, "main")
    listing = stored(tmp_path, made(1, two, hour=1), made(2, UNKNOWN, hour=2))
    assert resolve(listing, made(9, two), repository) == Resolution(
        listing.builds[0],
        warning=f"1 newer build at a commit this clone lacks was skipped: {2:016x} (fffffff); "
        f"{FETCH_HINT}",
    )


def test_an_unknown_commit_older_than_the_baseline_does_not_matter(
    tmp_path: Path, repository: Path
) -> None:
    listing = stored(tmp_path, made(1, UNKNOWN, hour=1), made(2, head(repository, "main"), hour=2))
    assert found(listing, made(9, head(repository, "main")), repository) == f"{2:016x}"


def test_git_failing_otherwise_is_an_error(tmp_path: Path, repository: Path) -> None:
    listing = stored(tmp_path, made(1, "not-a-commit"))
    with pytest.raises(BlicketError, match=r"^git cat-file -e not-a-commit failed: fatal: "):
        resolve(listing, made(9, head(repository, "main")), repository)


@pytest.fixture
def clone(tmp_path: Path, repository: Path) -> Path:
    """A clone of ``repository`` with its last commit only."""
    clone = tmp_path / "clone"
    url = f"file://{repository}"
    subprocess.run(["git", "clone", "-q", "--depth", "1", url, clone], check=True)
    return clone


def test_a_shallow_clone_fails_with_the_hint(tmp_path: Path, repository: Path, clone: Path) -> None:
    one = head(repository, "main~1")
    listing = stored(tmp_path, made(1, one))
    assert resolve(listing, made(9, head(clone, "HEAD")), clone) == Resolution(
        None,
        f"1 pushed build of profile test at a commit this clone lacks: {1:016x} ({one[:7]}); "
        f"{FETCH_HINT}",
        True,
    )


def test_a_shallow_clone_fails_against_a_ref_too(
    tmp_path: Path, repository: Path, clone: Path
) -> None:
    listing = stored(tmp_path, made(1, head(repository, "side")))
    resolution = resolve(listing, made(9, head(clone, "HEAD")), clone, "origin/main")
    assert (resolution.baseline, resolution.failed) == (None, True)
    assert resolution.reason.endswith(
        f"at a commit this clone lacks: {1:016x} ({head(repository, 'side')[:7]}); {FETCH_HINT}"
    )


def test_a_ref_a_shallow_clone_did_not_fetch_gets_the_hint(tmp_path: Path, clone: Path) -> None:
    resolution = resolve(Store(tmp_path / "store").list(), made(9, None), clone, "side")
    assert resolution == Resolution(
        None,
        "side is neither a build directory, a build in the store, nor a git ref; this clone is "
        f"shallow, so a ref it did not fetch is missing: {FETCH_HINT}",
        True,
    )


def test_a_ref_outside_git_is_an_error_quoting_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(
        BlicketError, match=r"^git rev-parse .* failed: fatal: not a git repository"
    ):
        resolve(Store(tmp_path / "store").list(), made(9, None), tmp_path, "origin/main")


@pytest.mark.parametrize(
    ("text", "reason"),
    [("not json", "not valid JSON"), ('{"spec": "0.1"}', "is spec 0.1")],
)
def test_an_unreadable_named_directory_fails(
    tmp_path: Path, repository: Path, text: str, reason: str
) -> None:
    (tmp_path / "named").mkdir()
    (tmp_path / "named" / "manifest.json").write_text(text)
    listing = Store(tmp_path / "store").list()
    resolution = resolve(listing, made(9, None), repository, str(tmp_path / "named"))
    assert (resolution.baseline, resolution.failed) == (None, True)
    assert reason in resolution.reason


def test_builds_of_another_spec_are_counted_in_the_reason(tmp_path: Path, repository: Path) -> None:
    store = Store(tmp_path / "store")
    (store.builds / f"{2:016x}").mkdir(parents=True)
    (store.builds / f"{2:016x}" / "manifest.json").write_text('{"spec": "0.1"}')
    resolution = resolve(store.list(), made(9, head(repository, "main")), repository)
    assert resolution == Resolution(
        None, "no other pushed build of profile test; 1 of another spec skipped"
    )
