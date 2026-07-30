import hashlib
import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import helpers
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.dependency_manager import DependencyManager, get_dependency_manager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


DEPENDENCIES_SUBDIR = cache_configuration.DEPENDENCIES_SUBDIR


def make_manager(tmp_path, minimization_enabled=False):
    return get_dependency_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=minimization_enabled))


def make_dependency():
    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_hash = '1234567890abcdef'
    return dep


def expected_cache_key(dep):
    return Source.for_repository(
        location=dep.repository,
        reference=helpers.resolved_reference(dep.resolved_version, dep.resolved_hash)
    ).get_cache_key()


def test_resource_for_uses_the_dependency_source():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    resource = DependencyManager.resource_for(dep)

    assert resource.kind == ResourceKind.DEPENDENCY
    assert resource.source.type == 'git'
    assert resource.source.location == 'https://example.com/json.git'
    assert resource.location == resource.source.location
    assert resource.cache_key == resource.source.get_cache_key()


def test_resolve_and_write(tmp_path):
    manager = make_manager(tmp_path)
    dep = Dependency(name='json', repository='https://example.com/json.git')

    cache_dir = manager.resolve_cache_directory(dep)
    root = manager.get_resource_location(cache_dir, dep)
    os.makedirs(root)
    manager.cache_manager.write_manifest(root, manager.resource_for(dep))

    source = manager.cache_manager.read_manifest_source(root)
    assert source.location == 'https://example.com/json.git'


def test_staged_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    dep = Dependency(name='json', repository='https://example.com/json.git')
    cache_dir = manager.resolve_cache_directory(dep)

    def populate(staging_root):
        source_dir = os.path.join(staging_root, cache_configuration.SOURCE_DIRNAME)
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'CMakeLists.txt'), 'w') as fileout:
            fileout.write('project(json)')

    resource_root = manager.staged_install(
        manager.get_cached_resource(cache_dir, dep), populate)

    assert os.path.isfile(
        os.path.join(resource_root, cache_configuration.SOURCE_DIRNAME, 'CMakeLists.txt'))
    assert not os.path.exists(resource_root + '.tmp')
    source = manager.cache_manager.read_manifest_source(resource_root)
    assert source.location == 'https://example.com/json.git'


def test_get_resource_location_reuses_the_repository_cache_key(tmp_path):
    manager = make_manager(tmp_path)
    cache_dir = CacheDirectory(str(tmp_path / 'cache'), is_read_only=False)
    dep = make_dependency()

    assert manager.get_resource_location(cache_dir, dep) == os.path.join(
        cache_dir.location, DEPENDENCIES_SUBDIR, expected_cache_key(dep))


def test_get_resource_location_is_minimized_flat_when_enabled(tmp_path):
    manager = make_manager(tmp_path, minimization_enabled=True)
    cache_dir = CacheDirectory(str(tmp_path / 'cache'), is_read_only=False)
    dep = make_dependency()

    expected_name = hashlib.sha1(
        '{}/{}'.format(DEPENDENCIES_SUBDIR, expected_cache_key(dep)).encode('utf-8')
    ).hexdigest()[:8]

    location = manager.get_resource_location(cache_dir, dep)

    assert location == os.path.join(cache_dir.location, expected_name)
    # Flat: no per-kind subdirectory in the path.
    assert DEPENDENCIES_SUBDIR not in os.path.relpath(location, cache_dir.location)


def test_get_resource_location_prefers_an_existing_non_minimized_layout(tmp_path):
    manager = make_manager(tmp_path, minimization_enabled=True)
    cache_dir = CacheDirectory(str(tmp_path / 'cache'), is_read_only=False)
    dep = make_dependency()

    non_minimized = os.path.join(
        cache_dir.location, DEPENDENCIES_SUBDIR, expected_cache_key(dep))
    os.makedirs(non_minimized, exist_ok=True)

    # A resource already present under the classic layout keeps its location even
    # though minimization is enabled.
    assert manager.get_resource_location(cache_dir, dep) == non_minimized
