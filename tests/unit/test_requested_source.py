import os

import pytest

from golemcpp.golem.requested_source import format_location
from golemcpp.golem.requested_source import parse_location
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.locator import Locator
from golemcpp.golem.setting_descriptor import SettingProcessingContext


def make_repository(path):
    '''A checkout, as the filesystem shows one: `.git` holding a HEAD.'''
    git_dir = path / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    return path


def make_bare_repository(path):
    '''A bare repository: the git directory itself, with no working tree.'''
    path.mkdir(parents=True)
    (path / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (path / 'objects').mkdir()
    (path / 'refs').mkdir()
    return path


def test_parse_normalizes_and_classifies_local_directory(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    requested = RequestedSource.parse('recipes', str(project_dir))

    assert requested.locator == Locator(recipes_dir.resolve().as_uri())
    assert requested.type == 'directory'


def test_parse_parses_encoded_local_directory_path(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1'
    recipes_dir.mkdir(parents=True)

    requested = RequestedSource.parse('recipes #1', str(project_dir))

    assert requested.locator.get_local_path() == str(recipes_dir.resolve())


def test_parse_normalizes_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    requested = RequestedSource.parse('recipes', str(project_dir))

    assert requested.locator == Locator(recipes_dir.resolve().as_uri())
    assert requested.locator.get_local_path() == str(recipes_dir.resolve())


def test_parse_classifies_local_non_git_directory(tmp_path):
    project_dir = tmp_path / 'project'
    lib_dir = project_dir / 'lib'
    lib_dir.mkdir(parents=True)

    requested = RequestedSource.parse('lib', str(project_dir))

    assert requested.type == 'directory'
    assert requested.locator == Locator(lib_dir.resolve().as_uri())


def test_parse_classifies_git_directory_as_git(tmp_path):
    project_dir = tmp_path / 'project'
    make_repository(project_dir / 'recipes')

    requested = RequestedSource.parse('recipes', str(project_dir))

    assert requested.type == 'git'


def test_parse_refuses_an_explicit_git_kind_on_a_plain_directory(tmp_path):
    # `git+` says the location is a repository, so a directory git cannot clone
    # from is a misconfiguration, named here rather than inside git later.
    project_dir = tmp_path / 'project'
    (project_dir / 'lib').mkdir(parents=True)

    with pytest.raises(ValueError) as error:
        RequestedSource.parse('git+lib', str(project_dir))

    assert 'not a repository git can clone from' in str(error.value)


def test_parse_accepts_an_explicit_git_kind_on_a_bare_repository(tmp_path):
    # A bare repository is the git directory itself: nothing to work in, and
    # every bit as clonable as the checkout it was made from.
    project_dir = tmp_path / 'project'
    make_bare_repository(project_dir / 'lib.git')

    requested = RequestedSource.parse('git+lib.git', str(project_dir))

    assert requested.type == 'git'


def test_parse_classifies_a_bare_repository_as_git(tmp_path):
    project_dir = tmp_path / 'project'
    make_bare_repository(project_dir / 'lib.git')

    assert RequestedSource.parse('lib.git', str(project_dir)).type == 'git'


def test_parse_honours_an_explicit_directory_kind_on_a_git_checkout(tmp_path):
    project_dir = tmp_path / 'project'
    make_repository(project_dir / 'recipes')

    requested = RequestedSource.parse('directory+recipes', str(project_dir))

    assert requested.type == 'directory'


def test_parse_honours_an_explicit_kind_on_a_remote_url(tmp_path):
    requested = RequestedSource.parse('git+https://github.com/GolemCpp/recipes.git', str(tmp_path))

    assert requested.type == 'git'
    assert requested.locator == Locator('https://github.com/GolemCpp/recipes.git')


def test_parse_refuses_an_unknown_kind(tmp_path):
    with pytest.raises(ValueError) as error:
        RequestedSource.parse('gti+https://github.com/GolemCpp/recipes.git', str(tmp_path))

    assert "unknown source kind 'gti'" in str(error.value)
    assert 'git+' in str(error.value)
    assert 'directory+' in str(error.value)


def test_parse_does_not_read_a_plus_inside_a_url_as_a_kind(tmp_path):
    requested = RequestedSource.parse('https://host/a+b.git', str(tmp_path))

    assert requested.type == 'git'
    assert requested.locator == Locator('https://host/a+b.git')


def test_format_location_always_spells_the_kind():
    context = SettingProcessingContext(project_dir=None)

    assert format_location(
        RequestedSource.for_repository('https://host/r.git'), context) == 'git+https://host/r.git'
    assert format_location(
        RequestedSource.for_directory('file:///tmp/mylib'), context) == 'directory+file:///tmp/mylib'


def test_parse_location_round_trips_through_format_location(tmp_path):
    context = SettingProcessingContext(project_dir=str(tmp_path))
    spelled = format_location(parse_location('https://host/r.git', context), context)

    assert spelled == 'git+https://host/r.git'
    assert parse_location(spelled, context) == parse_location('https://host/r.git', context)


# -- a location may name the version to obtain -----------------------------


def test_parse_reads_the_version_a_remote_location_names(tmp_path):
    requested = RequestedSource.parse(
        'https://host/r.git#^3.0.0', str(tmp_path))

    assert requested.locator == Locator('https://host/r.git')
    assert requested.version == '^3.0.0'
    assert requested.type == 'git'


def test_parse_keeps_a_version_holding_a_slash(tmp_path):
    # A namespaced ref is the common shape, and only the first separator counts.
    requested = RequestedSource.parse(
        'git+https://host/r.git#release/1.2.3', str(tmp_path))

    assert requested.locator == Locator('https://host/r.git')
    assert requested.version == 'release/1.2.3'


def test_parse_leaves_the_version_empty_when_none_is_named(tmp_path):
    # Empty means unasked. What an unasked version follows is the resource kind's
    # business, not the syntax's.
    assert RequestedSource.parse('https://host/r.git', str(tmp_path)).version == ''


def test_parse_reads_a_version_on_a_local_git_checkout(tmp_path):
    project_dir = tmp_path / 'project'
    checkout = make_repository(project_dir / 'mylib')

    requested = RequestedSource.parse('mylib#v1.2.0', str(project_dir))

    assert requested.locator == Locator(checkout.resolve().as_uri())
    assert requested.version == 'v1.2.0'


def test_parse_reads_a_version_spelled_on_a_file_url(tmp_path):
    # The same locator as above, spelled the way golem itself writes one back.
    # `#` is a fragment to a URL parser and a version separator here, and a
    # location means the same thing whichever way it was spelled.
    project_dir = tmp_path / 'project'
    checkout = make_repository(project_dir / 'mylib')

    requested = RequestedSource.parse(
        checkout.resolve().as_uri() + '#v1.2.0', str(project_dir))

    assert requested.locator == Locator(checkout.resolve().as_uri())
    assert requested.version == 'v1.2.0'


def test_parse_does_not_read_a_separator_inside_a_directory_name(tmp_path):
    # `#` is legal in a path. A location naming a directory as it stands is that
    # directory, never a versioned request for part of it.
    project_dir = tmp_path / 'project'
    checkout = make_repository(project_dir / 'weird#name')

    requested = RequestedSource.parse('weird#name', str(project_dir))

    assert requested.locator == Locator(checkout.resolve().as_uri())
    assert requested.version == ''


def test_parse_does_not_read_a_version_on_a_copied_directory(tmp_path):
    project_dir = tmp_path / 'project'
    (project_dir / 'lib#1').mkdir(parents=True)

    requested = RequestedSource.parse('lib#1', str(project_dir))

    assert requested.type == 'directory'
    assert requested.version == ''


def test_an_explicit_git_kind_looks_behind_a_directory_it_cannot_clone(tmp_path):
    # `weird#name` is there, so it would be the location asked for -- but `git+`
    # says the location is a repository, and this directory is not one. So the
    # separator is read as one after all, and the version behind it found.
    project_dir = tmp_path / 'project'
    (project_dir / 'weird#name').mkdir(parents=True)
    checkout = make_repository(project_dir / 'weird')

    requested = RequestedSource.parse('git+weird#name', str(project_dir))

    assert requested.locator == Locator(checkout.resolve().as_uri())
    assert requested.version == 'name'


def test_an_explicit_directory_kind_reads_no_version_at_all(tmp_path):
    # A copied directory has no version to ask for, so nothing here is ambiguous:
    # the separator can only be part of the name, whether that name is there yet
    # or not.
    project_dir = tmp_path / 'project'
    make_repository(project_dir / 'mylib')

    requested = RequestedSource.parse('directory+mylib#v1.2.0', str(project_dir))

    assert requested.version == ''
    assert requested.locator == Locator((project_dir / 'mylib#v1.2.0').resolve().as_uri())


def test_parse_refuses_a_version_asked_of_a_copied_directory(tmp_path):
    project_dir = tmp_path / 'project'
    (project_dir / 'lib').mkdir(parents=True)

    with pytest.raises(ValueError) as error:
        RequestedSource.parse('lib#v1.2.0', str(project_dir))

    assert 'a copied directory is whatever it holds now' in str(error.value)


def test_a_local_git_location_survives_being_written_back_and_read_again(tmp_path):
    # What golem persists is what golem re-reads: format_location spells a local
    # location as a file URL, and parsing that back has to find the same version.
    make_repository(tmp_path / 'recipes')
    context = SettingProcessingContext(project_dir=str(tmp_path))

    requested = parse_location('recipes#v2.1.0', context)
    again = parse_location(format_location(requested, context), context)

    assert again == requested
    assert again.version == 'v2.1.0'


def test_format_location_writes_the_version_back(tmp_path):
    context = SettingProcessingContext(project_dir=str(tmp_path))
    spelled = format_location(
        parse_location('https://host/r.git#^3.0.0', context), context)

    assert spelled == 'git+https://host/r.git#^3.0.0'
    assert parse_location(spelled, context) == \
        parse_location('https://host/r.git#^3.0.0', context)


def test_format_location_omits_a_version_that_was_never_asked_for(tmp_path):
    context = SettingProcessingContext(project_dir=str(tmp_path))

    assert format_location(
        parse_location('https://host/r.git', context), context) == \
        'git+https://host/r.git'


# -- the shapes git accepts, which golem does not try to enumerate ----------


def test_an_scp_style_remote_keeps_its_spelling_and_takes_a_version(tmp_path):
    # The form a host hands you by default. Rewriting it to ssh:// would not be
    # lossless, so what git gets is what was written.
    requested = RequestedSource.parse(
        'git@github.com:nlohmann/json.git#v3.12.0', str(tmp_path))

    assert requested.type == 'git'
    assert requested.locator == Locator('git@github.com:nlohmann/json.git')
    assert requested.version == 'v3.12.0'
    # And its identity says where that path hangs from.
    assert requested.get_id() == '@json@nlohmann@github.com@scp.git'


def test_a_transport_helper_passes_through_untouched(tmp_path):
    # `<transport>::<address>` dispatches to a git-remote-<transport> on PATH.
    # Golem cannot know what those are, so it does not try to.
    requested = RequestedSource.parse('hg::https://host/repo#default', str(tmp_path))

    assert requested.locator == Locator('hg::https://host/repo')
    assert requested.version == 'default'


def test_a_windows_drive_is_a_path_not_a_remote(tmp_path):
    # `C:` reads as an scp-style host by the colon rule. Git makes the exception
    # and so must golem, on every platform, since a cache is shared between them.
    requested = RequestedSource.parse('C:/proj/mylib', str(tmp_path))

    assert requested.locator.is_local()


def test_a_path_holding_a_colon_needs_the_leading_dot(tmp_path, monkeypatch):
    # Git's own escape hatch, inherited rather than reinvented so the two can
    # never disagree about what a locator is.
    #
    # The disk is made to claim the name rather than hold it: a colon cannot be in
    # a Windows filename, and the dot is what answers for it either way.
    monkeypatch.setattr(os.path, 'isdir', lambda path: True)

    assert RequestedSource.parse('./weird:name', str(tmp_path)).locator.is_local()
    assert not RequestedSource.parse('weird:name', str(tmp_path)).locator.is_local()


def test_a_version_on_a_url_needs_no_filesystem_to_be_found(tmp_path):
    # Nothing here is on this machine, so no probe can help: in a URL an
    # unencoded `#` is never part of the path and always starts a version.
    requested = RequestedSource.parse('file:///absent/mylib#v1.2.0', str(tmp_path))

    assert requested.locator == Locator('file:///absent/mylib')
    assert requested.version == 'v1.2.0'
