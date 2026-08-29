import os

import pytest

from golemcpp.golem import advertisement_store
from golemcpp.golem import safe_part

LISTING = "ref: refs/heads/main\tHEAD\nabc123\tHEAD\nabc123\trefs/heads/main\n"


@pytest.fixture(autouse=True)
def outside_a_resolve(monkeypatch):
    """Every test starts with no resolve running above it."""
    monkeypatch.delenv(advertisement_store.DIRECTORY_VARIABLE, raising=False)


def test_nothing_is_kept_outside_a_resolve():
    advertisement_store.write("https://host/r.git", LISTING)
    assert advertisement_store.read("https://host/r.git") == ""


def test_what_a_resolve_keeps_it_reads_back(tmp_path):
    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write("https://host/r.git", LISTING)
        assert advertisement_store.read("https://host/r.git") == LISTING


def test_every_spelling_of_one_repository_reads_one_file(tmp_path):
    # They already share one cache root, so they share one advertisement.
    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write("https://github.com/nlohmann/json.git", LISTING)
        assert advertisement_store.read("https://github.com/nlohmann/json") == LISTING


def test_two_repositories_are_kept_apart(tmp_path):
    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write("https://host/one.git", LISTING)
        assert advertisement_store.read("https://host/two.git") == ""


def test_the_outermost_resolve_empties_the_directory(tmp_path):
    directory = tmp_path / "resolve"
    directory.mkdir()
    (directory / "left-behind").write_text(LISTING, encoding="utf-8")

    with advertisement_store.shared(str(directory)):
        # A run killed halfway leaves the directory where the next one looks, so
        # emptying it on the way in is what keeps this out of a second resolve.
        assert os.listdir(str(directory)) == []


def test_the_directory_outlives_the_resolve_that_made_it(tmp_path):
    directory = tmp_path / "resolve"

    with advertisement_store.shared(str(directory)):
        advertisement_store.write("https://host/r.git", LISTING)

    assert os.listdir(str(directory))


def test_a_nested_resolve_writes_where_the_outermost_one_did(tmp_path):
    outer = tmp_path / "outer"
    nested = tmp_path / "nested"

    with advertisement_store.shared(str(outer)):
        with advertisement_store.shared(str(nested)):
            advertisement_store.write("https://host/r.git", LISTING)

        assert advertisement_store.read("https://host/r.git") == LISTING

    assert not nested.exists()


def test_a_nested_resolve_keeps_what_the_outermost_one_read(tmp_path):
    directory = tmp_path / "resolve"

    with advertisement_store.shared(str(directory)):
        advertisement_store.write("https://host/r.git", LISTING)

        with advertisement_store.shared(str(tmp_path / "nested")):
            assert advertisement_store.read("https://host/r.git") == LISTING


def test_the_store_closes_with_the_resolve(tmp_path):
    with advertisement_store.shared(str(tmp_path / "resolve")):
        pass

    assert advertisement_store.read("https://host/r.git") == ""


def test_a_directory_that_cannot_be_made_leaves_the_store_inert(tmp_path):
    # Under a file rather than a directory: nothing here may fail a resolve, so
    # the block runs and every read costs the round trip it was to save.
    blocked = tmp_path / "file"
    blocked.write_text("", encoding="utf-8")

    with advertisement_store.shared(str(blocked / "resolve")):
        advertisement_store.write("https://host/r.git", LISTING)
        assert advertisement_store.read("https://host/r.git") == ""


def test_a_url_naming_no_repository_is_kept_nowhere(tmp_path):
    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write("https://", LISTING)
        assert advertisement_store.read("https://") == ""
        assert os.listdir(str(tmp_path / "resolve")) == []


def test_a_long_id_is_shortened_to_a_file_name(tmp_path):
    # A local repository is spelled out of its whole path, which has no bound
    # where a file name does.
    deep = "file:///" + "/".join("directory{}".format(step) for step in range(20))

    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write(deep + "/mylib", LISTING)

        kept = os.listdir(str(tmp_path / "resolve"))
        assert len(kept) == 1
        assert len(kept[0]) <= safe_part.READABLE_LENGTH + 16
        assert advertisement_store.read(deep + "/mylib") == LISTING


def test_two_long_ids_are_kept_apart(tmp_path):
    deep = "file:///" + "/".join("directory{}".format(step) for step in range(20))

    with advertisement_store.shared(str(tmp_path / "resolve")):
        advertisement_store.write(deep + "/one", LISTING)
        assert advertisement_store.read(deep + "/two") == ""
