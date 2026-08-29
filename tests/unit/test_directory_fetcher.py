import pytest

from golemcpp.golem import helpers
from golemcpp.golem.directory_fetcher import DirectoryFetcher
from golemcpp.golem.directory_fetcher import ORIGIN_FILENAME
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.source import Source


@pytest.fixture
def git_calls(monkeypatch):
    """Every git invocation, so a copied source can be shown to make none."""
    calls = []
    monkeypatch.setattr(
        helpers, "run_git", lambda args, cwd=None, quiet=False: calls.append(args)
    )
    return calls


def make_fetcher(origin, destination):
    return DirectoryFetcher(
        str(destination), Source.for_directory(origin.resolve().as_uri()), FetchPolicy()
    )


def test_populate_copies_the_directory_and_records_its_origin(tmp_path, git_calls):
    origin = tmp_path / "mylib"
    origin.mkdir()
    (origin / "marker.txt").write_text("copied\n", encoding="utf-8")
    destination = tmp_path / "cache" / "mylib"

    result = make_fetcher(origin, destination).populate()

    assert (destination / "marker.txt").read_text(encoding="utf-8") == "copied\n"
    assert (destination / ORIGIN_FILENAME).read_text(
        encoding="utf-8"
    ) == origin.resolve().as_uri()
    # A copied source has no remote to talk to and no commit to name.
    assert git_calls == []
    assert result == Fetched()


def test_refresh_recopies_the_directory(tmp_path, git_calls):
    # Nothing distinguishes a fresh copy from a later one: both replace what is
    # there with what the source holds now.
    origin = tmp_path / "mylib"
    origin.mkdir()
    (origin / "marker.txt").write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "cache" / "mylib"
    destination.mkdir(parents=True)
    (destination / "marker.txt").write_text("stale\n", encoding="utf-8")

    make_fetcher(origin, destination).refresh()

    assert (destination / "marker.txt").read_text(encoding="utf-8") == "fresh\n"
    assert git_calls == []


def test_what_the_source_no_longer_holds_does_not_survive_a_recopy(tmp_path, git_calls):
    origin = tmp_path / "mylib"
    origin.mkdir()
    (origin / "kept.txt").write_text("kept\n", encoding="utf-8")
    destination = tmp_path / "cache" / "mylib"
    destination.mkdir(parents=True)
    (destination / "gone.txt").write_text("removed upstream\n", encoding="utf-8")

    make_fetcher(origin, destination).refresh()

    assert (destination / "kept.txt").exists()
    assert not (destination / "gone.txt").exists()
