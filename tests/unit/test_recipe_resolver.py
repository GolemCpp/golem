import json
import os
from types import SimpleNamespace

import pytest

from golemcpp.golem.recipe_resolver import RecipeResolver
from golemcpp.golem.source_id import SourceId


def make_cookbook(tmp_path, name, recipes=(), bare=(), declaring=()):
    '''
    Build a cookbook holding a recipe per name, and a bare directory per bare.

    A bare one is named like a recipe and holds nothing, which is what a
    half-made cookbook looks like from outside. One in `declaring` says where
    its package is and holds no project file, which is what a recipe reachable
    as a location but not loadable looks like.
    '''
    source = tmp_path / name / 'source'
    source.mkdir(parents=True, exist_ok=True)

    for recipe in recipes:
        (source / recipe).mkdir()
        (source / recipe / 'golemfile.py').write_text('def configure(p): pass')

    for recipe in bare:
        (source / recipe).mkdir()

    for recipe, locator in declaring:
        (source / recipe).mkdir(exist_ok=True)
        (source / recipe / 'recipe.json').write_text(
            json.dumps({'locator': locator}))

    return SimpleNamespace(source_path=str(source), cache_key=name)


def resolve(cookbooks, identity):
    return RecipeResolver(cookbooks).resolve(SourceId.parse(identity))


def served_from(cookbooks, identity):
    '''The directory the recipe answering an identity was declared in.'''
    return resolve(cookbooks, identity).served_by.directory


def tells_case_apart(directory):
    '''
    Whether a directory holds two names differing only in case as two names.

    This probes the filesystem capabilities.
    '''
    (directory / 'CASE_PROBE').mkdir()

    return not (directory / 'case_probe').exists()


def test_a_recipe_named_exactly_serves_the_identity(tmp_path, capsys):
    cookbook = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])

    directory = served_from([cookbook], '@json@nlohmann@github.com')

    assert directory.endswith('@json@nlohmann@github.com')
    assert ('@json@nlohmann@github.com: served by '
            '@json@nlohmann@github.com (base)') in capsys.readouterr().out


def test_a_lookup_saying_its_own_line_asks_for_no_report(tmp_path, capsys):
    # The location lookup names where the package is, and the sub-invocation
    # configuring the dependency names the recipe, so a second "served by" here
    # would say what one of those two already says.
    cookbook = make_cookbook(tmp_path, 'base', ['@json'])

    RecipeResolver([cookbook]).resolve(SourceId.parse('@json'), report=False)

    assert capsys.readouterr().out == ''


def test_a_shorter_rung_serves_when_nothing_is_named_exactly(tmp_path, capsys):
    # An ssh clone spells a rooting field the recipe does not carry, so the
    # ladder drops it and the plain directory answers.
    cookbook = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])

    directory = served_from([cookbook], '@json@nlohmann@github.com@scp.git')

    assert directory.endswith('@json@nlohmann@github.com')
    assert ('@json@nlohmann@github.com@scp.git: served by '
            '@json@nlohmann@github.com (base)') in capsys.readouterr().out


def test_the_most_specific_rung_is_probed_first(tmp_path):
    cookbook = make_cookbook(
        tmp_path, 'base', ['@json', '@json@nlohmann@github.com'])

    directory = served_from([cookbook], '@json@nlohmann@github.com')

    assert directory.endswith('@json@nlohmann@github.com')


def test_the_last_cookbook_listed_shadows_the_ones_below_it(tmp_path):
    # Named at a shorter qualification and still winning: layering is not
    # specificity arithmetic across cookbooks.
    base = make_cookbook(tmp_path, 'base', ['@json@nlohmann@github.com'])
    mine = make_cookbook(tmp_path, 'mine', ['@json'])

    directory = served_from([base, mine], '@json@nlohmann@github.com')

    assert directory == os.path.join(mine.source_path, '@json')


def test_a_directory_that_is_not_lowercase_is_never_reached(tmp_path):
    # Probing spells the path from an identity, which is always lowercase, so
    # the directory is a recipe nobody can look up.
    #
    # Wherever the filesystem tells case apart. APFS and NTFS do not, and there
    # the very same directory answers.
    if not tells_case_apart(tmp_path):
        pytest.skip('the filesystem does not tell two names apart by case')

    cookbook = make_cookbook(tmp_path, 'base', ['@Json@nlohmann@github.com'])

    with pytest.raises(RuntimeError, match='no recipe'):
        resolve([cookbook], '@json@nlohmann@github.com')


def test_a_recipe_answering_nothing_is_named_rather_than_skipped(tmp_path):
    # A directory named right and holding nothing serves nobody, so it is worth
    # pointing at rather than passing over.
    cookbook = make_cookbook(
        tmp_path, 'base', bare=['@json@nlohmann@github.com'])

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], '@json@nlohmann@github.com')

    assert 'holds no project file' in str(refusal.value)
    assert 'names no locator' in str(refusal.value)
    assert "cookbook 'base'" in str(refusal.value)


def test_a_bare_directory_does_not_fall_through_to_a_shorter_rung(tmp_path):
    # The refusal is raised where it is found rather than the ladder walking
    # past it: a cookbook holding a half-made recipe is worth pointing at.
    cookbook = make_cookbook(
        tmp_path, 'base', recipes=['@json'], bare=['@json@nlohmann@github.com'])

    with pytest.raises(RuntimeError, match='holds no project file'):
        resolve([cookbook], '@json@nlohmann@github.com')


def test_a_recipe_saying_only_where_its_package_is_still_serves(tmp_path):
    # It answers a caller pointed at the name, and refuses one looking for a
    # project file. Which of the two asked is not the resolver's business.
    cookbook = make_cookbook(
        tmp_path, 'base',
        declaring=[('@json', 'https://github.com/nlohmann/json.git')])

    recipe = resolve([cookbook], '@json@nlohmann@github.com')

    assert recipe.locator == 'https://github.com/nlohmann/json.git'
    assert recipe.project_directory == ''


def test_a_project_file_in_json_answers_as_well(tmp_path):
    cookbook = make_cookbook(tmp_path, 'base', bare=['@json@nlohmann@github.com'])
    directory = os.path.join(cookbook.source_path, '@json@nlohmann@github.com')
    open(os.path.join(directory, 'golemfile.json'), 'w').write('{}')

    assert served_from([cookbook], '@json@nlohmann@github.com') == directory


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
