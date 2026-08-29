import os

import pytest

from golemcpp.golem import source
from golemcpp.golem import source_location
from golemcpp.golem.locator import Locator
from golemcpp.golem.source_id import SourceId
from golemcpp.golem.source_location import SourceLocation


def make_repository(path):
    """A checkout, as the filesystem shows one: `.git` holding a HEAD."""
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return path


def make_bare_repository(path):
    """A bare repository: the git directory itself, with no working tree."""
    path.mkdir(parents=True)
    (path / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (path / "objects").mkdir()
    (path / "refs").mkdir()
    return path


def read(location, tmp_path, identity_allowed=True):
    """Read a location the way a dependency reads one."""
    return source_location.parse(
        location, project_directory=str(tmp_path), identity_allowed=identity_allowed
    )


def test_parse_normalizes_and_classifies_local_directory(tmp_path):
    project_dir = tmp_path / "project dir"
    recipes_dir = project_dir / "recipes"
    recipes_dir.mkdir(parents=True)

    settled = source_location.parse("recipes", str(project_dir))

    assert settled.locator == Locator(recipes_dir.resolve().as_uri())
    assert settled.kind == "directory"


def test_parse_parses_encoded_local_directory_path(tmp_path):
    project_dir = tmp_path / "project dir"
    recipes_dir = project_dir / "recipes #1"
    recipes_dir.mkdir(parents=True)

    settled = source_location.parse("recipes #1", str(project_dir))

    assert settled.locator.get_local_path() == str(recipes_dir.resolve())


def test_parse_normalizes_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / "日本 語 project"
    recipes_dir = project_dir / "recipes"
    recipes_dir.mkdir(parents=True)

    settled = source_location.parse("recipes", str(project_dir))

    assert settled.locator == Locator(recipes_dir.resolve().as_uri())
    assert settled.locator.get_local_path() == str(recipes_dir.resolve())


def test_parse_classifies_local_non_git_directory(tmp_path):
    project_dir = tmp_path / "project"
    lib_dir = project_dir / "lib"
    lib_dir.mkdir(parents=True)

    settled = source_location.parse("lib", str(project_dir))

    assert settled.kind == "directory"
    assert settled.locator == Locator(lib_dir.resolve().as_uri())


def test_parse_classifies_git_directory_as_git(tmp_path):
    project_dir = tmp_path / "project"
    make_repository(project_dir / "recipes")

    settled = source_location.parse("recipes", str(project_dir))

    assert settled.kind == "git"


def test_parse_refuses_an_explicit_git_kind_on_a_plain_directory(tmp_path):
    # `git+` says the location is a repository, so a directory git cannot clone
    # from is a misconfiguration, named here rather than inside git later.
    project_dir = tmp_path / "project"
    (project_dir / "lib").mkdir(parents=True)

    with pytest.raises(ValueError) as error:
        source_location.parse("git+lib", str(project_dir))

    assert "not a repository git can clone from" in str(error.value)


def test_parse_accepts_an_explicit_git_kind_on_a_bare_repository(tmp_path):
    # A bare repository is the git directory itself: nothing to work in, and
    # every bit as clonable as the checkout it was made from.
    project_dir = tmp_path / "project"
    make_bare_repository(project_dir / "lib.git")

    settled = source_location.parse("git+lib.git", str(project_dir))

    assert settled.kind == "git"


def test_parse_classifies_a_bare_repository_as_git(tmp_path):
    project_dir = tmp_path / "project"
    make_bare_repository(project_dir / "lib.git")

    assert source_location.parse("lib.git", str(project_dir)).kind == "git"


def test_parse_honours_an_explicit_directory_kind_on_a_git_checkout(tmp_path):
    project_dir = tmp_path / "project"
    make_repository(project_dir / "recipes")

    settled = source_location.parse("directory+recipes", str(project_dir))

    assert settled.kind == "directory"


def test_parse_honours_an_explicit_kind_on_a_remote_url(tmp_path):
    settled = source_location.parse(
        "git+https://github.com/GolemCpp/recipes.git", str(tmp_path)
    )

    assert settled.kind == "git"
    assert settled.locator == Locator("https://github.com/GolemCpp/recipes.git")


def test_parse_refuses_an_unknown_kind(tmp_path):
    with pytest.raises(ValueError) as error:
        source_location.parse(
            "gti+https://github.com/GolemCpp/recipes.git", str(tmp_path)
        )

    assert "unknown source kind 'gti'" in str(error.value)
    assert "git+" in str(error.value)
    assert "directory+" in str(error.value)


def test_parse_does_not_read_a_plus_inside_a_url_as_a_kind(tmp_path):
    settled = source_location.parse("https://host/a+b.git", str(tmp_path))

    assert settled.kind == "git"
    assert settled.locator == Locator("https://host/a+b.git")


def test_parse_reads_the_version_a_remote_location_names(tmp_path):
    settled = source_location.parse("https://host/r.git#^3.0.0", str(tmp_path))

    assert settled.locator == Locator("https://host/r.git")
    assert settled.version == "^3.0.0"
    assert settled.kind == "git"


def test_parse_keeps_a_version_holding_a_slash(tmp_path):
    # A namespaced ref is the common shape, and only the first separator counts.
    settled = source_location.parse(
        "git+https://host/r.git#release/1.2.3", str(tmp_path)
    )

    assert settled.locator == Locator("https://host/r.git")
    assert settled.version == "release/1.2.3"


def test_parse_leaves_the_version_empty_when_none_is_named(tmp_path):
    # Empty means unasked. What an unasked version follows is the resource kind's
    # business, not the syntax's.
    assert source_location.parse("https://host/r.git", str(tmp_path)).version == ""


def test_parse_reads_a_version_on_a_local_git_checkout(tmp_path):
    project_dir = tmp_path / "project"
    checkout = make_repository(project_dir / "mylib")

    settled = source_location.parse("mylib#v1.2.0", str(project_dir))

    assert settled.locator == Locator(checkout.resolve().as_uri())
    assert settled.version == "v1.2.0"


def test_parse_reads_a_version_spelled_on_a_file_url(tmp_path):
    # The same locator as above, spelled the way golem itself writes one back.
    # `#` is a fragment to a URL parser and a version separator here, and a
    # location means the same thing whichever way it was spelled.
    project_dir = tmp_path / "project"
    checkout = make_repository(project_dir / "mylib")

    settled = source_location.parse(
        checkout.resolve().as_uri() + "#v1.2.0", str(project_dir)
    )

    assert settled.locator == Locator(checkout.resolve().as_uri())
    assert settled.version == "v1.2.0"


def test_parse_does_not_read_a_separator_inside_a_directory_name(tmp_path):
    # `#` is legal in a path. A location naming a directory as it stands is that
    # directory, never a versioned request for part of it.
    project_dir = tmp_path / "project"
    checkout = make_repository(project_dir / "weird#name")

    settled = source_location.parse("weird#name", str(project_dir))

    assert settled.locator == Locator(checkout.resolve().as_uri())
    assert settled.version == ""


def test_parse_does_not_read_a_version_on_a_copied_directory(tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / "lib#1").mkdir(parents=True)

    settled = source_location.parse("lib#1", str(project_dir))

    assert settled.kind == "directory"
    assert settled.version == ""


def test_an_explicit_git_kind_looks_behind_a_directory_it_cannot_clone(tmp_path):
    # `weird#name` is there, so it would be the location asked for -- but `git+`
    # says the location is a repository, and this directory is not one. So the
    # separator is read as one after all, and the version behind it found.
    project_dir = tmp_path / "project"
    (project_dir / "weird#name").mkdir(parents=True)
    checkout = make_repository(project_dir / "weird")

    settled = source_location.parse("git+weird#name", str(project_dir))

    assert settled.locator == Locator(checkout.resolve().as_uri())
    assert settled.version == "name"


def test_an_explicit_directory_kind_reads_no_version_at_all(tmp_path):
    # A copied directory has no version to ask for, so nothing here is ambiguous:
    # the separator can only be part of the name, whether that name is there yet
    # or not.
    project_dir = tmp_path / "project"
    make_repository(project_dir / "mylib")

    settled = source_location.parse("directory+mylib#v1.2.0", str(project_dir))

    assert settled.version == ""
    assert settled.locator == Locator((project_dir / "mylib#v1.2.0").resolve().as_uri())


def test_parse_refuses_a_version_asked_of_a_copied_directory(tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / "lib").mkdir(parents=True)

    with pytest.raises(ValueError) as error:
        source_location.parse("lib#v1.2.0", str(project_dir))

    assert "a copied directory is whatever it holds now" in str(error.value)


def test_an_scp_style_remote_keeps_its_spelling_and_takes_a_version(tmp_path):
    # The form a host hands you by default. Rewriting it to ssh:// would not be
    # lossless, so what git gets is what was written.
    settled = source_location.parse(
        "git@github.com:nlohmann/json.git#v3.12.0", str(tmp_path)
    )

    assert settled.kind == "git"
    assert settled.locator == Locator("git@github.com:nlohmann/json.git")
    assert settled.version == "v3.12.0"
    # And its identity says where that path hangs from.
    assert settled.locator.get_id() == "@json@nlohmann@github.com@scp.git"


def test_a_transport_helper_passes_through_untouched(tmp_path):
    # `<transport>::<address>` dispatches to a git-remote-<transport> on PATH.
    # Golem cannot know what those are, so it does not try to.
    settled = source_location.parse("hg::https://host/repo#default", str(tmp_path))

    assert settled.locator == Locator("hg::https://host/repo")
    assert settled.version == "default"


def test_a_windows_drive_is_a_path_not_a_remote(tmp_path):
    # `C:` reads as an scp-style host by the colon rule. Git makes the exception
    # and so must golem, on every platform, since a cache is shared between them.
    settled = source_location.parse("C:/proj/mylib", str(tmp_path))

    assert settled.locator.is_local()


def test_a_path_holding_a_colon_needs_the_leading_dot(tmp_path, monkeypatch):
    # Git's own escape hatch, inherited rather than reinvented so the two can
    # never disagree about what a locator is.
    #
    # The disk is made to claim the name rather than hold it: a colon cannot be in
    # a Windows filename, and the dot is what answers for it either way.
    monkeypatch.setattr(os.path, "isdir", lambda path: True)

    assert source_location.parse("./weird:name", str(tmp_path)).locator.is_local()
    assert not source_location.parse("weird:name", str(tmp_path)).locator.is_local()


def test_a_version_on_a_url_needs_no_filesystem_to_be_found(tmp_path):
    # Nothing here is on this machine, so no probe can help: in a URL an
    # unencoded `#` is never part of the path and always starts a version.
    settled = source_location.parse("file:///absent/mylib#v1.2.0", str(tmp_path))

    assert settled.locator == Locator("file:///absent/mylib")
    assert settled.version == "v1.2.0"


def test_a_location_standing_for_a_source_is_read_as_an_identity(tmp_path):
    # `is_bare_path` reads `@boost` as a relative path, so the `@` has to be
    # asked about first or the identity is rejected as a path that is not there.
    settled = read("@boost", tmp_path)

    assert settled.names_an_identity
    assert str(settled.identity) == "@boost"


def test_an_identity_is_stored_as_it_spells_back(tmp_path):
    # Reading folds case and drops a trailing empty field, so one identity has
    # one spelling everywhere below this.
    settled = read("@JSON@Nlohmann@GitHub.com@", tmp_path)

    assert str(settled.identity) == "@json@nlohmann@github.com"


def test_an_identity_may_name_the_version_asked_of_it(tmp_path):
    settled = read("@boost#^1.87.0", tmp_path)

    assert str(settled.identity) == "@boost"
    assert settled.version == "^1.87.0"


def test_a_kind_spelled_on_an_identity_is_refused(tmp_path):
    # The grammar has no production for it, but split_kind runs first, so the
    # prefix is gone by the time the `@` is seen.
    with pytest.raises(ValueError, match="spells a kind on an identity"):
        read("git+@boost", tmp_path)


def test_a_directory_named_like_an_identity_is_written_as_a_path(tmp_path):
    (tmp_path / "@boost").mkdir()

    settled = read("./@boost", tmp_path)

    assert not settled.names_an_identity
    assert settled.locator.is_local()


def test_an_identity_that_is_no_identity_is_refused_where_it_was_written(tmp_path):
    with pytest.raises(ValueError, match="more than the four fields"):
        read("@a@b@c@d@e", tmp_path)


def test_an_identity_is_refused_where_nothing_can_resolve_it(tmp_path):
    # A cookbook, an overlay and an override are not resolved out of an identity
    # today. Nothing about an identity forbids it, so the rule is what is
    # supported rather than what is possible.
    with pytest.raises(ValueError, match="only a dependency's source"):
        read("@boost", tmp_path, identity_allowed=False)


def test_refusing_is_what_a_caller_gets_without_asking(tmp_path):
    # The default is what a caller added later inherits, so it is the one that
    # says no.
    with pytest.raises(ValueError, match="only a dependency's source"):
        source_location.parse("@boost", str(tmp_path))


@pytest.mark.parametrize("kind", ["git", "directory"])
def test_a_field_taking_a_locator_refuses_an_identity(tmp_path, kind):
    # `repository=` and `directory=` never reach resolve_location, so `@boost`
    # would otherwise become a path under the project nobody wrote.
    with pytest.raises(ValueError, match="takes where a source is"):
        source_location.resolve_locator("@boost", kind, str(tmp_path))


def test_a_location_naming_a_source_indirectly_says_so():
    settled = SourceLocation.for_identity(SourceId.parse("@boost"))

    assert settled.names_an_identity


def test_a_location_saying_where_a_source_is_does_not():
    settled = SourceLocation.for_locator(
        Locator("https://host.xz/repo.git"), kind=source.SOURCE_TYPE_GIT
    )

    assert not settled.names_an_identity


def test_a_location_naming_an_identity_carries_no_kind():
    # Nothing is there to detect one from: whatever resolves the identity is
    # what says where the source is, and therefore what it turns out to be.
    settled = SourceLocation.for_identity(SourceId.parse("@boost"))

    assert settled.kind == ""
    assert settled.locator is None


def test_either_shape_may_name_a_version():
    asked = SourceLocation.for_identity(SourceId.parse("@boost"), "^1.87.0")
    written = SourceLocation.for_locator(
        Locator("https://host.xz/repo.git"),
        kind=source.SOURCE_TYPE_GIT,
        version="^1.87.0",
    )

    assert asked.version == written.version == "^1.87.0"
