from golemcpp.golem import cache_directory
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.version_resolver import VersionResolver
from conftest import make_cache_configuration


def test_dependency_accepts_repository_keyword():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    assert dep.repository == 'https://example.com/json.git'
    assert dep.directory == ''
    assert dep.is_non_git_directory() is False


def test_dependency_accepts_directory_keyword():
    dep = Dependency(name='mylib', directory='./mylib')
    assert dep.directory == './mylib'
    assert dep.repository == ''
    assert dep.is_non_git_directory() is True
    # A directory dependency has no version to resolve.
    assert dep.resolve() == '-'
    source = dep.to_source()
    assert source.type == 'directory'
    assert source.location == './mylib'


def test_dependency_serializes_and_round_trips_repository():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload['repository'] == 'https://example.com/json.git'
    assert 'url' not in payload

    restored = Dependency.unserialize_from_json(payload)
    assert restored.repository == 'https://example.com/json.git'


def test_dependency_serializes_directory():
    dep = Dependency(name='mylib', directory='./mylib')
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload['directory'] == './mylib'

    restored = Dependency.unserialize_from_json(payload)
    assert restored.directory == './mylib'


def make_configuration(tmp_path):
    return make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')))


def test_cached_resource_is_resolved_once_and_kept(tmp_path):
    cache_configuration = make_configuration(tmp_path)
    dep = Dependency(name='json', repository='https://example.com/json.git')
    dep.resolved_hash = '1234567890abcdef'

    cached = dep.get_cached_resource(cache_configuration)

    assert cached is dep.cached_resource
    assert dep.get_cached_resource(cache_configuration) is cached


def test_resolving_drops_a_cached_resource_of_the_unresolved_dependency(
        tmp_path, monkeypatch):
    # The cache key comes from the resolved reference, so a cached resource taken
    # before resolution points at another location and must not be reused.
    cache_configuration = make_configuration(tmp_path)
    dep = Dependency(name='json', repository='https://example.com/json.git')

    stale = dep.get_cached_resource(cache_configuration)

    monkeypatch.setattr(
        VersionResolver, 'resolve',
        staticmethod(lambda *args, **kwargs: ('3.11.3', '1234567890abcdef')))
    dep.resolve()

    assert dep.cached_resource is None
    assert dep.get_cached_resource(cache_configuration).path != stale.path