import json
import os
from types import SimpleNamespace

import pytest

from golemcpp.golem.recipe_resolver import RecipeResolver
from golemcpp.golem.source_id import SourceId


def make_cookbook(tmp_path, name, recipes=(), bare=(), declaring=(), manifests=()):
    """
    Build a cookbook holding a recipe per name, and a bare directory per bare.

    A bare one is named like a recipe and holds nothing, which is what a
    half-made cookbook looks like from outside. One in `declaring` names where
    its source is and holds no project file, which is what a recipe reachable
    as a location but not loadable looks like. One in `manifests` carries the
    whole `recipe.json`, for the fields `declaring` does not reach.
    """
    source = tmp_path / name / "source"
    source.mkdir(parents=True, exist_ok=True)

    for recipe in recipes:
        (source / recipe).mkdir()
        (source / recipe / "golemfile.py").write_text("def configure(p): pass")

    for recipe in bare:
        (source / recipe).mkdir()

    for recipe, locator in declaring:
        (source / recipe).mkdir(exist_ok=True)
        (source / recipe / "recipe.json").write_text(json.dumps({"locator": locator}))

    for recipe, manifest in manifests:
        (source / recipe).mkdir(exist_ok=True)
        (source / recipe / "recipe.json").write_text(json.dumps(manifest))

    return SimpleNamespace(source_path=str(source), cache_key=name)


def resolve(cookbooks, identity):
    return RecipeResolver(cookbooks).resolve(SourceId.parse(identity))


def served_from(cookbooks, identity):
    """The directory the recipe answering an identity was declared in."""
    return resolve(cookbooks, identity).served_by.directory


def tells_case_apart(directory):
    """
    Whether a directory holds two names differing only in case as two names.

    This probes the filesystem capabilities.
    """
    (directory / "CASE_PROBE").mkdir()

    return not (directory / "case_probe").exists()


def test_a_recipe_named_exactly_serves_the_identity(tmp_path, capsys):
    cookbook = make_cookbook(tmp_path, "base", ["@json@nlohmann@github.com"])

    directory = served_from([cookbook], "@json@nlohmann@github.com")

    assert directory.endswith("@json@nlohmann@github.com")
    assert (
        "@json@nlohmann@github.com: served by " "@json@nlohmann@github.com (base)"
    ) in capsys.readouterr().out


def test_a_lookup_saying_its_own_line_asks_for_no_report(tmp_path, capsys):
    # The location lookup names where the source is, and the sub-invocation
    # configuring the dependency names the recipe, so a second "served by" here
    # would say what one of those two already says.
    cookbook = make_cookbook(tmp_path, "base", ["@json"])

    RecipeResolver([cookbook]).resolve(SourceId.parse("@json"), report=False)

    assert capsys.readouterr().out == ""


def test_a_shorter_rung_serves_when_nothing_is_named_exactly(tmp_path, capsys):
    # An ssh clone spells a rooting field the recipe does not carry, so the
    # ladder drops it and the plain directory answers.
    cookbook = make_cookbook(tmp_path, "base", ["@json@nlohmann@github.com"])

    directory = served_from([cookbook], "@json@nlohmann@github.com@scp.git")

    assert directory.endswith("@json@nlohmann@github.com")
    assert (
        "@json@nlohmann@github.com@scp.git: served by "
        "@json@nlohmann@github.com (base)"
    ) in capsys.readouterr().out


def test_the_most_specific_rung_is_probed_first(tmp_path):
    cookbook = make_cookbook(tmp_path, "base", ["@json", "@json@nlohmann@github.com"])

    directory = served_from([cookbook], "@json@nlohmann@github.com")

    assert directory.endswith("@json@nlohmann@github.com")


def test_the_last_cookbook_listed_shadows_the_ones_below_it(tmp_path):
    # Named at a shorter qualification and still winning: layering is not
    # specificity arithmetic across cookbooks.
    base = make_cookbook(tmp_path, "base", ["@json@nlohmann@github.com"])
    mine = make_cookbook(tmp_path, "mine", ["@json"])

    directory = served_from([base, mine], "@json@nlohmann@github.com")

    assert directory == os.path.join(mine.source_path, "@json")


