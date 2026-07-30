import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.overrides_repository_manager import (
    OverridesRepositoryManager, get_overrides_repository_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def make_manager(tmp_path):
    return get_overrides_repository_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def make_source():
    return Source.for_repository('https://example.com/overrides.git', reference='main')


def test_resource_for_bakes_in_the_overrides_kind():
    source = make_source()
    resource = OverridesRepositoryManager.resource_for(source)

    assert resource.kind == ResourceKind.OVERRIDES_REPOSITORY
    assert resource.subdir == cache_configuration.OVERRIDES_SUBDIR
    assert resource.source is source
    assert resource.cache_key == source.get_cache_key()


def test_resolve_and_locate(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    cached_repository = manager.resolve_cached_resource(source)

    assert cached_repository.cache_root == str(tmp_path / 'cache')
    assert cached_repository.path == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.OVERRIDES_SUBDIR, source.get_cache_key())


def test_staged_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    def populate(staging_root):
        with open(os.path.join(staging_root, 'overrides.json'), 'w') as fileout:
            fileout.write('[]')

    resource_root = manager.staged_install(
        manager.resolve_cached_resource(source), populate)

    assert os.path.isfile(os.path.join(resource_root, 'overrides.json'))
    assert not os.path.exists(resource_root + '.tmp')
    manifest = ResourceManifest.read_from_root(resource_root)
    assert manifest.kind == ResourceKind.OVERRIDES_REPOSITORY.value
    assert manager.cache_manager.read_manifest_source(resource_root).reference == 'main'


def test_the_two_repository_kinds_do_not_share_a_cache_location(tmp_path):
    # Recipes and overrides repositories from the same URL land in different
    # subdirectories, which is the whole reason the managers are separate.
    from golemcpp.golem.recipes_repository_manager import RecipesRepositoryManager

    source = make_source()

    assert (OverridesRepositoryManager.resource_for(source).subdir
            != RecipesRepositoryManager.resource_for(source).subdir)
