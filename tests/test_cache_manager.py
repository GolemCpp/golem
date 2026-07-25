import os

from golemcpp.golem import cache
from golemcpp.golem import cache_manifest
from golemcpp.golem import cache_manager


def make_resource(cache_root, subdir, name, *, manifest_kind=None, identity=None, size=10):
    resource_root = os.path.join(cache_root, subdir, name)
    os.makedirs(resource_root, exist_ok=True)
    with open(os.path.join(resource_root, 'payload'), 'w', encoding='utf-8') as fp:
        fp.write('x' * size)
    if manifest_kind is not None:
        cache_manifest.write_manifest(
            resource_root=resource_root,
            kind=manifest_kind,
            cache_key=name,
            identity=identity or {})
    return resource_root


def make_manager(*cache_dirs):
    return cache_manager.CacheManager(locations=list(cache_dirs))


def test_scan_identifies_resources_and_unidentified(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY,
                  identity={'name': 'json', 'resolved_version': 'v3.12.0'})
    make_resource(root, cache.RECIPES_SUBDIR, 'mystery@host+main')  # no manifest

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    resources = manager.scan()

    assert len(resources) == 2
    by_key = {resource.cache_key: resource for resource in resources}

    dep = by_key['json@com.github.nlohmann+abc']
    assert dep.is_identified
    assert dep.kind == 'dependency'
    assert dep.identity['resolved_version'] == 'v3.12.0'
    assert dep.size_bytes > 0

    mystery = by_key['mystery@host+main']
    assert not mystery.is_identified
    # Kind is inferred from the subdirectory when unidentified.
    assert mystery.kind == 'recipes-repository'


def test_select_substring_and_regex(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    resources = manager.scan()

    substring = cache_manager.CacheManager.select(resources, 'nlohmann')
    assert [r.cache_key for r in substring] == ['json@com.github.nlohmann+abc']

    regex = cache_manager.CacheManager.select(resources, r'^fmt@', use_regex=True)
    assert [r.cache_key for r in regex] == ['fmt@com.github.fmtlib+def']


def test_filter_kind(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)
    make_resource(root, cache.TOOLS_SUBDIR, 'cppfront',
                  manifest_kind=cache_manifest.ResourceKind.TOOL,
                  identity={'name': 'cppfront', 'version': 'v0.8.1'})

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    resources = manager.scan()

    tools = cache_manager.CacheManager.filter_kind(resources, 'tool')
    assert [r.cache_key for r in tools] == ['cppfront']


def test_remove_resources_skips_read_only(tmp_path):
    writable_root = str(tmp_path / 'writable')
    read_only_root = str(tmp_path / 'readonly')
    make_resource(writable_root, cache.DEPENDENCIES_SUBDIR, 'a@h+1',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)
    make_resource(read_only_root, cache.DEPENDENCIES_SUBDIR, 'b@h+2',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)

    manager = make_manager(
        cache.CacheDir(location=writable_root, is_read_only=False),
        cache.CacheDir(location=read_only_root, is_read_only=True))
    resources = manager.scan()

    removed, skipped = cache_manager.CacheManager.remove_resources(resources)

    assert [r.cache_key for r in removed] == ['a@h+1']
    assert [r.cache_key for r in skipped] == ['b@h+2']
    assert not os.path.exists(os.path.join(writable_root, cache.DEPENDENCIES_SUBDIR, 'a@h+1'))
    assert os.path.exists(os.path.join(read_only_root, cache.DEPENDENCIES_SUBDIR, 'b@h+2'))


def test_list_cache_locations_reports_existence(tmp_path):
    existing = str(tmp_path / 'exists')
    os.makedirs(existing)
    missing = str(tmp_path / 'missing')

    manager = make_manager(
        cache.CacheDir(location=existing, is_read_only=False),
        cache.CacheDir(location=missing, is_read_only=True, regex='github'))
    summaries = manager.list_cache_locations()

    assert summaries[0].exists is True
    assert summaries[0].is_read_only is False
    assert summaries[1].exists is False
    assert summaries[1].is_read_only is True
    assert summaries[1].regex == 'github'


def test_scan_detects_legacy_flat_entries_as_unidentified(tmp_path):
    root = str(tmp_path / 'cache')
    # A normal resource under a known subdirectory.
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)
    # A legacy flat resource stored directly at the cache root, no manifest.
    make_resource(root, '', 'mylogger@fsys.home+-')

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
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
    cache_manifest.write_manifest(
        resource_root=resource_root,
        kind=cache_manifest.ResourceKind.DEPENDENCY,
        cache_key='json@com.github.nlohmann+abc',
        identity={})

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    resources = manager.scan()

    assert len(resources) == 1
    resource = resources[0]
    assert resource.is_identified is True
    assert resource.kind == cache_manifest.ResourceKind.DEPENDENCY.value
    # The real cache_key comes from the manifest, not the flat hashed dir name.
    assert resource.cache_key == 'json@com.github.nlohmann+abc'


def test_scan_does_not_treat_known_subdirs_as_resources(tmp_path):
    root = str(tmp_path / 'cache')
    make_resource(root, cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  manifest_kind=cache_manifest.ResourceKind.DEPENDENCY)
    # Create empty known subdirs; none of them should show up as a resource.
    for subdir in cache.RESOURCE_SUBDIRS:
        os.makedirs(os.path.join(root, subdir), exist_ok=True)

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    keys = {resource.cache_key for resource in manager.scan()}

    assert keys == {'json@h+abc'}
    assert not (keys & set(cache.RESOURCE_SUBDIRS))


def test_scan_ignores_stray_files_at_cache_root(tmp_path):
    root = str(tmp_path / 'cache')
    os.makedirs(root)
    with open(os.path.join(root, 'stray.txt'), 'w', encoding='utf-8') as fp:
        fp.write('junk')

    manager = make_manager(cache.CacheDir(location=root, is_read_only=False))
    assert manager.scan() == []
