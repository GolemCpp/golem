import json
import os
from types import SimpleNamespace

import pytest

from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.recipe import Recipe
from golemcpp.golem.recipe_manifest import RecipeManifest
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem import overrides
from golemcpp.golem.dependency_manager import DependencyManager
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source_id import SourceId
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.locator import Locator
from golemcpp.golem import safe_part
from golemcpp.golem.resource_manager import make_revision_part
from golemcpp.golem.version_resolver import VersionResolver

# A full object name, so make_revision_part abbreviates it the way it
# abbreviates a real one.
STUB_REVISION = "65ee68451d8eb2b5f3a30b410476ab83deb3289b"


def test_dependency_accepts_repository_keyword():
    dep = Dependency(name="json", repository="https://example.com/json.git")
    assert dep.repository == "https://example.com/json.git"
    assert dep.directory == ""
    assert dep.is_non_git_directory() is False


def test_dependency_accepts_directory_keyword(tmp_path):
    dep = Dependency(name="mylib", directory="./mylib")
    assert dep.directory == "./mylib"
    assert dep.repository == ""

    # Against the project it was declared in, which is what every reader of a
    # dependency does first. Only then does anything know what this is: the
    # declaration says where, the reading says what.
    dep.update_source(str(tmp_path))

    assert dep.is_non_git_directory() is True
    # Kept as the golemfile wrote it; what it means sits in `resolved`.
    assert dep.directory == "./mylib"
    assert dep.resolved.locator == (tmp_path / "mylib").resolve().as_uri()

    # A directory dependency has no version to resolve, and resolving one names
    # nothing rather than standing something in for it.
    assert dep.resolve() == ResolvedVersion()
    assert not dep.resolved.version
    # Idempotent. Where it comes from was worked out even so, therefore the
    # record holds that much and no version.
    assert dep.resolve() == ResolvedVersion()
    recorded = Dependency.serialize_to_json(dep)["resolved"]
    assert recorded["locator"] == (tmp_path / "mylib").resolve().as_uri()
    assert recorded["kind"] == "directory"
    # No version to record, therefore no key: an empty one would say a version
    # was looked for and not found.
    assert "version" not in recorded
    # Composed from the locator, so the record explains the cache directory.
    assert recorded["identity"] == str(SourceId.from_locator(recorded["locator"]))

    source = ResourceManager.source_for(dep)
    assert source.type == "directory"
    assert source.locator == Locator((tmp_path / "mylib").resolve().as_uri())


def test_a_dependency_does_nothing_before_it_is_resolved_against_a_project():
    # `./mylib` means nothing without the project it was written in, so anything
    # asking what this dependency is refuses rather than answering with a source
    # nothing can locate. One mistake, one error, whichever way it is reached.
    dep = Dependency(name="mylib", directory="./mylib")

    for ask in (ResourceManager.source_for, Dependency.resolve):
        with pytest.raises(ValueError) as error:
            ask(dep)
        assert "resolved against a project first" in str(error.value)


def test_dependency_serializes_and_round_trips_repository():
    dep = Dependency(name="json", repository="https://example.com/json.git")
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload["repository"] == "https://example.com/json.git"
    assert "url" not in payload

    restored = Dependency.unserialize_from_json(payload)
    assert restored.repository == "https://example.com/json.git"


def test_dependency_serializes_directory():
    dep = Dependency(name="mylib", directory="./mylib")
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload["directory"] == "./mylib"

    restored = Dependency.unserialize_from_json(payload)
    assert restored.directory == "./mylib"


def test_a_dependency_starts_without_a_cached_resource():
    # A DependencyManager fills it in; a dependency restored from a
    # dependencies.json comes back without one.
    assert (
        Dependency(
            name="json", repository="https://example.com/json.git"
        ).cached_resource
        is None
    )


def test_a_location_may_name_the_version(tmp_path):
    dep = Dependency(name="json", location="git+https://host/json.git#^3.0.0")
    dep.update_source(str(tmp_path))

    assert dep.resolved.locator == "https://host/json.git"
    assert dep.version == "^3.0.0"


def test_a_location_naming_no_version_leaves_the_version_alone(tmp_path):
    # Empty means the latest release for a dependency, which is not what a git
    # location with nothing named should silently turn into.
    dep = Dependency(name="json", location="git+https://host/json.git")
    dep.update_source(str(tmp_path))

    assert dep.version == ""


def test_a_declared_version_survives_a_location_naming_none(tmp_path):
    dep = Dependency(
        name="json", location="git+https://host/json.git", version="^3.0.0"
    )
    dep.update_source(str(tmp_path))

    assert dep.version == "^3.0.0"


def make_checkout(path):
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return path


