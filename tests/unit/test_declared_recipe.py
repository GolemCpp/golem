import json
import os
from types import SimpleNamespace

import pytest

from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.source_id import SourceId


def make_recipe(tmp_path, name='@json', manifest=None, project=None):
    '''Build a cookbook holding one recipe directory, and name both.'''
    source = tmp_path / 'source'
    (source / name).mkdir(parents=True)

    if manifest is not None:
        (source / name / 'recipe.json').write_text(json.dumps(manifest))

    if project is not None:
        (source / name / project).write_text('def configure(p): pass')

    return SimpleNamespace(source_path=str(source), cache_key='base')


def read(cookbook, name='@json'):
    return DeclaredRecipe.read(cookbook, SourceId.parse(name))


def test_a_cookbook_holding_no_such_directory_declares_nothing(tmp_path):
    # Answering None is what lets the probe carry on to the next rung.
    cookbook = make_recipe(tmp_path, project='golemfile.py')

    assert read(cookbook, '@boost') is None


def test_a_recipe_holding_only_a_project_file_says_how_to_build_it(tmp_path):
    cookbook = make_recipe(tmp_path, project='golemfile.py')

    declared = read(cookbook)

    assert declared.project_directory == os.path.join(cookbook.source_path, '@json')
    assert declared.locator == ''


def test_a_project_file_in_json_counts_as_one(tmp_path):
    cookbook = make_recipe(tmp_path, project='golemfile.json')

    assert read(cookbook).project_directory


def test_a_recipe_holding_only_a_manifest_says_where_its_source_is(tmp_path):
    cookbook = make_recipe(
        tmp_path, manifest={'locator': 'https://github.com/nlohmann/json.git'})

    declared = read(cookbook)

    assert declared.locator == 'https://github.com/nlohmann/json.git'
    assert declared.project_directory == ''


def test_a_recipe_holding_neither_declares_neither(tmp_path):
    # Refusing this is the resolver's call, not the declaration's: a layer may
    # be empty without the recipe being broken once one can override another.
    cookbook = make_recipe(tmp_path)

    declared = read(cookbook)

    assert declared.locator == ''
    assert declared.project_directory == ''


def test_a_relative_locator_is_anchored_on_the_recipe_directory(tmp_path):
    # The one anchor a cookbook author can see. Anchoring against the consuming
    # project would resolve it on a filesystem they have never seen.
    (tmp_path / 'source' / 'vendor').mkdir(parents=True)
    cookbook = make_recipe(tmp_path, manifest={'locator': '../vendor/json'})

    assert read(cookbook).locator == str(tmp_path / 'source' / 'vendor' / 'json')


def test_an_absolute_locator_is_left_alone(tmp_path):
    cookbook = make_recipe(tmp_path, manifest={'locator': str(tmp_path / 'here')})

    assert read(cookbook).locator == str(tmp_path / 'here')


@pytest.mark.parametrize('locator', [
    'https://github.com/nlohmann/json.git',
    'git@github.com:nlohmann/json.git',
    'ext::sh -c foo',
])
def test_a_locator_that_is_no_path_is_left_alone(tmp_path, locator):
    # Git's own rule tells a path from a remote, so Golem never disagrees with
    # it about which is which.
    cookbook = make_recipe(tmp_path, manifest={'locator': locator})

    assert read(cookbook).locator == locator


def test_a_declaration_names_itself_by_its_recipe_and_its_cookbook(tmp_path):
    # A cookbook path is a hash under minimization, so a message names the
    # cache key instead.
    cookbook = make_recipe(tmp_path, project='golemfile.py')

    assert str(read(cookbook)) == "recipe '@json' in cookbook 'base'"


def test_a_manifest_golem_cannot_read_is_refused_naming_the_recipe(tmp_path):
    cookbook = make_recipe(tmp_path, project='golemfile.py')
    (tmp_path / 'source' / '@json' / 'recipe.json').write_text('{')

    with pytest.raises(RuntimeError) as refusal:
        read(cookbook)

    assert "recipe '@json' in cookbook 'base'" in str(refusal.value)
