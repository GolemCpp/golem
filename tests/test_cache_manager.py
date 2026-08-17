import os

import pytest

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import resource_manifest
from golemcpp.golem import cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


def make_resource(cache_root, subdir, name, *, manifest_kind=None, source=None, size=10):
    resource_root = os.path.join(cache_root, subdir, name)
    os.makedirs(resource_root, exist_ok=True)
    with open(os.path.join(resource_root, 'payload'), 'w', encoding='utf-8') as fp:
        fp.write('x' * size)
    if manifest_kind is not None:
        resource_manifest.write_manifest(
            resource_root=resource_root,
            kind=manifest_kind,
            cache_key=name,
            source=source or {})
    return resource_root


def make_manager(*cache_dirs):
    return cache_manager.get_cache_manager(make_cache_configuration(*cache_dirs))


def test_scan_identifies_resources_and_unidentified(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY,
                  source={'type': 'git', 'location': 'u', 'reference': 'v3.12.0'})
    make_resource(root, cache_configuration.COOKBOOKS_SUBDIR, 'mystery@host+main')  # no manifest

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    resources = manager.scan()

    assert len(resources) == 2
    by_key = {resource.cache_key: resource for resource in resources}

    dep = by_key['json@com.github.nlohmann+abc']
    assert dep.is_identified
    assert dep.kind == 'dependency'
    assert dep.source['reference'] == 'v3.12.0'
    assert dep.size_bytes > 0

    mystery = by_key['mystery@host+main']
    assert not mystery.is_identified
    # Kind is inferred from the subdirectory when unidentified.
    assert mystery.kind == 'cookbook'


def test_select_substring_and_regex(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    resources = manager.scan()

    substring = cache_manager.CacheManager.select(resources, 'nlohmann')
    assert [r.cache_key for r in substring] == ['json@com.github.nlohmann+abc']

    regex = cache_manager.CacheManager.select(resources, r'^fmt@', use_regex=True)
    assert [r.cache_key for r in regex] == ['fmt@com.github.fmtlib+def']


def test_filter_kind(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)
    make_resource(root, cache_configuration.TOOLS_SUBDIR, 'cppfront',
                  manifest_kind=resource_manifest.ResourceKind.TOOL,
                  source={'type': 'git', 'location': 'u', 'reference': 'v0.8.1'})

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    resources = manager.scan()

    tools = cache_manager.CacheManager.filter_kind(resources, 'tool')
    assert [r.cache_key for r in tools] == ['cppfront']


def test_remove_resources_skips_read_only(tmp_path):
    writable_root = str(tmp_path / 'writable')
    read_only_root = str(tmp_path / 'readonly')
    make_resource(writable_root, cache_configuration.DEPENDENCIES_SUBDIR, 'a@h+1',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)
    make_resource(read_only_root, cache_configuration.DEPENDENCIES_SUBDIR, 'b@h+2',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)

    manager = make_manager(
        cache_directory.CacheDirectory(location=writable_root, is_read_only=False),
        cache_directory.CacheDirectory(location=read_only_root, is_read_only=True))
    resources = manager.scan()

    removed, skipped = cache_manager.CacheManager.remove_resources(resources)

    assert [r.cache_key for r in removed] == ['a@h+1']
    assert [r.cache_key for r in skipped] == ['b@h+2']
    assert not os.path.exists(os.path.join(writable_root, cache_configuration.DEPENDENCIES_SUBDIR, 'a@h+1'))
    assert os.path.exists(os.path.join(read_only_root, cache_configuration.DEPENDENCIES_SUBDIR, 'b@h+2'))


def test_list_cache_locations_reports_existence(tmp_path):
    existing = str(tmp_path / 'exists')
    os.makedirs(existing)
    missing = str(tmp_path / 'missing')

    manager = make_manager(
        cache_directory.CacheDirectory(location=existing, is_read_only=False),
        cache_directory.CacheDirectory(location=missing, is_read_only=True, regex='github'))
    summaries = manager.list_cache_locations()

    assert summaries[0].exists is True
    assert summaries[0].is_read_only is False
    assert summaries[1].exists is False
    assert summaries[1].is_read_only is True
    assert summaries[1].regex == 'github'


def test_scan_detects_legacy_flat_entries_as_unidentified(tmp_path):
    root = str(tmp_path / 'cache')
    # A normal resource under a known subdirectory.
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)
    # A legacy flat resource stored directly at the cache root, no manifest.
    make_resource(root, '', 'mylogger@fsys.home+-')

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    by_key = {resource.cache_key: resource for resource in manager.scan()}

    assert set(by_key) == {'json@h+abc', 'mylogger@fsys.home+-'}

    legacy = by_key['mylogger@fsys.home+-']
    assert legacy.is_identified is False
    assert legacy.kind == cache_manager.UNKNOWN_KIND
    assert legacy.subdir == ''
    assert legacy.size_bytes > 0


def test_scan_identifies_top_level_entries_via_manifest(tmp_path):
    root = str(tmp_path / 'cache')
    # A minimized resource stored flat at the cache root under a short hashed
    # name. It is identified purely by its manifest, which is the source of truth
    # for identity regardless of where the resource lives.
    resource_root = make_resource(root, '', 'a1b2c3d4')
    resource_manifest.write_manifest(
        resource_root=resource_root,
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        cache_key='json@com.github.nlohmann+abc',
        source={})

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    resources = manager.scan()

    assert len(resources) == 1
    resource = resources[0]
    assert resource.is_identified is True
    assert resource.kind == resource_manifest.ResourceKind.DEPENDENCY.value
    # The real cache_key comes from the manifest, not the flat hashed dir name.
    assert resource.cache_key == 'json@com.github.nlohmann+abc'


