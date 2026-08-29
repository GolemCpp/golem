from types import SimpleNamespace

import pytest

from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.recipe import Recipe
from golemcpp.golem.recipe_manifest import RecipeManifest
from golemcpp.golem.source_id import SourceId


def declaration(tmp_path, locator='', project=False, mirrors=(), name='@json'):
    '''Build a declaration on disk, since a project file is read off it.'''
    directory = tmp_path / name
    directory.mkdir(exist_ok=True)

    if project:
        (directory / 'golemfile.py').write_text('def configure(p): pass')

    return DeclaredRecipe(
        directory=str(directory),
        cookbook=SimpleNamespace(source_path=str(tmp_path), cache_key='base'),
        rung=SourceId.parse('@json'),
        manifest=RecipeManifest(locator=locator, mirrors=mirrors),
    )


def layered(*declarations):
    '''A recipe made of several declarations, most derived first.'''
    return Recipe(chain=declarations)


GITHUB = 'https://github.com/nlohmann/json.git'
GITLAB = 'https://gitlab.com/nlohmann/json.git'
FORK = 'https://git.corp/fork/json.git'


def mirrored(tmp_path):
    '''A recipe served from github, and from a gitlab mirror of it.'''
    return Recipe.resolve(
        declaration(tmp_path, locator=GITHUB, mirrors=(GITLAB,)))


def test_a_recipe_answers_where_its_source_is(tmp_path):
    recipe = Recipe.resolve(declaration(tmp_path, locator='https://host.xz/j.git'))

    assert recipe.locator == 'https://host.xz/j.git'


def test_a_recipe_answers_where_its_project_file_is(tmp_path):
    recipe = Recipe.resolve(declaration(tmp_path, project=True))

    assert recipe.project_directory == str(tmp_path / '@json')


def test_a_recipe_saying_neither_answers_nothing(tmp_path):
    assert not Recipe.resolve(declaration(tmp_path))


def test_a_recipe_saying_either_answers_something(tmp_path):
    assert Recipe.resolve(declaration(tmp_path, locator='https://host.xz/j.git'))
    assert Recipe.resolve(declaration(tmp_path, project=True))


def test_asking_for_a_locator_a_recipe_does_not_name_is_refused(tmp_path):
    # The caller was pointed at an identity, therefore the recipe is the only
    # thing that could say what to clone.
    recipe = Recipe.resolve(declaration(tmp_path, project=True))

    with pytest.raises(RuntimeError) as refusal:
        recipe.require_locators()

    assert "recipe '@json' in cookbook 'base'" in str(refusal.value)
    assert 'names no locator' in str(refusal.value)


def test_asking_for_a_project_file_a_recipe_does_not_hold_is_refused(tmp_path):
    # The caller has no golemfile of its own, therefore a recipe that only says
    # where its source is answers somebody else's question.
    recipe = Recipe.resolve(declaration(tmp_path, locator='https://host.xz/j.git'))

    with pytest.raises(RuntimeError) as refusal:
        recipe.require_project_directory()

    assert "recipe '@json' in cookbook 'base'" in str(refusal.value)
    assert 'holds no project file' in str(refusal.value)


def test_what_a_recipe_answers_is_returned_rather_than_refused(tmp_path):
    recipe = Recipe.resolve(
        declaration(tmp_path, locator='https://host.xz/j.git', project=True))

    assert recipe.require_locators() == ('https://host.xz/j.git',)
    assert recipe.require_project_directory() == str(tmp_path / '@json')


def test_a_recipe_names_the_declaration_that_answered(tmp_path):
    # One long until a recipe can be a delta on another, and the chain is what
    # a resolution records.
    declared = declaration(tmp_path, project=True)

    assert Recipe.resolve(declared).chain == (declared,)
    assert Recipe.resolve(declared).served_by is declared


def test_an_identity_naming_a_mirror_is_answered_by_that_mirror(tmp_path):
    identity = SourceId.parse('@json@nlohmann@gitlab.com')

    assert mirrored(tmp_path).locator_for(identity) == GITLAB


def test_an_identity_naming_no_host_is_answered_by_the_primary(tmp_path):
    # It contradicts nothing, therefore it matches the mirror too: the declared
    # order is the whole of what decides, not a tiebreak.
    recipe = mirrored(tmp_path)

    assert recipe.locator_for(SourceId.parse('@json')) == GITHUB
    assert recipe.locator_for(SourceId.parse('@json@nlohmann')) == GITHUB


def test_an_identity_every_locator_contradicts_is_answered_by_none(tmp_path):
    identity = SourceId.parse('@json@somefork@github.com')

    assert mirrored(tmp_path).locator_for(identity) == ''


def test_a_recipe_lists_its_mirrors_after_where_its_source_is(tmp_path):
    assert mirrored(tmp_path).locators == (GITHUB, GITLAB)
    # The first of them is still where the source is.
    assert mirrored(tmp_path).locator == GITHUB