def test_a_directory_that_is_not_lowercase_is_never_reached(tmp_path):
    # Probing spells the path from an identity, which is always lowercase, so
    # the directory is a recipe nobody can look up.
    #
    # Wherever the filesystem tells case apart. APFS and NTFS do not, and there
    # the very same directory answers.
    if not tells_case_apart(tmp_path):
        pytest.skip("the filesystem does not tell two names apart by case")

    cookbook = make_cookbook(tmp_path, "base", ["@Json@nlohmann@github.com"])

    with pytest.raises(RuntimeError, match="no recipe"):
        resolve([cookbook], "@json@nlohmann@github.com")


def test_a_recipe_answering_nothing_is_named_rather_than_skipped(tmp_path):
    # A directory named right and holding nothing serves nobody, so it is worth
    # pointing at rather than passing over.
    cookbook = make_cookbook(tmp_path, "base", bare=["@json@nlohmann@github.com"])

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], "@json@nlohmann@github.com")

    assert "holds no project file" in str(refusal.value)
    assert "names no locator" in str(refusal.value)
    assert "cookbook 'base'" in str(refusal.value)


def test_a_bare_directory_does_not_fall_through_to_a_shorter_rung(tmp_path):
    # The refusal is raised where it is found rather than the ladder walking
    # past it: a cookbook holding a half-made recipe is worth pointing at.
    cookbook = make_cookbook(
        tmp_path, "base", recipes=["@json"], bare=["@json@nlohmann@github.com"]
    )

    with pytest.raises(RuntimeError, match="holds no project file"):
        resolve([cookbook], "@json@nlohmann@github.com")


def test_a_recipe_saying_only_where_its_source_is_still_serves(tmp_path):
    # It answers a caller pointed at the name, and refuses one looking for a
    # project file. Which of the two asked is not the resolver's business.
    cookbook = make_cookbook(
        tmp_path, "base", declaring=[("@json", "https://github.com/nlohmann/json.git")]
    )

    recipe = resolve([cookbook], "@json@nlohmann@github.com")

    assert recipe.locator == "https://github.com/nlohmann/json.git"
    assert recipe.project_directory == ""


def test_a_project_file_in_json_answers_as_well(tmp_path):
    cookbook = make_cookbook(tmp_path, "base", bare=["@json@nlohmann@github.com"])
    directory = os.path.join(cookbook.source_path, "@json@nlohmann@github.com")
    open(os.path.join(directory, "golemfile.json"), "w").write("{}")

    assert served_from([cookbook], "@json@nlohmann@github.com") == directory


def test_no_recipe_anywhere_names_the_identity_and_what_was_searched(tmp_path):
    one = make_cookbook(tmp_path, "one", ["@boost@boostorg@github.com"])
    two = make_cookbook(tmp_path, "two", [])

    with pytest.raises(RuntimeError) as refusal:
        resolve([one, two], "@json@nlohmann@github.com")

    message = str(refusal.value)
    assert "no recipe '@json@nlohmann@github.com'" in message
    assert "Searched 2 cookbook(s)" in message
    assert one.source_path in message and two.source_path in message


def test_a_missing_recipe_names_no_project_file(tmp_path):
    # The refusal reports the search and never what a caller wanted out of it.
    # A dependency written as an identity asks for a locator, so a golemfile
    # named here points at a file nobody was expected to write, and a
    # `--recipe` given by hand may come from a project holding one already.
    cookbook = make_cookbook(tmp_path, "base", ["@boost"])

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], "@json")

    assert "golemfile" not in str(refusal.value)


def test_searching_no_cookbook_at_all_still_says_so():
    with pytest.raises(RuntimeError, match=r"Searched 0 cookbook\(s\)"):
        resolve([], "@json")


UPSTREAM = "https://github.com/boostorg/boost.git"
MIRROR = "https://git.corp/mirror/boost.git"