def test_scan_does_not_treat_known_subdirs_as_resources(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=resource_manifest.ResourceKind.DEPENDENCY)
    # Create empty known subdirs; none of them should show up as a resource.
    for subdir in cache_configuration.RESOURCE_SUBDIRS:
        os.makedirs(os.path.join(root, subdir), exist_ok=True)

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    keys = {resource.cache_key for resource in manager.scan()}

    assert keys == {'json@h+abc'}
    assert not (keys & set(cache_configuration.RESOURCE_SUBDIRS))


def test_scan_ignores_stray_files_at_cache_root(tmp_path):
    root = str(tmp_path / 'cache')
    os.makedirs(root)
    with open(os.path.join(root, 'stray.txt'), 'w', encoding='utf-8') as fp:
        fp.write('junk')

    manager = make_manager(cache_directory.CacheDirectory(location=root, is_read_only=False))
    assert manager.scan() == []


# -- the per-resource API (resolving one resource rather than scanning) ------


def make_tool_resource():
    source = Source.for_repository('https://example.com/tool.git', reference='v1')
    return Resource(kind=ResourceKind.TOOL, cache_key='demo', source=source)


def make_classic_manager(*locations):
    return cache_manager.get_cache_manager(
        make_cache_configuration(*locations, minimization_enabled=False))


def test_resolve_and_locate(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_classic_manager(cache_dir)
    resource = make_tool_resource()

    assert manager.resolve_cache_directory(resource).location == str(tmp_path / 'cache')
    assert manager.get_resource_location(cache_dir, resource) == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.TOOLS_SUBDIR, 'demo')
    assert manager.resolve_cached_resource(resource).exists() is False


def test_write_and_read_source(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_classic_manager(cache_dir)
    resource = make_tool_resource()
    root = manager.get_resource_location(cache_dir, resource)
    os.makedirs(root)

    manager.write_manifest(root, resource)

    manifest = ResourceManifest.read_from_root(root)
    assert manifest.kind == ResourceKind.TOOL.value
    assert manifest.cache_key == 'demo'
    source = manager.read_manifest_source(root)
    assert source.location == 'https://example.com/tool.git'
    assert source.reference == 'v1'
    assert manager.resolve_cached_resource(resource).exists() is True


def test_resolve_cached_resource_reads_size_and_manifest_on_demand(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_classic_manager(cache_dir)
    resource = make_tool_resource()
    root = manager.get_resource_location(cache_dir, resource)
    os.makedirs(root)
    with open(os.path.join(root, 'payload.txt'), 'w') as fileout:
        fileout.write('hi')
    manager.write_manifest(root, resource)

    # Both are opt-in: resolving alone reports neither.
    plain = manager.resolve_cached_resource(resource)
    assert plain.size_bytes == 0
    assert plain.manifest is None

    detailed = manager.resolve_cached_resource(resource, compute_size=True, read_manifest=True)
    assert detailed.path == root
    assert detailed.cache_key == 'demo'
    assert detailed.kind == ResourceKind.TOOL.value
    assert detailed.size_bytes > 0
    assert detailed.source['location'] == 'https://example.com/tool.git'


def test_staged_install_swaps_atomically(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    manager = make_classic_manager(cache_dir)
    resource = make_tool_resource()

    def populate(staging_root):
        with open(os.path.join(staging_root, 'payload.txt'), 'w') as fileout:
            fileout.write('hi')

    root = manager.staged_install(
        manager._make_cached_resource(cache_dir, resource), populate)

    assert os.path.isfile(os.path.join(root, 'payload.txt'))
    assert ResourceManifest.read_from_root(root) is not None
    assert not os.path.exists(root + '.tmp')


def test_staged_install_refuses_a_scanned_resource(tmp_path):
    cache_root = str(tmp_path / 'cache')
    make_resource(cache_root, cache_configuration.TOOLS_SUBDIR, 'demo',
                  manifest_kind=ResourceKind.TOOL)
    manager = make_classic_manager(
        cache_directory.CacheDirectory(location=cache_root))

    # A scanned entry names itself from its own manifest, so it has no resource
    # to write a fresh manifest from: installing through it is a programming error.
    scanned = manager.scan(compute_size=False)[0]

    with pytest.raises(ValueError):
        manager.staged_install(scanned, lambda staging_root: None)


def test_remove_resources_honors_read_only_guard(tmp_path):
    writable = cache_directory.CacheDirectory(location=str(tmp_path / 'w'))
    read_only = cache_directory.CacheDirectory(location=str(tmp_path / 'ro'), is_read_only=True)
    resource = make_tool_resource()

    manager = make_classic_manager(writable)
    cached = manager.resolve_cached_resource(resource)
    os.makedirs(cached.path)

    removed, skipped = manager.remove_resources([cached])

    assert [entry.path for entry in removed] == [cached.path]
    assert skipped == []
    assert not os.path.exists(cached.path)

    ro_manager = make_classic_manager(read_only)
    ro_cached = ro_manager.resolve_cached_resource(resource)
    os.makedirs(ro_cached.path)

    removed, skipped = ro_manager.remove_resources([ro_cached])

    assert removed == []
    assert [entry.path for entry in skipped] == [ro_cached.path]
    assert os.path.exists(ro_cached.path)


def test_remove_resources_skips_a_resource_that_is_already_gone(tmp_path):
    manager = make_classic_manager(
        cache_directory.CacheDirectory(location=str(tmp_path / 'w')))

    cached = manager.resolve_cached_resource(make_tool_resource())

    assert manager.remove_resources([cached]) == ([], [])
