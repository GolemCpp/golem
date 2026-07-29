import json
import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import resource_manifest


def test_resource_kind_subdir_mapping():
    assert resource_manifest.ResourceKind.DEPENDENCY.subdir == cache_configuration.DEPENDENCIES_SUBDIR
    assert resource_manifest.ResourceKind.RECIPES_REPOSITORY.subdir == cache_configuration.RECIPES_SUBDIR
    assert resource_manifest.ResourceKind.OVERRIDES_REPOSITORY.subdir == cache_configuration.OVERRIDES_SUBDIR
    assert resource_manifest.ResourceKind.TOOL.subdir == cache_configuration.TOOLS_SUBDIR

    assert resource_manifest.ResourceKind.from_subdir('dependencies') == resource_manifest.ResourceKind.DEPENDENCY
    assert resource_manifest.ResourceKind.from_subdir('unknown') is None


def test_write_and_read_manifest_roundtrip(tmp_path):
    root = tmp_path / 'json@com.github.nlohmann+65ee6845'
    root.mkdir()

    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        cache_key=root.name,
        source={'type': 'git', 'location': 'u', 'reference': 'v3.12.0'},
    )

    manifest_file = root / resource_manifest.MANIFEST_FILENAME
    assert manifest_file.exists()

    manifest = resource_manifest.ResourceManifest.read_from_root(str(root))
    assert manifest.kind == 'dependency'
    assert manifest.cache_key == root.name
    assert manifest.version == resource_manifest.MANIFEST_VERSION
    assert manifest.source == {'type': 'git', 'location': 'u', 'reference': 'v3.12.0'}
    assert manifest.created_at
    assert manifest.last_used_at == manifest.created_at
    assert manifest.golem_version

    data = json.loads(manifest_file.read_text(encoding='utf-8'))
    assert 'source' in data


def test_read_missing_manifest_returns_none(tmp_path):
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None


def test_read_invalid_manifest_returns_none(tmp_path):
    manifest_file = tmp_path / resource_manifest.MANIFEST_FILENAME
    manifest_file.write_text('not-json', encoding='utf-8')
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None

    manifest_file.write_text(json.dumps({'no_kind': True}), encoding='utf-8')
    assert resource_manifest.ResourceManifest.read_from_root(str(tmp_path)) is None


def test_touch_last_used_updates_timestamp(tmp_path):
    root = tmp_path / 'resource'
    root.mkdir()
    resource_manifest.write_manifest(
        resource_root=str(root),
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key='cppfront',
        source={'type': 'git', 'location': 'u', 'reference': 'v0.8.1'},
    )

    manifest_before = resource_manifest.ResourceManifest.read_from_root(str(root))
    # Force a distinguishable earlier timestamp, then touch.
    manifest_before.last_used_at = '2000-01-01T00:00:00+00:00'
    manifest_before.write_to_root(str(root))

    resource_manifest.touch_last_used(str(root))

    manifest_after = resource_manifest.ResourceManifest.read_from_root(str(root))
    assert manifest_after.last_used_at > '2000-01-01T00:00:00+00:00'


def test_touch_last_used_no_manifest_is_noop(tmp_path):
    # Should not raise when there is no manifest.
    resource_manifest.touch_last_used(str(tmp_path))
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
