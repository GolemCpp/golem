import pytest

from golemcpp.golem.directory_fetcher import DirectoryFetcher
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.fetcher import Fetcher
from golemcpp.golem.fetcher import fetcher_for
from golemcpp.golem.git_fetcher import GitFetcher
from golemcpp.golem.source import Source


# -- which fetcher a source gets is the source's own business ---------------


def test_a_repository_is_fetched_with_git():
    assert isinstance(
        fetcher_for('/cache/r', Source.for_repository('https://host/r.git'), FetchPolicy()),
        GitFetcher)


def test_a_directory_is_copied(tmp_path):
    assert isinstance(
        fetcher_for('/cache/r', Source.for_directory(tmp_path.resolve().as_uri()),
                    FetchPolicy()),
        DirectoryFetcher)


def test_a_fetcher_is_made_for_one_source_in_one_place():
    source = Source.for_repository('https://host/r.git')
    policy = FetchPolicy(reference='cafebabe')

    fetcher = fetcher_for('/cache/r', source, policy)

    assert fetcher.path == '/cache/r'
    assert fetcher.source is source
    assert fetcher.policy is policy


def test_a_way_of_obtaining_a_source_has_to_say_how():
    # The base names the two questions every fetcher answers and answers neither.
    fetcher = Fetcher('/cache/r', Source.for_repository('https://host/r.git'), FetchPolicy())

    with pytest.raises(NotImplementedError):
        fetcher.populate()
    with pytest.raises(NotImplementedError):
        fetcher.refresh()


# -- the local source is checked before anything touches it -----------------


def make_local_fetcher(location):
    return Fetcher('/cache/r', Source.for_directory(location.resolve().as_uri()), FetchPolicy())


def test_a_missing_local_source_is_named(tmp_path):
    with pytest.raises(RuntimeError, match="Can't find local source directory"):
        make_local_fetcher(tmp_path / 'absent').local_path


def test_a_local_source_that_is_a_file_is_named(tmp_path):
    a_file = tmp_path / 'mylib'
    a_file.write_text('not a directory', encoding='utf-8')

    with pytest.raises(RuntimeError, match='not a directory'):
        make_local_fetcher(a_file).local_path


def test_a_remote_source_has_no_local_path_to_check():
    fetcher = Fetcher(
        '/cache/r', Source.for_repository('https://host/r.git'), FetchPolicy())

    assert fetcher.local_path is None
