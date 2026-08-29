import json
import os

from support import make_source
from golemcpp.golem import cache_configuration
from golemcpp.golem import resource_manifest


def test_resource_kind_subdir_mapping():
    assert (
        resource_manifest.ResourceKind.DEPENDENCY.subdir
        == cache_configuration.DEPENDENCIES_SUBDIR
    )
    assert (
        resource_manifest.ResourceKind.COOKBOOK.subdir
        == cache_configuration.COOKBOOKS_SUBDIR
    )
    assert (
        resource_manifest.ResourceKind.OVERLAY.subdir
        == cache_configuration.OVERLAYS_SUBDIR
    )
    assert (
        resource_manifest.ResourceKind.TOOL.subdir == cache_configuration.TOOLS_SUBDIR
    )

    assert (
        resource_manifest.ResourceKind.from_subdir('dependencies')
        == resource_manifest.ResourceKind.DEPENDENCY
    )
    assert resource_manifest.ResourceKind.from_subdir('unknown') is None


def test_write_and_read_manifest_roundtrip(tmp_path):
    root = tmp_path / '@json@nlohmann@github.com#65ee684'
    root.mkdir()

    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        cache_key=root.name,
        source=make_source(reference='v3.12.0'),
    )

    manifest_file = root / resource_manifest.MANIFEST_FILENAME
    assert manifest_file.exists()

    manifest = resource_manifest.ResourceManifest.read_from_root(str(root))
    assert manifest.kind == 'dependency'
    assert manifest.cache_key == root.name
    assert manifest.version == resource_manifest.MANIFEST_VERSION
    assert manifest.source == make_source(reference='v3.12.0')
    assert manifest.created_at
    assert manifest.last_used_at == manifest.created_at
    assert manifest.golem_version

    data = json.loads(manifest_file.read_text(encoding='utf-8'))
    assert 'source' in data


def test_what_the_fetch_left_survives_the_roundtrip(tmp_path):
    # The source names what was asked for, `fetched` names what the root ended up
    # holding, and the two travel together.
    root = tmp_path / 'r'
    root.mkdir()

    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.COOKBOOK,
        cache_key=root.name,
        source=make_source(reference='main'),
        fetched={'head': 'cafebabe'},
    )

    manifest = resource_manifest.ResourceManifest.read_from_root(str(root))
    assert manifest.fetched == {'head': 'cafebabe'}
    assert json.loads(
        (root / resource_manifest.MANIFEST_FILENAME).read_text(encoding='utf-8')
    )['fetched'] == {'head': 'cafebabe'}


def test_a_manifest_written_without_a_fetch_reads_back_empty(tmp_path):
    # A copied directory is not fetched at all, and an older manifest predates the
    # field entirely: both read back as nothing recorded rather than as missing.
    root = tmp_path / 'r'
    root.mkdir()

    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.OVERLAY,
        cache_key=root.name,
        source=make_source(
            locator='file:///somewhere',
            reference='',
            revision='',
            source_type='directory',
        ),
    )

    assert resource_manifest.ResourceManifest.read_from_root(str(root)).fetched == {}


def test_read_missing_manifest_returns_none(tmp_path):
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None


def test_read_invalid_manifest_returns_none(tmp_path):
    manifest_file = tmp_path / resource_manifest.MANIFEST_FILENAME
    manifest_file.write_text('not-json', encoding='utf-8')
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None

    manifest_file.write_text(json.dumps({'no_kind': True}), encoding='utf-8')
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None


def test_read_manifest_of_an_unknown_kind_returns_none(tmp_path):
    # A kind an earlier Golem version wrote and this one no longer has. Nothing
    # can be done with such a resource, so it reads as no manifest at all even
    # though everything else about it is well-formed.
    manifest_file = tmp_path / resource_manifest.MANIFEST_FILENAME
    manifest_file.write_text(
        json.dumps(
            {
                'kind': 'recipes-repository',
                'cache_key': '@recipes@@h#main',
                'source': make_source(reference='main'),
            }
        ),
        encoding='utf-8',
    )
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None

    assert (
        resource_manifest.ResourceKind.from_name('dependency')
        == resource_manifest.ResourceKind.DEPENDENCY
    )
    assert resource_manifest.ResourceKind.from_name('overrides-repository') is None


def test_read_manifest_naming_no_source_returns_none(tmp_path):
    # A manifest that cannot say where its resource came from identifies nothing.
    # An earlier Golem version spelled a source `location`/`reference`, which is
    # what such a manifest holds today.
    manifest_file = tmp_path / resource_manifest.MANIFEST_FILENAME
    for source in (
        {},
        [],
        {'type': 'git'},
        {
            'type': 'git',
            'location': 'https://github.com/nlohmann/json.git',
            'reference': 'v3.12.0',
        },
        # A locator has to be settled: a bare path never identified one.
        {'type': 'directory', 'locator': '../somewhere'},
    ):
        manifest_file.write_text(
            json.dumps(
                {'kind': 'dependency', 'cache_key': '@json@@h#abc', 'source': source}
            ),
            encoding='utf-8',
        )
        assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None

    manifest_file.write_text(
        json.dumps(
            {'kind': 'dependency', 'cache_key': '@json@@h#abc', 'source': make_source()}
        ),
        encoding='utf-8',
    )
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is not None


def test_touch_last_used_updates_timestamp(tmp_path):
    root = tmp_path / 'resource'
    root.mkdir()
    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key='cppfront',
        source=make_source(reference='v0.8.1'),
    )

    manifest_before = resource_manifest.ResourceManifest.read_from_root(str(root))
    # Force a distinguishable earlier timestamp, then touch.
    manifest_before.last_used_at = '2000-01-01T00:00:00+00:00'
    manifest_before.write_to_root(str(root))

    resource_manifest.ResourceManifest.touch(str(root))

    manifest_after = resource_manifest.ResourceManifest.read_from_root(str(root))
    assert manifest_after.last_used_at > '2000-01-01T00:00:00+00:00'


def test_touch_last_used_no_manifest_is_noop(tmp_path):
    # Should not raise when there is no manifest.
    resource_manifest.ResourceManifest.touch(str(tmp_path))
    assert not (tmp_path / resource_manifest.MANIFEST_FILENAME).exists()


def test_manifest_write_is_atomic_no_temp_left(tmp_path):
    root = tmp_path / 'resource'
    root.mkdir()
    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        cache_key='x',
        source={},
    )
    leftovers = [name for name in os.listdir(root) if name.endswith('.tmp')]
    assert leftovers == []
