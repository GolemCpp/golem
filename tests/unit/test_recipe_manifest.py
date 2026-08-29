import json

import pytest

from golemcpp.golem import recipe_manifest
from golemcpp.golem.recipe_manifest import RecipeManifest


def write_manifest(tmp_path, content):
    '''Put a recipe.json holding content in a recipe directory, and name it.'''
    directory = tmp_path / '@boost'
    directory.mkdir()

    path = directory / recipe_manifest.RECIPE_MANIFEST_FILENAME
    path.write_text(
        content if isinstance(content, str) else json.dumps(content), encoding='utf-8'
    )

    return recipe_manifest.recipe_manifest_path(str(directory))


def test_a_recipe_declaring_nothing_reads_as_an_empty_manifest(tmp_path):
    # The common case: a recipe reachable by name alone declares nothing, so
    # asking for a manifest it does not hold is not asking for trouble.
    manifest = RecipeManifest.read(recipe_manifest.recipe_manifest_path(str(tmp_path)))

    assert manifest.locator == ''
    assert manifest.overrides == ''
    assert manifest.version == recipe_manifest.RECIPE_MANIFEST_VERSION


def test_a_manifest_names_where_the_source_is(tmp_path):
    path = write_manifest(
        tmp_path,
        {
            'version': 1,
            'locator': 'https://github.com/boostorg/boost.git',
        },
    )

    assert RecipeManifest.read(path).locator == 'https://github.com/boostorg/boost.git'


def test_a_manifest_naming_no_version_is_read_as_the_first(tmp_path):
    path = write_manifest(tmp_path, {'locator': 'https://host.xz/repo.git'})

    assert RecipeManifest.read(path).version == 1


def test_a_field_this_golem_does_not_know_is_ignored(tmp_path):
    # A cookbook is read by golems of several ages, therefore a field added
    # after this one shipped leaves the rest of the manifest usable.
    path = write_manifest(
        tmp_path,
        {
            'locator': 'https://host.xz/repo.git',
            'invented_later': {'anything': True},
        },
    )

    assert RecipeManifest.read(path).locator == 'https://host.xz/repo.git'


def test_a_newer_format_is_refused_rather_than_read_in_part(tmp_path):
    path = write_manifest(
        tmp_path, {'version': recipe_manifest.RECIPE_MANIFEST_VERSION + 1}
    )

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert 'this Golem reads 1' in str(refusal.value)


def test_a_refusal_names_the_origin_it_was_given(tmp_path):
    # A path under the cache names its cookbook by a hash, so a caller that
    # knows better says so, and the message is the caller's words.
    path = write_manifest(tmp_path, {'version': 99})

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path, origin="recipe '@boost' in cookbook '@x#v2'")

    assert "recipe '@boost' in cookbook '@x#v2'" in str(refusal.value)


def test_a_manifest_golem_cannot_parse_is_refused_not_taken_for_absent(tmp_path):
    # The whole reason this refuses where the resource manifest returns None: a
    # typo here would otherwise serve a recipe saying something else.
    path = write_manifest(tmp_path, '{"locator": ')

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert recipe_manifest.RECIPE_MANIFEST_FILENAME in str(refusal.value)


def test_a_manifest_that_names_no_fields_is_refused(tmp_path):
    path = write_manifest(tmp_path, ['https://host.xz/repo.git'])

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert 'a manifest names fields' in str(refusal.value)


def test_a_locator_written_as_an_identity_is_refused(tmp_path):
    # A recipe says where a source is. An identity says where to go looking,
    # therefore taking one here would leave nothing to fetch.
    path = write_manifest(tmp_path, {'locator': '@boost@boostorg@github.com'})

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert 'is an identity' in str(refusal.value)


def test_a_directory_named_like_an_identity_is_written_as_a_path(tmp_path):
    # Git's own escape, which is what tells the two apart everywhere else.
    path = write_manifest(tmp_path, {'locator': './@boost'})

    assert RecipeManifest.read(path).locator == './@boost'


def test_a_relative_locator_is_carried_as_it_was_written(tmp_path):
    # What it is relative to is the recipe directory, which a manifest matching
    # the file field for field cannot know.
    path = write_manifest(tmp_path, {'locator': '../vendor/boost'})

    assert RecipeManifest.read(path).locator == '../vendor/boost'


def test_a_recipe_names_the_one_it_is_a_delta_on(tmp_path):
    path = write_manifest(tmp_path, {'overrides': '@boost'})

    assert RecipeManifest.read(path).overrides == '@boost'


def test_an_overrides_that_names_no_identity_is_refused(tmp_path):
    # Nothing acts on it until recipes inherit, so this is the only moment its
    # author is still the one being told.
    path = write_manifest(
        tmp_path,
        {
            'overrides': 'https://github.com/boostorg/boost.git',
        },
    )

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert 'no identity' in str(refusal.value)


@pytest.mark.parametrize(
    'field, value',
    [
        ('locator', 12),
        ('overrides', ['@boost']),
        ('version', '1'),
        ('version', True),
    ],
)
def test_a_field_written_as_the_wrong_kind_of_value_is_refused(tmp_path, field, value):
    path = write_manifest(tmp_path, {field: value})

    with pytest.raises(RuntimeError):
        RecipeManifest.read(path)


def test_a_manifest_names_the_other_locators_its_source_is_served_from(tmp_path):
    path = write_manifest(
        tmp_path,
        {
            'locator': 'https://github.com/boostorg/boost.git',
            'mirrors': ['https://gitlab.com/boostorg/boost.git'],
        },
    )

    assert RecipeManifest.read(path).mirrors == (
        'https://gitlab.com/boostorg/boost.git',
    )


def test_a_manifest_naming_no_mirror_reads_as_holding_none(tmp_path):
    path = write_manifest(
        tmp_path,
        {
            'locator': 'https://github.com/boostorg/boost.git',
        },
    )

    assert RecipeManifest.read(path).mirrors == ()


def test_a_mirror_that_names_an_identity_is_refused(tmp_path):
    # The rule the locator carries: a recipe cannot delegate where its source
    # is to another recipe.
    path = write_manifest(
        tmp_path,
        {
            'locator': 'https://github.com/boostorg/boost.git',
            'mirrors': ['@boost@boostorg@gitlab.com'],
        },
    )

    with pytest.raises(RuntimeError) as refusal:
        RecipeManifest.read(path)

    assert 'is an identity' in str(refusal.value)


def test_a_manifest_may_name_mirrors_and_no_locator(tmp_path):
    # A source with no default remote: every location it can be reached at is
    # a mirror, and each is summoned by the identity it composes.
    path = write_manifest(
        tmp_path,
        {
            'mirrors': [
                'https://gitlab.com/boostorg/boost.git',
                'https://github.com/boostorg/boost.git',
            ],
        },
    )
    manifest = RecipeManifest.read(path)

    assert manifest.locator == ''
    assert len(manifest.mirrors) == 2


@pytest.mark.parametrize('mirrors', ['https://gitlab.com/b/b.git', {}, [12]])
def test_mirrors_written_as_the_wrong_kind_of_value_are_refused(tmp_path, mirrors):
    path = write_manifest(
        tmp_path,
        {
            'locator': 'https://github.com/boostorg/boost.git',
            'mirrors': mirrors,
        },
    )

    with pytest.raises(RuntimeError):
        RecipeManifest.read(path)
