import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.recipes_repository_manager import (
    RecipesRepositoryManager, get_recipes_repository_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def make_manager(tmp_path):
    return get_recipes_repository_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def make_source():
    return Source.for_repository('https://example.com/recipes.git', reference='main')


def test_resource_for_bakes_in_the_recipes_kind():
    source = make_source()
    resource = RecipesRepositoryManager.resource_for(source)

    assert resource.kind == ResourceKind.RECIPES_REPOSITORY
    assert resource.subdir == cache_configuration.RECIPES_SUBDIR
    assert resource.source is source
    assert resource.cache_key == source.get_cache_key()


def test_resolve_and_locate(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    cache_dir = manager.resolve_cache_directory(source)

    assert cache_dir.location == str(tmp_path / 'cache')
    assert manager.get_resource_location(cache_dir, source) == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.RECIPES_SUBDIR, source.get_cache_key())


def test_staged_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    def populate(staging_root):
        with open(os.path.join(staging_root, 'recipes.json'), 'w') as fileout:
            fileout.write('{}')

    resource_root = manager.staged_install(
        manager.resolve_cached_resource(source), populate)

    assert os.path.isfile(os.path.join(resource_root, 'recipes.json'))
    assert not os.path.exists(resource_root + '.tmp')
    manifest = ResourceManifest.read_from_root(resource_root)
    assert manifest.kind == ResourceKind.RECIPES_REPOSITORY.value
    assert manager.cache_manager.read_manifest_source(resource_root).reference == 'main'


def test_weak_policy_falls_back_to_the_regex_cache_when_no_probe_hits():
    # Under the weak policy every candidate is probed on disk; nothing is there,
    # so resolution falls back to the first regex-matching candidate rather than
    # the plain writable default.
    manager = get_recipes_repository_manager(make_cache_configuration(
        CacheDirectory('/static-regex', is_read_only=True, regex='.*recipes.*'),
        CacheDirectory('/writable-default', is_read_only=False),
        resolution_policy=CacheResolutionPolicy.WEAK))

    cache_dir = manager.resolve_cache_directory(
        Source.for_repository(location='https://github.com/GolemCpp/recipes.git'))

    assert cache_dir.location == '/static-regex'
