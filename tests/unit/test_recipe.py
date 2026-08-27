from types import SimpleNamespace

import pytest

from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.recipe import Recipe
from golemcpp.golem.recipe_manifest import RecipeManifest
from golemcpp.golem.source_id import SourceId


def declaration(tmp_path, locator='', project=False):
    '''Build a declaration on disk, since a project file is read off it.'''
    directory = tmp_path / '@json'
    directory.mkdir(exist_ok=True)

    if project:
        (directory / 'golemfile.py').write_text('def configure(p): pass')

    return DeclaredRecipe(
        directory=str(directory),
        cookbook=SimpleNamespace(source_path=str(tmp_path), cache_key='base'),
        rung=SourceId.parse('@json'),
        manifest=RecipeManifest(locator=locator),
    )


def test_a_recipe_answers_where_its_package_is(tmp_path):
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
        recipe.require_locator()

    assert "recipe '@json' in cookbook 'base'" in str(refusal.value)
    assert 'names no locator' in str(refusal.value)


def test_asking_for_a_project_file_a_recipe_does_not_hold_is_refused(tmp_path):
    # The caller has no golemfile of its own, therefore a recipe that only says
    # where its package is answers somebody else's question.
    recipe = Recipe.resolve(declaration(tmp_path, locator='https://host.xz/j.git'))

    with pytest.raises(RuntimeError) as refusal:
        recipe.require_project_directory()

    assert "recipe '@json' in cookbook 'base'" in str(refusal.value)
    assert 'holds no project file' in str(refusal.value)


def test_what_a_recipe_answers_is_returned_rather_than_refused(tmp_path):
    recipe = Recipe.resolve(
        declaration(tmp_path, locator='https://host.xz/j.git', project=True))

    assert recipe.require_locator() == 'https://host.xz/j.git'
    assert recipe.require_project_directory() == str(tmp_path / '@json')


def test_a_recipe_names_the_declaration_that_answered(tmp_path):
    # One long until a recipe can be a delta on another, and the chain is what
    # a resolution records.
    declared = declaration(tmp_path, project=True)

    assert Recipe.resolve(declared).chain == (declared,)
    assert Recipe.resolve(declared).served_by is declared
