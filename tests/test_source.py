import hashlib
import os
import re

import pytest

from golemcpp.golem.source import format_location
from golemcpp.golem.source import make_revision_component
from golemcpp.golem.source import parse_location
from golemcpp.golem.source import Source
from golemcpp.golem.setting_descriptor import SettingProcessingContext


def test_parse_normalizes_and_classifies_local_directory(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source = Source.parse('recipes', str(project_dir))

    assert source.location == recipes_dir.resolve().as_uri()
    assert source.type == 'directory'


def test_for_repository_preserves_location_and_reference():
    source = Source.for_repository(
        'https://github.com/GolemCpp/recipes.git', reference='stable')

    assert source.location == 'https://github.com/GolemCpp/recipes.git'
    assert source.reference == 'stable'
    assert source.type == 'git'


def test_parse_parses_encoded_local_directory_path(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1'
    recipes_dir.mkdir(parents=True)

    source = Source.parse('recipes #1', str(project_dir))

    assert source.get_local_path() == str(recipes_dir.resolve())


def test_parse_normalizes_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source = Source.parse('recipes', str(project_dir))

    assert source.location == recipes_dir.resolve().as_uri()
    assert source.get_local_path() == str(recipes_dir.resolve())


def test_generate_id_accepts_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source_id = Source.generate_id(str(recipes_dir))

    assert source_id.startswith('recipes@fsys.')
    assert 'project' in source_id


def test_generate_id_uses_hash_for_local_path_uniqueness(tmp_path):
    parent_one = tmp_path / 'alpha' / 'recipes'
    parent_two = tmp_path / 'beta' / 'recipes'
    parent_one.mkdir(parents=True)
    parent_two.mkdir(parents=True)

    source_id_one = Source.generate_id(str(parent_one))
    source_id_two = Source.generate_id(str(parent_two))

    assert source_id_one != source_id_two
    assert source_id_one.startswith('recipes@fsys.')
    assert source_id_two.startswith('recipes@fsys.')


def test_parse_classifies_local_non_git_directory(tmp_path):
    project_dir = tmp_path / 'project'
    lib_dir = project_dir / 'lib'
    lib_dir.mkdir(parents=True)

    source = Source.parse('lib', str(project_dir))

    assert source.type == 'directory'
    assert source.location == lib_dir.resolve().as_uri()


def test_parse_classifies_git_directory_as_git(tmp_path):
    project_dir = tmp_path / 'project'
    recipes_dir = project_dir / 'recipes'
    git_dir = recipes_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    source = Source.parse('recipes', str(project_dir))

    assert source.type == 'git'


# -- a location may spell its kind rather than leave it to detection --------


def test_parse_honours_an_explicit_git_kind_on_a_plain_directory(tmp_path):
    project_dir = tmp_path / 'project'
    lib_dir = project_dir / 'lib'
    lib_dir.mkdir(parents=True)

    source = Source.parse('git+lib', str(project_dir))

    assert source.type == 'git'
    assert source.location == lib_dir.resolve().as_uri()


def test_parse_honours_an_explicit_directory_kind_on_a_git_checkout(tmp_path):
    project_dir = tmp_path / 'project'
    recipes_dir = project_dir / 'recipes'
    git_dir = recipes_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    source = Source.parse('directory+recipes', str(project_dir))

    assert source.type == 'directory'


def test_parse_honours_an_explicit_kind_on_a_remote_url(tmp_path):
    source = Source.parse('git+https://github.com/GolemCpp/recipes.git', str(tmp_path))

    assert source.type == 'git'
    assert source.location == 'https://github.com/GolemCpp/recipes.git'


def test_parse_refuses_an_unknown_kind(tmp_path):
    with pytest.raises(ValueError) as error:
        Source.parse('gti+https://github.com/GolemCpp/recipes.git', str(tmp_path))

    assert "unknown source kind 'gti'" in str(error.value)
    assert 'git+' in str(error.value)
    assert 'directory+' in str(error.value)


def test_parse_does_not_read_a_plus_inside_a_url_as_a_kind(tmp_path):
    source = Source.parse('https://host/a+b.git', str(tmp_path))

    assert source.type == 'git'
    assert source.location == 'https://host/a+b.git'


def test_format_location_always_spells_the_kind():
    context = SettingProcessingContext(project_dir=None)

    assert format_location(
        Source.for_repository('https://host/r.git'), context) == 'git+https://host/r.git'
    assert format_location(
        Source.for_directory('file:///tmp/mylib'), context) == 'directory+file:///tmp/mylib'


def test_parse_location_round_trips_through_format_location(tmp_path):
    context = SettingProcessingContext(project_dir=str(tmp_path))
    spelled = format_location(parse_location('https://host/r.git', context), context)

    assert spelled == 'git+https://host/r.git'
    assert parse_location(spelled, context) == parse_location('https://host/r.git', context)


def test_for_directory_is_directory_type():
    source = Source.for_directory('/tmp/mylib')
    assert source.type == 'directory'
    assert source.location == '/tmp/mylib'


def test_cache_key_uses_source_id_and_reference():
    source = Source.for_repository(
        'https://github.com/GolemCpp/recipes.git', reference='main')

    assert source.get_cache_key() == 'recipes@com.github.golemcpp+main=0d6e4079'


def test_cache_key_abbreviates_an_object_name_the_way_git_does():
    source = Source.for_repository(
        'https://github.com/nlohmann/json.git',
        reference='65ee68451d8eb2b5f3a30b410476ab83deb3289b')

    # No digest to disambiguate: an object name already identifies itself, and a
    # component without one is by construction a commit.
    assert source.get_cache_key() == 'json@com.github.nlohmann+65ee6845'


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

    assert component == 'release-1.2.3=88ded651'
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

        assert re.fullmatch(r'[0-9a-z._-]*(=[0-9a-f]{8})?', component)
        # Ends in the digest or in an object name, so never in something Windows
        # would silently strip.
        assert not component.endswith('.') and not component.endswith(' ')
        assert component not in ('.', '..')


def test_get_id_matches_existing_format():
    source = Source.for_repository('https://github.com/GolemCpp/recipes.git')

    assert source.get_id() == 'recipes@com.github.golemcpp'


# -- Source as a resource identity (recorded in a manifest) -----------------


def test_to_dict_round_trips_canonical_keys():
    source = Source(
        type='git', location='https://github.com/nlohmann/json.git',
        reference='v3.12.0')

    data = source.to_dict()
    assert data == {'type': 'git', 'location': 'https://github.com/nlohmann/json.git',
                    'reference': 'v3.12.0'}
    assert Source.from_dict(data) == source


def test_from_manifest_reads_source_dict():
    from golemcpp.golem import resource_manifest

    manifest = resource_manifest.ResourceManifest.create(
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key='cppfront',
        source={'type': 'git', 'location': 'u', 'reference': 'v0.8.1'})
    source = Source.from_manifest(manifest)
    assert source.location == 'u'
    assert source.reference == 'v0.8.1'


def test_label_prefers_location_and_reference():
    assert Source(location='https://x/json.git', reference='v3.12.0').label == \
        'https://x/json.git v3.12.0'
    assert Source.for_directory('/tmp/mylib').label == '/tmp/mylib'
    assert Source(location='').label == ''
