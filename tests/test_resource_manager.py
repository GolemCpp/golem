import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.resource_manager import (
    DependencyResourceManager, RepositoryResourceManager, ResourceSpec,
    get_dependency_manager, get_repository_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def make_spec():
    source = Source.for_repository('https://example.com/tool.git', reference='v1')
    return ResourceSpec(
        kind=ResourceKind.TOOL,
        cache_key='demo',
        source=source)


def make_cache_manager(*locations):
    return get_cache_manager(
        make_cache_configuration(*locations, minimization_enabled=False))


# -- the unified CacheManager's per-spec resource API -----------------------


def test_resolve_and_locate(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_cache_manager(cache_dir)
    spec = make_spec()

    assert manager.resolve_cache_directory(spec).location == str(tmp_path / 'cache')
    assert manager.get_resource_location(cache_dir, spec) == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.TOOLS_SUBDIR, 'demo')
    assert manager.is_resource_in_cache_directory(cache_dir, spec) is False


def test_write_and_read_source(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_cache_manager(cache_dir)
    spec = make_spec()
    root = manager.get_resource_location(cache_dir, spec)
    os.makedirs(root)

    manager.write_manifest(root, spec)

    manifest = ResourceManifest.read_from_root(root)
    assert manifest.kind == ResourceKind.TOOL.value
    assert manifest.cache_key == 'demo'
    source = manager.read_manifest_source(root)
    assert source.location == 'https://example.com/tool.git'
    assert source.reference == 'v1'
    assert manager.is_resource_in_cache_directory(cache_dir, spec) is True


def test_staged_install_swaps_atomically(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_cache_manager(cache_dir)
    spec = make_spec()

    def populate(staging_root):
        with open(os.path.join(staging_root, 'payload.txt'), 'w') as fileout:
            fileout.write('hi')

    root = manager.staged_install(cache_dir, spec, populate)

    assert os.path.isfile(os.path.join(root, 'payload.txt'))
    assert ResourceManifest.read_from_root(root) is not None
    assert not os.path.exists(root + '.tmp')


def test_remove_honors_read_only_guard(tmp_path):
    writable = cache_directory.CacheDirectory(location=str(tmp_path / 'w'))
    read_only = cache_directory.CacheDirectory(location=str(tmp_path / 'ro'), is_read_only=True)
    spec = make_spec()

    manager = make_cache_manager(writable)
    root = manager.get_resource_location(writable, spec)
    os.makedirs(root)
    assert manager.remove(writable, spec) is True
    assert not os.path.exists(root)

    ro_manager = make_cache_manager(read_only)
    ro_root = ro_manager.get_resource_location(read_only, spec)
    os.makedirs(ro_root)
    assert ro_manager.remove(read_only, spec) is False
    assert os.path.exists(ro_root)


# -- per-kind resource managers (delegating to the CacheManager) ------------


def test_dependency_spec_for_uses_source():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    spec = DependencyResourceManager.spec_for(dep)
    assert spec.kind == ResourceKind.DEPENDENCY
    assert spec.source.type == 'git'
    assert spec.source.location == 'https://example.com/json.git'
    assert spec.location == spec.source.location
    assert spec.cache_key == spec.source.get_cache_key()


def test_repository_spec_for_uses_source():
    source = Source.for_repository('https://example.com/recipes.git', reference='main')
    spec = RepositoryResourceManager.spec_for(source, ResourceKind.RECIPES_REPOSITORY)
    assert spec.kind == ResourceKind.RECIPES_REPOSITORY
    assert spec.source is source
    assert spec.cache_key == source.get_cache_key()


def test_dependency_manager_resolve_and_write(tmp_path):
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False)
    manager = get_dependency_manager(conf)
    dep = Dependency(name='json', repository='https://example.com/json.git')

    cache_dir = manager.resolve_cache_directory(dep)
    root = manager.get_resource_location(cache_dir, dep)
    os.makedirs(root)
    manager.cache_manager.write_manifest(root, manager.spec_for(dep))

    source = manager.cache_manager.read_manifest_source(root)
    assert source.location == 'https://example.com/json.git'


def test_dependency_manager_staged_install_swaps_source_and_manifest(tmp_path):
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False)
    manager = get_dependency_manager(conf)
    dep = Dependency(name='json', repository='https://example.com/json.git')
    cache_dir = manager.resolve_cache_directory(dep)

    def populate(staging_root):
        source_dir = os.path.join(staging_root, cache_configuration.SOURCE_DIRNAME)
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'CMakeLists.txt'), 'w') as fileout:
            fileout.write('project(json)')

    cache_root = manager.staged_install(cache_dir, dep, populate)

    assert os.path.isfile(
        os.path.join(cache_root, cache_configuration.SOURCE_DIRNAME, 'CMakeLists.txt'))
    assert not os.path.exists(cache_root + '.tmp')
    source = manager.cache_manager.read_manifest_source(cache_root)
    assert source.location == 'https://example.com/json.git'


def test_repository_manager_staged_install_swaps_source_and_manifest(tmp_path):
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False)
    manager = get_repository_manager(conf)
    source = Source.for_repository('https://example.com/recipes.git', reference='main')
    cache_dir = manager.resolve_cache_directory(source, ResourceKind.RECIPES_REPOSITORY)

    def populate(staging_root):
        with open(os.path.join(staging_root, 'recipes.json'), 'w') as fileout:
            fileout.write('{}')

    cache_root = manager.staged_install(
        cache_dir, source, ResourceKind.RECIPES_REPOSITORY, populate)

    assert os.path.isfile(os.path.join(cache_root, 'recipes.json'))
    assert not os.path.exists(cache_root + '.tmp')
    manifest = ResourceManifest.read_from_root(cache_root)
    assert manifest.kind == ResourceKind.RECIPES_REPOSITORY.value
    assert manager.cache_manager.read_manifest_source(cache_root).reference == 'main'


def test_repository_manager_resolve(tmp_path):
    conf = make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False)
    manager = get_repository_manager(conf)
    source = Source.for_repository('https://example.com/recipes.git', reference='main')

    cache_dir = manager.resolve_cache_directory(source, ResourceKind.RECIPES_REPOSITORY)
    assert cache_dir.location == str(tmp_path / 'cache')
    root = manager.get_resource_location(cache_dir, source, ResourceKind.RECIPES_REPOSITORY)
    assert root == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.RECIPES_SUBDIR, source.get_cache_key())