def test_a_mirror_written_relative_hangs_off_the_recipe_directory(tmp_path):
    # The one anchor a cookbook author can see, the same rule the locator has.
    (tmp_path / 'vendor').mkdir()
    recipe = Recipe.resolve(
        declaration(tmp_path, locator='https://host.xz/j.git',
                    mirrors=('../vendor',)))

    assert recipe.locators[1] == str(tmp_path / 'vendor')


def test_a_recipe_naming_only_mirrors_names_no_remote_to_clone(tmp_path):
    # `locator` is the default source and `mirrors` are a convenience, so a
    # recipe declaring only mirrors advertises no remote of its own.
    recipe = Recipe.resolve(declaration(tmp_path, mirrors=(GITLAB, GITHUB)))

    assert recipe.locator == ''
    assert recipe.mirrors == (GITLAB, GITHUB)
    # It still names somewhere to clone from, therefore it answers as a recipe.
    assert recipe.locators == (GITLAB, GITHUB)
    assert recipe


def test_a_recipe_naming_only_mirrors_serves_no_identity_asking_for_none(tmp_path):
    # `@json` names the recipe and nothing more, and there is no official
    # remote to hand it. A mirror is never handed to somebody who did not ask.
    recipe = Recipe.resolve(declaration(tmp_path, mirrors=(GITLAB, GITHUB)))

    assert recipe.locator_for(SourceId.parse('@json')) == ''
    assert recipe.locator_for(
        SourceId.parse('@json@nlohmann@github.com')) == GITHUB


def test_a_mirror_serves_the_identity_naming_it_and_no_other(tmp_path):
    # An identity a mirror merely does not contradict has not named it: filling
    # its blanks from a mirror is what would make the mirror a default.
    recipe = Recipe.resolve(declaration(tmp_path, mirrors=(GITLAB,)))

    assert recipe.locator_for(SourceId.parse('@json@nlohmann')) == ''
    assert recipe.locator_for(SourceId.parse('@json@nlohmann@gitlab.com')) == GITLAB


def test_a_mirror_is_read_before_the_locator(tmp_path):
    # The two never both answer, since an identity naming a mirror exactly
    # states a remote the locator does not. Order settles only a mirror
    # composing the same identity as the locator, which is a redundant one.
    recipe = Recipe.resolve(
        declaration(tmp_path, locator=GITHUB, mirrors=(GITLAB,)))

    assert recipe.locator_for(SourceId.parse('@json@nlohmann@gitlab.com')) == GITLAB
    assert recipe.locator_for(SourceId.parse('@json@nlohmann@github.com')) == GITHUB


def test_a_mirror_is_never_served_to_an_identity_naming_the_recipe_alone(tmp_path):
    # With a default source, `@json` is served that one and never a mirror.
    recipe = Recipe.resolve(
        declaration(tmp_path, locator=GITHUB, mirrors=(GITLAB,)))

    assert recipe.locator_for(SourceId.parse('@json')) == GITHUB


def test_the_most_derived_declaration_naming_a_field_wins(tmp_path):
    recipe = layered(
        declaration(tmp_path, locator=FORK, name='@delta'),
        declaration(tmp_path, locator=GITHUB, project=True, name='@base'))

    assert recipe.locator == FORK
    assert recipe.project_directory == str(tmp_path / '@base')


def test_a_delta_naming_mirrors_leaves_the_locator_to_the_layer_below(tmp_path):
    # The two fields resolve independently, therefore naming one does not
    # shadow the other and a mirrors-only delta keeps the default below it.
    recipe = layered(
        declaration(tmp_path, mirrors=(GITLAB,), name='@delta'),
        declaration(tmp_path, locator=GITHUB, name='@base'))

    assert recipe.locator == GITHUB
    assert recipe.mirrors == (GITLAB,)
    assert recipe.locators == (GITHUB, GITLAB)


def test_a_delta_replacing_the_locator_keeps_the_mirrors_below_it(tmp_path):
    # A mirror is only ever reached by an identity naming it exactly, so an
    # inherited one reaches nobody who did not spell its full identity.
    recipe = layered(
        declaration(tmp_path, locator=FORK, name='@delta'),
        declaration(tmp_path, locator=GITHUB, mirrors=(GITLAB,), name='@base'))

    assert recipe.locator == FORK
    assert recipe.mirrors == (GITLAB,)
    assert recipe.locator_for(SourceId.parse('@json')) == FORK
    assert recipe.locator_for(SourceId.parse('@json@nlohmann@gitlab.com')) == GITLAB


def test_a_refusal_names_the_layers_a_recipe_was_made_of(tmp_path):
    # Naming only the declaration the lookup landed on would hide the layer the
    # missing field was expected from.
    recipe = layered(
        declaration(tmp_path, locator=FORK, name='@delta'),
        declaration(tmp_path, locator=GITHUB, name='@base'))

    with pytest.raises(RuntimeError) as refusal:
        recipe.require_project_directory()

    assert 'Inherited through @json (base) -> @json (base)' in str(refusal.value)