def test_a_repository_must_name_a_repository(tmp_path):
    # The same assertion `location='git+./plaindir'` makes. It used to be skipped
    # for this spelling, so which field you wrote decided whether a plain
    # directory was caught here or much later inside git.
    (tmp_path / "plaindir").mkdir()

    with pytest.raises(ValueError) as error:
        Dependency(name="mylib", repository="./plaindir").update_source(str(tmp_path))

    assert "is not a repository git can clone from" in str(error.value)


def test_a_repository_naming_a_checkout_resolves_against_the_project(tmp_path):
    checkout = make_checkout(tmp_path / "myrepo")
    dep = Dependency(name="mylib", repository="./myrepo")
    dep.update_source(str(tmp_path))

    assert dep.repository == "./myrepo"
    assert dep.resolved.locator == checkout.resolve().as_uri()


@pytest.mark.parametrize("field", ["repository", "directory"])
def test_neither_field_reads_a_version_out_of_its_locator(tmp_path, field):
    # They name a locator and state a kind by being the field they are. Only
    # `location` is `[<kind>+]<locator>[#<version>]`, so a `#` here is part of
    # what was pointed at.
    named = tmp_path / "mylib#v1.2.0"
    if field == "repository":
        make_checkout(named)
    else:
        named.mkdir()

    dep = Dependency(name="mylib", **{field: "./mylib#v1.2.0"})
    dep.update_source(str(tmp_path))

    assert getattr(dep, field) == "./mylib#v1.2.0"
    assert dep.resolved.locator == named.resolve().as_uri()
    assert dep.version == ""


def test_an_override_naming_a_plain_directory_as_a_repository_is_refused(tmp_path):
    # read_overrides runs every entry through update_source, so overrides.json
    # gets the same refusal without knowing about it.
    (tmp_path / "plaindir").mkdir()
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(
        json.dumps([{"name": "mylib", "repository": "./plaindir"}]), encoding="utf-8"
    )

    with pytest.raises(ValueError) as error:
        overrides.read_overrides(str(overrides_path), str(tmp_path))

    assert "is not a repository git can clone from" in str(error.value)


def test_a_dependency_asking_for_two_versions_is_refused(tmp_path):
    dep = Dependency(
        name="json", location="git+https://host/json.git#v1", version="^3.0.0"
    )

    with pytest.raises(ValueError) as error:
        dep.update_source(str(tmp_path))

    assert "asks for exactly one" in str(error.value)
    assert "'^3.0.0'" in str(error.value)
    assert "'v1'" in str(error.value)


def test_a_recorded_reference_alone_is_not_a_resolution(monkeypatch):
    # A reference names no commit, and a dependency root is named after one, so
    # a file recording only a reference is asking for a version rather than
    # answering one. Resolve it, rather than let a tag name a root that is never
    # fetched again.
    dep = Dependency.unserialize_from_json(
        {
            "name": "json",
            "repository": "https://host/json.git",
            "resolved": {
                "locator": "https://host/json.git",
                "kind": "git",
                "version": {"reference": "v3.12.0"},
            },
        }
    )
    whole = ResolvedVersion(reference="v3.12.0", revision=STUB_REVISION)
    monkeypatch.setattr(VersionResolver, "resolve", staticmethod(lambda _: whole))

    assert dep.resolve() == whole


def test_a_recorded_revision_alone_is_a_resolution(monkeypatch):
    # The commit is what names the root, so nothing is missing. The reference is
    # the label, and it stays empty rather than claiming the commit was one.
    dep = Dependency.unserialize_from_json(
        {
            "name": "json",
            "repository": "https://host/json.git",
            "resolved": {
                "locator": "https://host/json.git",
                "kind": "git",
                "version": {"revision": STUB_REVISION},
            },
        }
    )
    monkeypatch.setattr(
        VersionResolver,
        "resolve",
        staticmethod(lambda _: pytest.fail("the remote must not be reached")),
    )

    assert dep.resolve() == ResolvedVersion(revision=STUB_REVISION)
    assert DependencyManager.cache_key_for(dep).endswith(
        safe_part.VERSION_SEPARATOR + make_revision_part(STUB_REVISION)
    )


def test_a_dependency_records_a_whole_resolution_untouched():
    dep = Dependency.unserialize_from_json(
        {
            "name": "json",
            "repository": "https://host/json.git",
            "resolved": {"version": {"reference": "v3.12.0", "revision": "65ee6845"}},
        }
    )

    assert dep.resolved.version == ResolvedVersion(
        reference="v3.12.0", revision="65ee6845"
    )


def test_a_recorded_revision_that_names_no_commit_is_refused():
    # Everything downstream takes a revision for a commit: the cache root is
    # named after it, and the fetch resets onto it without interpreting it. A
    # branch written here would reach git as a revision it reads its own way.
    with pytest.raises(RuntimeError) as error:
        Dependency.unserialize_from_json(
            {
                "name": "json",
                "repository": "https://host/json.git",
                "resolved": {"version": {"reference": "main", "revision": "main"}},
            }
        )

    assert "names no commit" in str(error.value)
    assert "'json'" in str(error.value)


