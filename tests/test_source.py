import hashlib
import os
import re

from golemcpp.golem.source import make_revision_component
from golemcpp.golem import locator as locator_module
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source import Source
from golemcpp.golem.locator import Locator

def test_for_repository_preserves_location_and_resolved_version():
    source = Source.for_repository(
        'https://github.com/GolemCpp/recipes.git',
        ResolvedVersion(reference='stable', revision='cafebabe'))

    assert source.locator == Locator('https://github.com/GolemCpp/recipes.git')
    assert source.resolved == ResolvedVersion(reference='stable', revision='cafebabe')
    assert source.type == 'git'


def test_a_source_nothing_resolved_names_no_version():
    # The Null Object, as on Locator: a copied directory reaches this.
    assert not Source.for_repository('https://host/r.git').resolved
    assert not Source.for_directory('file:///tmp/mylib').resolved


def test_generate_id_accepts_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source_id = locator_module.generate_id(str(recipes_dir))

    assert source_id.startswith('recipes@fsys.')
    assert 'project' in source_id


def test_generate_id_uses_hash_for_local_path_uniqueness(tmp_path):
    parent_one = tmp_path / 'alpha' / 'recipes'
    parent_two = tmp_path / 'beta' / 'recipes'
    parent_one.mkdir(parents=True)
    parent_two.mkdir(parents=True)

    source_id_one = locator_module.generate_id(str(parent_one))
    source_id_two = locator_module.generate_id(str(parent_two))

    assert source_id_one != source_id_two
    assert source_id_one.startswith('recipes@fsys.')
    assert source_id_two.startswith('recipes@fsys.')


def test_for_directory_is_directory_type():
    source = Source.for_directory('file:///tmp/mylib')
    assert source.type == 'directory'
    assert source.locator == Locator('file:///tmp/mylib')


def test_make_revision_component_abbreviates_either_object_name_format():
    # 40 hex is SHA-1, 64 is SHA-256. Git is migrating, and both name a commit.
    assert make_revision_component('a' * 40) == 'aaaaaaaa'
    assert make_revision_component('b' * 64) == 'bbbbbbbb'


def test_make_revision_component_abbreviates_nothing_of_another_length():
    # Neither is an object name, so neither may be silently cut down to one.
    assert make_revision_component('c' * 39) == 'c' * 39 + '=' + \
        hashlib.sha256(('c' * 39).encode('utf-8')).hexdigest()[:8]
    assert make_revision_component('d' * 41).startswith('d' * 40 + '=')


def test_a_revision_that_looks_like_an_abbreviation_cannot_alias_a_commit():
    # A tag may be spelled like a short hash. It takes the other branch, so it
    # never collides with the commit whose object name starts the same way.
    assert make_revision_component('deadbeef') == 'deadbeef=2baf1f40'


def test_a_namespaced_revision_stays_one_path_component():
    component = make_revision_component('release/1.2.3')

    assert component == 'release~1.2.3=88ded651'
    assert '/' not in component and os.sep not in component


def test_revisions_a_filesystem_would_confuse_stay_distinct():
    # Each pair is one directory on some platform golem runs on -- NTFS and APFS
    # fold case, Windows drops a trailing dot -- so the digest is what keeps them
    # apart, and it is taken over the name as written.
    assert make_revision_component('V1.0') == 'v1.0=35a6fd96'
    assert make_revision_component('v1.0') == 'v1.0=fa8b919c'
    assert make_revision_component('v1.0.') == 'v1.0.=db5f409d'
    # And a name spelled with the substitute is not the name holding the original.
    assert make_revision_component('release/1.2.3') != make_revision_component('release-1.2.3')


def test_make_revision_component_is_always_a_usable_directory_name():
    for revision in ['main', 'V1.0', 'release/1.2.3', 'feature:x', 'a b', '..',
                     '...', 'café', 'x' * 200, 'a' * 40]:
        component = make_revision_component(revision)

        assert re.fullmatch(r'[0-9a-z._~-]*(=[0-9a-f]{8})?', component)
        # Ends in the digest or in an object name, so never in something Windows
        # would silently strip.
        assert not component.endswith('.') and not component.endswith(' ')
        assert component not in ('.', '..')


def test_get_id_matches_existing_format():
    source = Source.for_repository('https://github.com/GolemCpp/recipes.git')

    assert source.locator.get_id() == 'recipes@com.github.golemcpp'


# -- Source as a resource identity (recorded in a manifest) -----------------


def test_to_dict_round_trips_canonical_keys():
    source = Source(
        type='git', locator=Locator('https://github.com/nlohmann/json.git'),
        resolved=ResolvedVersion(reference='v3.12.0', revision='65ee6845'))

    data = source.to_dict()
    assert data == {'type': 'git', 'locator': 'https://github.com/nlohmann/json.git',
                    'resolved': {'reference': 'v3.12.0', 'revision': '65ee6845'}}
    assert Source.from_dict(data) == source


def test_every_field_round_trips_so_a_manifest_is_not_rewritten_each_resolve():
    # record_manifest compares a disk Source against the in-memory one, so a
    # field dropped by from_dict rewrites every manifest on every resolve.
    for source in [
            Source(type='git', locator=Locator('https://h/r.git'),
                   resolved=ResolvedVersion(reference='main', revision='cafebabe')),
            Source(type='directory', locator=Locator('file:///tmp/mylib')),
            Source(type='git', locator=Locator('https://h/r.git'),
                   resolved=ResolvedVersion(revision='cafebabe')),
    ]:
        assert Source.from_dict(source.to_dict()) == source


def test_from_manifest_reads_source_dict():
    from golemcpp.golem import resource_manifest

    manifest = resource_manifest.ResourceManifest.create(
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key='cppfront',
        source={'type': 'git', 'locator': 'https://host/u.git',
                'resolved': {'reference': 'v0.8.1', 'revision': 'cafebabe'}})
    source = Source.from_manifest(manifest)
    assert source.locator == Locator('https://host/u.git')
    assert source.resolved.reference == 'v0.8.1'


def test_label_prefers_locator_and_reference():
    assert Source(locator=Locator('https://x/json.git'),
                  resolved=ResolvedVersion(reference='v3.12.0')).label == \
        'https://x/json.git v3.12.0'
    assert Source.for_directory('file:///tmp/mylib').label == 'file:///tmp/mylib'
    assert Source().label == ''
