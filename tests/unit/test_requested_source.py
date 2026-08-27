import pytest

from golemcpp.golem.requested_source import format_location
from golemcpp.golem.requested_source import parse_location
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.setting_descriptor import SettingProcessingContext


def make_repository(path):
    '''A checkout, as the filesystem shows one: `.git` holding a HEAD.'''
    git_dir = path / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    return path


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
    assert parse_location(spelled, context) == parse_location(
        'https://host/r.git', context)


# -- a location may name the version to obtain -----------------------------


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


def test_a_requested_source_never_carries_an_identity(tmp_path):
    # It is what a locator was settled into, and an identity has none until
    # something resolves it.
    with pytest.raises(ValueError, match="only a dependency's source"):
        RequestedSource.parse('@boost', str(tmp_path))