def test_a_dependency_written_as_an_identity_keeps_it_as_written():
    # A locator resolves away into the field naming its kind; an identity has
    # no such field, so it stays where it was written until something resolves
    # it into where the source actually is.
    dependency = Dependency(name="boost", location="@boost#^1.87.0")

    dependency.update_source("/proj", identity_allowed=True)

    assert dependency.location == "@boost#^1.87.0"


def test_where_an_identity_comes_from_is_not_known_yet():
    # The cookbook lookup finds it, so neither field naming a source is filled.
    dependency = Dependency(name="boost", location="@boost")

    dependency.update_source("/proj", identity_allowed=True)

    assert dependency.repository == ""
    assert dependency.directory == ""


def test_an_identity_is_refused_for_anything_but_a_dependency():
    # An override entry arrives through update_source too, and naming one by
    # identity is what the deferred overrides work has to settle first.
    dependency = Dependency(name="boost", location="@boost")

    with pytest.raises(ValueError, match="only a dependency's source"):
        dependency.update_source("/proj")


def test_an_identity_is_read_for_its_refusals_even_though_it_is_kept():
    # Leaving it as written is not leaving it unchecked: the grammar errors
    # belong where the text a person typed is still in hand.
    dependency = Dependency(name="boost", location="@a@b@c@d@e")

    with pytest.raises(ValueError, match="more than the four fields"):
        dependency.update_source("/proj", identity_allowed=True)


def test_a_copied_directory_takes_no_version_even_when_one_was_patched_in():
    # An override writes `version` onto every entry it matches, kind and all,
    # therefore one reaches a directory without anybody having asked for it.
    dependency = Dependency(name="mylib", directory="/srv/mylib", version="^2.0.0")
    dependency.update_source("")

    assert dependency.version == "^2.0.0"
    assert dependency.requested_source().version == ""


BOOST_LOCATOR = "https://github.com/boostorg/boost.git"


def make_recipe(locator, rung="@boost", cookbook="base", mirrors=()):
    """A recipe declaring where its source is, the way a cookbook does."""
    return Recipe.resolve(
        DeclaredRecipe(
            directory=os.path.join("/cookbook", rung),
            cookbook=SimpleNamespace(cache_key=cookbook),
            rung=SourceId.parse(rung),
            manifest=RecipeManifest(locator=locator, mirrors=mirrors),
        )
    )


def settled_from_identity(location, recipe):
    """A dependency written as an identity, read and then looked up."""
    dependency = Dependency(name="boost", location=location)
    dependency.update_source("/proj", identity_allowed=True)
    dependency.settle_from_recipe(dependency.declared_identity(), recipe)
    return dependency


def test_an_identity_is_read_back_out_of_what_was_declared():
    # Nothing holds it: the location is the record of what was asked for.
    dependency = Dependency(name="boost", location="@boost#^1.87.0")
    dependency.update_source("/proj", identity_allowed=True)

    assert str(dependency.declared_identity()) == "@boost"


def test_a_dependency_naming_no_identity_has_none_to_look_up():
    dependency = Dependency(name="json", location="git+https://host/json.git")
    dependency.update_source("/proj", identity_allowed=True)

    assert dependency.declared_identity() is None
    assert Dependency(name="json", repository="x").declared_identity() is None


def test_a_recipe_says_where_a_dependency_written_as_an_identity_comes_from():
    dependency = settled_from_identity("@boost", make_recipe(BOOST_LOCATOR))

    assert dependency.resolved.locator == BOOST_LOCATOR
    assert dependency.resolved.kind == "git"
    # Composed from the locator, as every identity is, therefore `@boost` and
    # the URL land on one cache entry with nothing filled in.
    assert str(dependency.resolved.identity) == "@boost@boostorg@github.com"
    assert dependency.location == "@boost"


def test_the_lookup_says_what_the_identity_resolved_to(capsys):
    settled_from_identity("@boost", make_recipe(BOOST_LOCATOR, cookbook="acme"))

    out = capsys.readouterr().out

    assert "@boost -> {}".format(BOOST_LOCATOR) in out
    assert "(acme)" in out


def test_the_version_asked_of_an_identity_is_asked_of_the_recipes_locator():
    # A cookbook says where a source is and never which version to take.
    dependency = settled_from_identity("@boost#^1.87.0", make_recipe(BOOST_LOCATOR))

    requested = dependency.requested_source()

    assert requested.version == "^1.87.0"
    assert str(requested.locator) == BOOST_LOCATOR


