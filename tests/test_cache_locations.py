import os
from types import SimpleNamespace

from golemcpp.golem import cache


def test_primary_cache_directory_from_cli_option(tmp_path):
    options = SimpleNamespace(cache_directory=str(tmp_path / 'my-cache'))
    locations = cache.resolve_cache_locations(
        project_dir=str(tmp_path), build_dir=None, options=options)

    assert len(locations) == 1
    assert locations[0].location == str(tmp_path / 'my-cache')
    assert locations[0].is_read_only is False


def test_default_cache_directory_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)
    locations = cache.resolve_cache_locations(
        project_dir=str(tmp_path), build_dir=None, options=None)

    assert locations[0].location == cache.get_default_cache_directory_path()


def test_additional_writable_and_read_only_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', str(tmp_path / 'primary'))
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
        '{}|{}=github'.format(tmp_path / 'extra1', tmp_path / 'extra2'))
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
        str(tmp_path / 'shared'))

    locations = cache.resolve_cache_locations(
        project_dir=str(tmp_path), build_dir=None, options=None)

    by_location = {loc.location: loc for loc in locations}
    assert str(tmp_path / 'primary') in by_location
    assert by_location[str(tmp_path / 'extra1')].is_read_only is False
    assert by_location[str(tmp_path / 'extra2')].regex == 'github'
    assert by_location[str(tmp_path / 'shared')].is_read_only is True


def test_relative_additional_paths_resolved_against_project_dir(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', 'relative-cache')
    locations = cache.resolve_cache_locations(
        project_dir=str(tmp_path), build_dir=None, options=None)

    additional = [loc for loc in locations if loc.location.endswith('relative-cache')]
    assert additional
    assert additional[0].location == os.path.join(str(tmp_path), 'relative-cache')


def test_deduplicates_identical_locations(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', str(tmp_path / 'shared'))
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', str(tmp_path / 'shared'))

    locations = cache.resolve_cache_locations(
        project_dir=str(tmp_path), build_dir=None, options=None)

    shared = [loc for loc in locations if loc.location == str(tmp_path / 'shared')]
    assert len(shared) == 1
