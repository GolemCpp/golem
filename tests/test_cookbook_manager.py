import os

from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.cookbook_manager import (
    CookbookManager, get_cookbook_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from golemcpp.golem.resolved_version import ResolvedVersion
from conftest import STUB_HEAD
from conftest import make_cache_configuration


def make_manager(tmp_path):
    return get_cookbook_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def make_source():
    return RequestedSource.for_repository('https://example.com/recipes.git', version='main')


def test_resource_for_bakes_in_the_recipes_kind():
    source = make_source()
    resource = CookbookManager.resource_for(Cookbook(source=source))

    assert resource.kind == ResourceKind.COOKBOOK
    assert resource.subdir == cache_configuration.COOKBOOKS_SUBDIR
    # Nothing resolved it, so it names no version -- which the key does not
    # need, since a cookbook root is named after the request.
    assert resource.source == source.resolved_at(ResolvedVersion())
    assert resource.cache_key == CookbookManager.cache_key_for(Cookbook(source=source))


def test_a_cookbook_lands_where_it_did_before_being_resolved():
    # A cookbook follows the version it was configured with, so resolving one may
    # never move what is already cached.
    source = make_source()

    unresolved = CookbookManager.resource_for(Cookbook(source=source))
    resolved = CookbookManager.resource_for(
        CookbookManager.resolve_version(Cookbook(source=source)))

    assert resolved.cache_key == unresolved.cache_key


def test_resolve_and_locate(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    cached_repository = manager.resolve_cached_resource(Cookbook(source=source))

    assert cached_repository.cache_root == str(tmp_path / 'cache')
    assert cached_repository.path == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.COOKBOOKS_SUBDIR,
        CookbookManager.cache_key_for(Cookbook(source=source)))


def test_guard_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    def populate(staging_root):
        with open(os.path.join(staging_root, 'recipes.json'), 'w') as fileout:
            fileout.write('{}')

    item = Cookbook(source=source)
    item.resolved = ResolvedVersion(reference='main', revision=STUB_HEAD)
    cached = manager.resolve_cached_resource(item)
    resource_root = manager.guard_install(cached, populate)

    assert os.path.isfile(os.path.join(resource_root, 'recipes.json'))
    assert not os.path.exists(cached.staging_path)
    manifest = ResourceManifest.read_from_root(resource_root)
    assert manifest.kind == ResourceKind.COOKBOOK.value
    assert manager.cache_manager.read_manifest_source(cached).resolved.reference == 'main'


def test_making_cookbooks_available_keeps_the_configured_order(tmp_path):
    manager = make_manager(tmp_path)
    sources = [
        RequestedSource.for_repository('https://example.com/{}.git'.format(name), version='main')
        for name in ('first', 'second')
    ]

    cached_cookbooks = manager.make_available_all(
        [manager.get_cookbook(source) for source in sources], fetch=False)

    # Roots, not contents: the recipes sit under source_path and the manifest
    # naming the cookbook sits at the root.
    assert [cached.path for cached in cached_cookbooks] == [
        manager.resolve_cached_resource(Cookbook(source=source)).path
        for source in sources
    ]


def test_weak_policy_falls_back_to_the_regex_cache_when_no_probe_hits():
    # Under the weak policy every candidate is probed on disk; nothing is there,
    # so resolution falls back to the first regex-matching candidate rather than
    # the plain writable default.
    manager = get_cookbook_manager(make_cache_configuration(
        CacheDirectory('/static-regex', is_read_only=True, regex='.*recipes.*'),
        CacheDirectory('/writable-default', is_read_only=False),
        resolution_policy=CacheResolutionPolicy.WEAK))

    cached_repository = manager.resolve_cached_resource(Cookbook(
        source=RequestedSource.for_repository('https://github.com/GolemCpp/recipes.git')))

    assert cached_repository.cache_root == '/static-regex'
    assert cached_repository.is_read_only is True