def in_cookbook(cookbook, recipe):
    return os.path.join(cookbook.source_path, recipe)


def test_a_delta_takes_over_the_recipe_of_the_same_name_below_it(tmp_path):
    # The headline case: a private cookbook moves where boost comes from, and
    # the recipe it overrides carries the same name it does.
    base = make_cookbook(
        tmp_path, "base", recipes=["@boost"], declaring=[("@boost", UPSTREAM)]
    )
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[("@boost", {"locator": MIRROR, "overrides": "@boost"})],
    )

    recipe = resolve([base, mine], "@boost")

    assert recipe.locator == MIRROR
    assert recipe.served_by.directory == in_cookbook(mine, "@boost")


def test_a_delta_inherits_a_project_file_it_does_not_restate(tmp_path):
    base = make_cookbook(
        tmp_path, "base", recipes=["@boost"], declaring=[("@boost", UPSTREAM)]
    )
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[("@boost", {"locator": MIRROR, "overrides": "@boost"})],
    )

    recipe = resolve([base, mine], "@boost")

    assert recipe.project_directory == in_cookbook(base, "@boost")


def test_the_full_ladder_restarts_in_each_cookbook(tmp_path):
    # `mine` runs its ladder down to nothing, and `base` is still asked for the
    # long name first. A cookbook outranks a more specific name below it, so
    # where the ladder stopped in one cookbook says nothing about the next.
    base = make_cookbook(
        tmp_path, "base", recipes=["@json", "@json@nlohmann@github.com"]
    )
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[
            ("@json@nlohmann@github.com", {"overrides": "@json@nlohmann@github.com"})
        ],
    )

    recipe = resolve([base, mine], "@json@nlohmann@github.com")

    assert recipe.project_directory == in_cookbook(base, "@json@nlohmann@github.com")


def test_a_skipped_entry_falls_to_the_next_rung_before_descending(tmp_path):
    # Inheritance inside one cookbook: the delta skips itself, drops a rung, and
    # finds its base without ever leaving `mine`.
    base = make_cookbook(tmp_path, "base", recipes=["@json"])
    mine = make_cookbook(
        tmp_path,
        "mine",
        recipes=["@json"],
        manifests=[
            ("@json@nlohmann@github.com", {"overrides": "@json@nlohmann@github.com"})
        ],
    )

    recipe = resolve([base, mine], "@json@nlohmann@github.com")

    assert [declaration.directory for declaration in recipe.chain] == [
        in_cookbook(mine, "@json@nlohmann@github.com"),
        in_cookbook(mine, "@json"),
    ]


def test_a_recipe_never_inherits_from_a_cookbook_above_it(tmp_path):
    # Downward only, so a base cookbook's recipe means the same thing whatever
    # is layered on top of it.
    base = make_cookbook(tmp_path, "base", manifests=[("@a", {"overrides": "@b"})])
    mine = make_cookbook(tmp_path, "mine", recipes=["@b"])

    with pytest.raises(RuntimeError) as refusal:
        resolve([base, mine], "@a")

    message = str(refusal.value)
    assert "recipe '@a' in cookbook 'base' overrides '@b'" in message
    assert "no cookbook at or below it holds one" in message
    # One declaration was consumed, and the message already names it.
    assert "Inherited through" not in message


def test_a_cycle_within_one_cookbook_is_refused_rather_than_looping(tmp_path):
    cookbook = make_cookbook(
        tmp_path,
        "base",
        manifests=[("@a", {"overrides": "@b"}), ("@b", {"overrides": "@a"})],
    )

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], "@a")

    assert "cycle in cookbook 'base': @a -> @b -> @a" in str(refusal.value)


