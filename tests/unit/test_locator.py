import os

import pytest

from golemcpp.golem.locator import Locator, generate_id, is_bare_path

# -- what counts as a path, which is git's question to answer ---------------


@pytest.mark.parametrize(
    'value',
    [
        'mylib',
        './mylib',
        '../mylib',
        '/srv/git/mylib.git',
        './weird:name',
        r'\\server\share\mylib.git',
    ],
)
def test_a_path_written_as_one_is_a_path(value):
    assert is_bare_path(value) is True


@pytest.mark.parametrize(
    'value',
    [
        'https://github.com/org/repo.git',
        'ssh://git@github.com/org/repo.git',
        'git://host/repo.git',
        'file:///srv/git/mylib.git',
        # scp-style, the form a host hands you by default.
        'git@github.com:org/repo.git',
        # A transport helper, dispatched to `git-remote-hg`.
        'hg::https://host/repo',
        # An alias only the user's git config knows how to rewrite.
        'gh:org/repo',
    ],
)
def test_everything_git_takes_as_it_stands_is_not_a_path(value):
    assert is_bare_path(value) is False


@pytest.mark.parametrize('value', ['C:/proj/mylib', r'C:\proj\mylib'])
def test_a_windows_drive_is_a_path_not_a_host(value):
    # `C:` reads as an scp-style host by the colon rule, and as a URL scheme to
    # urlparse. Git makes the same exception, and golem has to make it wherever
    # it runs, since a cache is shared between platforms.
    assert is_bare_path(value) is True


# -- the type itself --------------------------------------------------------


def test_a_path_is_refused_as_a_settled_locator():
    # `./mylib` means nothing without the project it was written in.
    with pytest.raises(ValueError) as error:
        Locator('./mylib')

    assert 'resolved against a project first' in str(error.value)


def test_an_empty_locator_names_nothing():
    assert not Locator()
    assert Locator() == Locator('')
    assert str(Locator()) == ''


def test_a_remote_locator_keeps_its_exact_spelling():
    # Rewriting scp-style to ssh:// would not be lossless -- `host:foo.git` is
    # relative to the login user's home where `ssh://host/foo.git` is absolute --
    # so what git was handed is what the user wrote.
    scp = 'git@github.com:org/repo.git'

    assert str(Locator(scp)) == scp
    assert Locator(scp).get_local_path() is None
    assert Locator(scp).is_local() is False


def test_equality_is_between_locators_only():
    # Deliberately not comparing equal to the string spelling it: the boundaries
    # where a locator becomes text are the ones this type exists to make visible.
    assert Locator('https://host/r.git') == Locator('https://host/r.git')
    assert Locator('https://host/r.git') != 'https://host/r.git'


def test_a_file_url_names_a_local_path(tmp_path):
    locator = Locator(tmp_path.resolve().as_uri())

    assert locator.is_local() is True
    assert locator.get_local_path() == str(tmp_path.resolve())
    assert locator.is_existing_directory() is True


def test_a_local_path_that_is_not_there_names_no_directory(tmp_path):
    locator = Locator((tmp_path / 'absent').resolve().as_uri())

    assert locator.get_local_path() == str(tmp_path / 'absent')
    assert locator.is_existing_directory() is False


def test_a_percent_encoded_path_reads_back_as_it_was_written(tmp_path):
    directory = tmp_path / 'weird#name'
    directory.mkdir()
    locator = Locator(directory.resolve().as_uri())

    # as_uri percent-encodes the separator, which is what keeps a `#` in a name
    # from reading as a version.
    assert '%23' in str(locator)
    assert locator.get_local_path() == str(directory)


def test_a_repository_is_recognised_through_the_locator(tmp_path):
    checkout = tmp_path / 'mylib'
    (checkout / '.git').mkdir(parents=True)
    (checkout / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    assert Locator(checkout.resolve().as_uri()).is_git_repository() is True
    assert Locator(tmp_path.resolve().as_uri()).is_git_repository() is False
    assert Locator('https://host/r.git').is_git_repository() is False


def test_get_id_is_the_identity_of_what_the_locator_names():
    # A Locator answers for its own identity; how that identity is composed is
    # source_id's, and its arguments live in test_source_id.py.
    assert Locator('https://github.com/nlohmann/json.git').get_id() == generate_id(
        'https://github.com/nlohmann/json.git'
    )


def test_a_settled_locator_carries_no_fragment(tmp_path):
    # What a `#` in a local path becomes, so nothing downstream has to know the
    # version separator exists.
    directory = tmp_path / 'weird#name'
    directory.mkdir()

    assert Locator(directory.resolve().as_uri()).get_local_path() == str(directory)


# -- shapes that used to crash rather than be reported ----------------------


@pytest.mark.parametrize('value', ['ssh://', 'http://', 'file://'])
def test_a_scheme_on_its_own_is_refused_where_it_is_written(value):
    # It used to reach generate_id and index an empty list, so what a typo in a
    # location produced was an IndexError traceback out of cache-key building.
    with pytest.raises(ValueError) as error:
        Locator(value)

    assert 'names nothing' in str(error.value)


def test_a_locator_no_url_parser_can_read_is_named_by_the_error():
    # A bad setting is reported as `ERROR: <message>` and nothing else, so
    # urlparse's own `Invalid IPv6 URL` would name neither the locator nor the
    # setting it was written in.
    with pytest.raises(ValueError) as error:
        Locator('http://[')

    assert "'http://['" in str(error.value)
    assert 'cannot be read as a URL' in str(error.value)
