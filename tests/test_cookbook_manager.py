import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.cookbook_manager import (
    CookbookManager, get_cookbook_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def make_manager(tmp_path):
    return get_cookbook_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def make_source():
    return Source.for_repository('https://example.com/recipes.git', reference='main')


def test_resource_for_bakes_in_the_recipes_kind():
    source = make_source()
    resource = CookbookManager.resource_for(source)

    assert resource.kind == ResourceKind.COOKBOOK
    assert resource.subdir == cache_configuration.COOKBOOKS_SUBDIR
    assert resource.source is source
    assert resource.cache_key == source.get_cache_key()


def test_resolve_and_locate(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    cached_repository = manager.resolve_cached_resource(source)

    assert cached_repository.cache_root == str(tmp_path / 'cache')
    assert cached_repository.path == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.COOKBOOKS_SUBDIR, source.get_cache_key())


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
    assert manifest.kind == ResourceKind.COOKBOOK.value
    assert manager.cache_manager.read_manifest_source(resource_root).reference == 'main'


def test_weak_policy_falls_back_to_the_regex_cache_when_no_probe_hits():
    # Under the weak policy every candidate is probed on disk; nothing is there,
    # so resolution falls back to the first regex-matching candidate rather than
    # the plain writable default.
    manager = get_cookbook_manager(make_cache_configuration(
        CacheDirectory('/static-regex', is_read_only=True, regex='.*recipes.*'),
        CacheDirectory('/writable-default', is_read_only=False),
        resolution_policy=CacheResolutionPolicy.WEAK))

    cached_repository = manager.resolve_cached_resource(
        Source.for_repository(location='https://github.com/GolemCpp/recipes.git'))

    assert cached_repository.cache_root == '/static-regex'
    assert cached_repository.is_read_only is True