def test_a_recipe_answering_a_shorter_name_states_nothing_that_contradicts():
    dependency = settled_from_identity("@boost@boostorg", make_recipe(BOOST_LOCATOR))

    assert dependency.resolved.locator == BOOST_LOCATOR


def test_a_recipe_the_identity_contradicts_is_refused():
    # The ladder's fallback is right for finding a recipe and wrong for finding
    # a location: `@boost` says how to build boost wherever it was cloned from,
    # and asking for a fork must not fetch boostorg instead.
    dependency = Dependency(name="boost", location="@boost@somefork@github.com")
    dependency.update_source("/proj", identity_allowed=True)

    with pytest.raises(RuntimeError, match="@boost@somefork@github.com"):
        dependency.settle_from_recipe(
            dependency.declared_identity(), make_recipe(BOOST_LOCATOR)
        )

    assert dependency.resolved.locator == ""


def test_a_recipe_naming_no_locator_cannot_be_used_as_a_location():
    dependency = Dependency(name="boost", location="@boost")
    dependency.update_source("/proj", identity_allowed=True)

    with pytest.raises(RuntimeError, match="names no locator"):
        dependency.settle_from_recipe(dependency.declared_identity(), make_recipe(""))


GITLAB_LOCATOR = "https://gitlab.com/boostorg/boost.git"


def test_an_identity_naming_a_mirror_settles_that_mirror(capsys):
    recipe = make_recipe(BOOST_LOCATOR, mirrors=(GITLAB_LOCATOR,))
    dependency = settled_from_identity("@boost@boostorg@gitlab.com", recipe)

    assert dependency.resolved.locator == GITLAB_LOCATOR
    # Composed from the locator that won, therefore the gitlab spelling is its
    # own cache entry rather than the github one under another name.
    assert str(dependency.resolved.identity) == "@boost@boostorg@gitlab.com"
    assert GITLAB_LOCATOR in capsys.readouterr().out


def test_a_bare_identity_settles_the_primary_though_a_mirror_matches_too():
    recipe = make_recipe(BOOST_LOCATOR, mirrors=(GITLAB_LOCATOR,))
    dependency = settled_from_identity("@boost", recipe)

    assert dependency.resolved.locator == BOOST_LOCATOR


def test_the_two_spellings_of_one_mirrored_source_are_two_cache_entries():
    recipe = make_recipe(BOOST_LOCATOR, mirrors=(GITLAB_LOCATOR,))

    primary = settled_from_identity("@boost", recipe)
    mirror = settled_from_identity("@boost@boostorg@gitlab.com", recipe)

    assert primary.resolved.identity != mirror.resolved.identity


def test_a_refusal_names_every_locator_the_recipe_was_asked_about():
    recipe = make_recipe(BOOST_LOCATOR, mirrors=(GITLAB_LOCATOR,))
    dependency = Dependency(name="boost", location="@boost@somefork@github.com")
    dependency.update_source("/proj", identity_allowed=True)

    with pytest.raises(RuntimeError) as refusal:
        dependency.settle_from_recipe(dependency.declared_identity(), recipe)

    # With what each one composes, so a reader compares them with what was
    # asked for rather than composing them by eye.
    assert BOOST_LOCATOR in str(refusal.value)
    assert GITLAB_LOCATOR in str(refusal.value)
    assert "@boost@boostorg@gitlab.com" in str(refusal.value)


def test_the_imports_fall_back_to_the_name():
    # The two are one string until a consumer says otherwise, which is what
    # keeps every existing golemfile working.
    assert Dependency(name="boost").requested_imports() == ["boost"]


def test_a_declared_import_is_what_leaves_the_project_file():
    # `name` labels the declaration locally; an import is spelled in the
    # dependency's own vocabulary, so a consumer may call it what it likes.
    dependency = Dependency(name="bst", location="@boost", imports="boost")

    assert dependency.name == "bst"
    assert dependency.requested_imports() == ["boost"]


def test_a_declared_import_survives_a_round_trip():
    dependency = Dependency(name="bst", location="@boost", imports=["boost"])

    restored = Dependency.unserialize_from_json(
        Dependency.serialize_to_json(dependency)
    )

    assert restored.imports == ["boost"]


def test_an_import_nobody_declared_is_left_out_of_the_record():
    # The rule every other empty member follows, so a lock records what the
    # golemfile wrote and never what Golem filled in.
    recorded = Dependency.serialize_to_json(Dependency(name="boost"))

    assert "imports" not in recorded
    assert Dependency.unserialize_from_json(recorded).requested_imports() == ["boost"]


def test_importing_more_than_one_export_is_refused_for_now():
    # The shape is plural so the limit lifts without a rename, but a consumer
    # cannot yet know which import produces which target.
    with pytest.raises(ValueError, match="one is all Golem reads today"):
        Dependency(name="boost", imports=["boost", "boost-tools"])
