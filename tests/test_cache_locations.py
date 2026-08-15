import os
from types import SimpleNamespace

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import cache_resolution_policy
from golemcpp.golem import settings
from golemcpp.golem.cache_manager import CacheManager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def _settings(project_dir=None, build_dir=None, options=None):
    return settings.get_settings(
        options=options, build_dir=build_dir, project_dir=project_dir)


def test_primary_cache_directory_from_cli_option(tmp_path):
    options = SimpleNamespace(cache_directory=str(tmp_path / 'my-cache'))
    locations = cache_configuration.resolve_cache_locations(
        _settings(project_dir=str(tmp_path), options=options))

    assert len(locations) == 1
    assert locations[0].location == str(tmp_path / 'my-cache')
    assert locations[0].is_read_only is False


def test_default_cache_directory_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)
    locations = cache_configuration.resolve_cache_locations(_settings(project_dir=str(tmp_path)))

    assert locations[0].location == settings.get_default_cache_directory_path()


def test_additional_writable_and_read_only_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', str(tmp_path / 'primary'))
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
        '{}|{}=github'.format(tmp_path / 'extra1', tmp_path / 'extra2'))
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
        str(tmp_path / 'shared'))

    locations = cache_configuration.resolve_cache_locations(_settings(project_dir=str(tmp_path)))

    by_location = {loc.location: loc for loc in locations}
    assert str(tmp_path / 'primary') in by_location
    assert by_location[str(tmp_path / 'extra1')].is_read_only is False
    assert by_location[str(tmp_path / 'extra2')].regex == 'github'
    assert by_location[str(tmp_path / 'shared')].is_read_only is True


def test_relative_additional_paths_resolved_against_project_dir(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', 'relative-cache')
    locations = cache_configuration.resolve_cache_locations(_settings(project_dir=str(tmp_path)))

    additional = [loc for loc in locations if loc.location.endswith('relative-cache')]
    assert additional
    assert additional[0].location == os.path.join(str(tmp_path), 'relative-cache')


def test_deduplicates_identical_locations(monkeypatch, tmp_path):
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', str(tmp_path / 'shared'))
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', str(tmp_path / 'shared'))

    locations = cache_configuration.resolve_cache_locations(_settings(project_dir=str(tmp_path)))

    shared = [loc for loc in locations if loc.location == str(tmp_path / 'shared')]
    assert len(shared) == 1


def test_cache_resolution_policy_default(monkeypatch):
    monkeypatch.delenv('GOLEM_CACHE_RESOLUTION_POLICY', raising=False)
    assert _settings().get(
        'GOLEM_CACHE_RESOLUTION_POLICY') == cache_resolution_policy.CacheResolutionPolicy.STRICT


def test_cache_resolution_policy_from_option():
    options = SimpleNamespace(cache_resolution_policy='weak')
    assert _settings(options=options).get(
        'GOLEM_CACHE_RESOLUTION_POLICY') == cache_resolution_policy.CacheResolutionPolicy.WEAK


def test_cache_resolution_policy_from_env(monkeypatch):
    monkeypatch.setenv('GOLEM_CACHE_RESOLUTION_POLICY', 'weak')
    assert _settings().get(
        'GOLEM_CACHE_RESOLUTION_POLICY') == cache_resolution_policy.CacheResolutionPolicy.WEAK


def _tool_resource(identifier, cache_key='cppfront'):
    # A resource resolves by its resource: `locator` is the identifier matched
    # against per-cache regexes, `kind` gives the subdir, and `cache_key` the
    # on-disk name.
    return Resource(
        kind=ResourceKind.TOOL,
        cache_key=cache_key,
        source=Source.for_repository(identifier))


def test_resolve_resource_cache_dir_prefers_regex_matching_cache(tmp_path):
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'primary')),
        cache_directory.CacheDirectory(location=str(tmp_path / 'github'),
                                       regex='https://github.com'),
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.STRICT,
        minimization_enabled=False)
    cache_dir = CacheManager(conf).resolve_cache_directory(
        _tool_resource('https://github.com/hsutter/cppfront.git'))

    assert cache_dir.location == str(tmp_path / 'github')


def test_resolve_resource_cache_dir_weak_finds_existing(tmp_path):
    primary = tmp_path / 'primary'
    extra = tmp_path / 'extra'
    (extra / cache_configuration.TOOLS_SUBDIR / 'cppfront').mkdir(parents=True)

    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(primary)),
        cache_directory.CacheDirectory(location=str(extra)),
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.WEAK,
        minimization_enabled=False)
    cache_dir = CacheManager(conf).resolve_cache_directory(_tool_resource('https://host/cppfront.git'))

    assert cache_dir.location == str(extra)


def _seed_resource(cache_root, cache_key='cppfront'):
    # A resource is present in a cache when its classic location exists on disk.
    (cache_root / cache_configuration.TOOLS_SUBDIR / cache_key).mkdir(parents=True)


def test_strict_policy_takes_the_first_matching_cache_without_probing(tmp_path):
    # Nothing is on disk anywhere: a strict resolution never asks, it takes the
    # first cache whose regex matches, read-only ones first.
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'static-regex'),
                                       is_read_only=True, regex='.*recipes.*'),
        cache_directory.CacheDirectory(location=str(tmp_path / 'writable')),
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.STRICT,
        minimization_enabled=False)

    cache_dir = CacheManager(conf).resolve_cache_directory(
        _tool_resource('https://github.com/GolemCpp/recipes.git'))

    assert cache_dir.location == str(tmp_path / 'static-regex')


def test_weak_policy_picks_the_matching_cache_that_holds_the_resource(tmp_path):
    present = tmp_path / 'static-present'
    _seed_resource(present, cache_key='json')
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'static-missing'),
                                       is_read_only=True, regex='.*json.*'),
        cache_directory.CacheDirectory(location=str(present),
                                       is_read_only=True, regex='.*json.*'),
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.WEAK,
        minimization_enabled=False)

    cache_dir = CacheManager(conf).resolve_cache_directory(
        _tool_resource('https://github.com/nlohmann/json.git', cache_key='json'))

    assert cache_dir.location == str(present)


def test_weak_policy_falls_back_to_the_first_writable_cache(tmp_path):
    # No cache holds the resource, so it goes where it can be written, the
    # regex-matching cache first.
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'writable-regex'),
                                       regex='.*json.*'),
        cache_directory.CacheDirectory(location=str(tmp_path / 'writable-default')),
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.WEAK,
        minimization_enabled=False)

    cache_dir = CacheManager(conf).resolve_cache_directory(
        _tool_resource('https://github.com/nlohmann/json.git', cache_key='json'))

    assert cache_dir.location == str(tmp_path / 'writable-regex')
