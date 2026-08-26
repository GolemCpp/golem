import os
from types import SimpleNamespace

import pytest

from golemcpp.golem.recipe_resolver import RecipeResolver
from golemcpp.golem.source_id import SourceId


def make_cookbook(tmp_path, name, recipes=(), bare=()):
    '''
    Build a cookbook holding a recipe per name, and a bare directory per bare.

    A bare one is named like a recipe and holds nothing, which is what a
    half-made cookbook looks like from outside.
    '''
    source = tmp_path / name / 'source'
    source.mkdir(parents=True, exist_ok=True)

    for recipe in recipes:
        (source / recipe).mkdir()
        (source / recipe / 'golemfile.py').write_text('def configure(p): pass')

    for recipe in bare:
        (source / recipe).mkdir()

    return SimpleNamespace(source_path=str(source), cache_key=name)


def resolve(cookbooks, identity):
    return RecipeResolver(cookbooks).resolve(SourceId.parse(identity))


def test_a_recipe_named_exactly_serves_the_identity(tmp_path, capsys):
    cookbook = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])

    directory = resolve([cookbook], '@json@nlohmann@github.com')

    assert directory.endswith('@json@nlohmann@github.com')
    assert ('@json@nlohmann@github.com: served by '
            '@json@nlohmann@github.com (base)') in capsys.readouterr().out


def test_a_shorter_rung_serves_when_nothing_is_named_exactly(tmp_path, capsys):
    # An ssh clone spells a rooting field the recipe does not carry, so the
    # ladder drops it and the plain directory answers.
    cookbook = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])

    directory = resolve([cookbook], '@json@nlohmann@github.com@scp.git')

    assert directory.endswith('@json@nlohmann@github.com')
    assert ('@json@nlohmann@github.com@scp.git: served by '
            '@json@nlohmann@github.com (base)') in capsys.readouterr().out


def test_the_most_specific_rung_is_probed_first(tmp_path):
    cookbook = make_cookbook(
        tmp_path, 'base', ['@json', '@json@nlohmann@github.com'])

    directory = resolve([cookbook], '@json@nlohmann@github.com')

    assert directory.endswith('@json@nlohmann@github.com')


def test_the_last_cookbook_listed_shadows_the_ones_below_it(tmp_path):
    # Named at a shorter qualification and still winning: layering is not
    # specificity arithmetic across cookbooks.
    base = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])
    mine = make_cookbook(tmp_path, 'mine', ['@json'])

    directory = resolve([base, mine], '@json@nlohmann@github.com')

    assert directory == os.path.join(mine.source_path, '@json')


def test_a_directory_that_is_not_lowercase_is_never_reached(tmp_path):
    # Probing spells the path from an identity, which is always lowercase, so
    # the directory is a recipe nobody can look up.
    cookbook = make_cookbook(tmp_path, 'base', ['@Json@nlohmann@github.com'])

    with pytest.raises(RuntimeError, match='no recipe'):
        resolve([cookbook], '@json@nlohmann@github.com')


def test_a_recipe_holding_no_project_file_is_named_rather_than_skipped(tmp_path):
    # load_project leaves the project unset when it finds nothing, so serving
    # this in silence is what the refusal exists to prevent.
    cookbook = make_cookbook(
        tmp_path, 'base', bare=['@json@nlohmann@github.com'])

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], '@json@nlohmann@github.com')

    assert 'holds no project file' in str(refusal.value)
    assert "cookbook 'base'" in str(refusal.value)


def test_a_bare_directory_does_not_fall_through_to_a_shorter_rung(tmp_path):
    # The refusal is raised where it is found rather than the ladder walking
    # past it: a cookbook holding a half-made recipe is worth pointing at.
    cookbook = make_cookbook(
        tmp_path, 'base', recipes=['@json'], bare=['@json@nlohmann@github.com'])

    with pytest.raises(RuntimeError, match='holds no project file'):
        resolve([cookbook], '@json@nlohmann@github.com')


def test_a_project_file_in_json_answers_as_well(tmp_path):
    cookbook = make_cookbook(tmp_path, 'base', bare=['@json@nlohmann@github.com'])
    directory = os.path.join(cookbook.source_path, '@json@nlohmann@github.com')
    open(os.path.join(directory, 'golemfile.json'), 'w').write('{}')

    assert resolve([cookbook], '@json@nlohmann@github.com') == directory


def test_no_recipe_anywhere_names_the_identity_and_what_was_searched(tmp_path):
    one = make_cookbook(tmp_path, 'one', ['@boost@boostorg@github.com'])
    two = make_cookbook(tmp_path, 'two', [])

    with pytest.raises(RuntimeError) as refusal:
        resolve([one, two], '@json@nlohmann@github.com')

    message = str(refusal.value)
    assert "no recipe '@json@nlohmann@github.com'" in message
    assert 'Searched 2 cookbook(s)' in message
    assert one.source_path in message and two.source_path in message


def test_searching_no_cookbook_at_all_still_says_so():
    with pytest.raises(RuntimeError, match=r'Searched 0 cookbook\(s\)'):
        resolve([], '@json')