def test_a_cycle_is_refused_rather_than_dropping_to_a_shorter_rung(tmp_path):
    # `@a@b` names `@a@b@c`, which the chain already took. `@a` is free and the
    # ladder could reach it, and taking it would record `@a@b` inheriting from a
    # recipe it never named. A revisit is the fault, whatever else is reachable.
    cookbook = make_cookbook(
        tmp_path,
        "base",
        recipes=["@a"],
        manifests=[
            ("@a@b@c", {"overrides": "@a@b"}),
            ("@a@b", {"overrides": "@a@b@c"}),
        ],
    )

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], "@a@b@c")

    assert "cycle in cookbook 'base': @a@b@c -> @a@b -> @a@b@c" in str(refusal.value)


def test_a_cycle_is_refused_though_a_cookbook_below_could_absorb_it(tmp_path):
    # `mine` holds a loop and `base` holds a recipe the descent would land on.
    # Letting it resolve would hide the same false record in a longer chain.
    base = make_cookbook(tmp_path, "base", recipes=["@a"])
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[("@a", {"overrides": "@b"}), ("@b", {"overrides": "@a"})],
    )

    with pytest.raises(RuntimeError) as refusal:
        resolve([base, mine], "@a")

    assert "cycle in cookbook 'mine': @a -> @b -> @a" in str(refusal.value)


def test_a_cycle_reports_the_loop_and_not_what_led_into_it(tmp_path):
    # The search never rises, so a recipe reached again sits no higher than the
    # one overriding it and the loop is always inside one cookbook. `mine/@x` is
    # how the chain got there and is no part of what has to be fixed.
    base = make_cookbook(
        tmp_path,
        "base",
        recipes=["@b"],
        manifests=[("@a", {"overrides": "@b"}), ("@b", {"overrides": "@a"})],
    )
    mine = make_cookbook(tmp_path, "mine", manifests=[("@x", {"overrides": "@a"})])

    with pytest.raises(RuntimeError) as refusal:
        resolve([base, mine], "@x")

    message = str(refusal.value)
    assert "cycle in cookbook 'base': @a -> @b -> @a" in message
    assert "@x" not in message


def test_a_declaration_still_passes_over_itself(tmp_path):
    # Self-reference is exclusion and never a revisit, which is what lets a
    # recipe override the name it carries.
    base = make_cookbook(
        tmp_path, "base", recipes=["@boost"], declaring=[("@boost", UPSTREAM)]
    )
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[("@boost", {"locator": MIRROR, "overrides": "@boost"})],
    )

    assert resolve([base, mine], "@boost").locator == MIRROR


def test_a_chain_mixing_manifest_versions_is_not_an_error(tmp_path):
    # Each declaration is read under its own version and nothing compares them.
    # Only one version exists to write, so this pins the decision rather than
    # exercising a real skew.
    base = make_cookbook(
        tmp_path,
        "base",
        recipes=["@boost"],
        manifests=[("@boost", {"locator": UPSTREAM, "version": 1})],
    )
    mine = make_cookbook(
        tmp_path, "mine", manifests=[("@boost", {"overrides": "@boost"})]
    )

    assert resolve([base, mine], "@boost").locator == UPSTREAM


def test_the_report_names_every_recipe_that_served(tmp_path, capsys):
    base = make_cookbook(
        tmp_path, "base", recipes=["@boost"], declaring=[("@boost", UPSTREAM)]
    )
    mine = make_cookbook(
        tmp_path,
        "mine",
        manifests=[("@boost", {"locator": MIRROR, "overrides": "@boost"})],
    )

    resolve([base, mine], "@boost")

    assert "@boost: served by @boost (mine) -> @boost (base)" in capsys.readouterr().out


def test_a_chain_answering_nothing_names_what_it_was_made_of(tmp_path):
    # Neither layer holds a project file or names a locator, and the refusal has
    # to name both: the reader cannot see which one was expected to carry them.
    cookbook = make_cookbook(
        tmp_path, "base", manifests=[("@a", {"overrides": "@b"})], bare=["@b"]
    )

    with pytest.raises(RuntimeError) as refusal:
        resolve([cookbook], "@a")

    message = str(refusal.value)
    assert "holds no project file" in message and "names no locator" in message
    assert "Inherited through @a (base) -> @b (base)" in message
