import pytest

from golemcpp.golem import dependency_reference
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.source_id import SourceId


def refer(text, project_directory="/proj"):
    return dependency_reference.read(text, project_directory)


def test_an_identity_is_read_as_itself():
    reference = refer("@boost@boostorg@github.com")

    assert str(reference.identity) == "@boost@boostorg@github.com"
    assert reference.version == ""


def test_a_reference_may_name_a_version():
    reference = refer("@boost#^1.87.0")

    assert str(reference.identity) == "@boost"
    assert reference.version == "^1.87.0"


def test_a_locator_composes_an_identity():
    # Which is what lets one set of rules answer both shapes of a location.
    reference = refer("https://github.com/boostorg/boost.git")

    assert str(reference.identity) == "@boost@boostorg@github.com"


def test_a_path_composes_one_too(tmp_path):
    (tmp_path / "mylib").mkdir()

    assert str(refer("./mylib", str(tmp_path)).identity).startswith("@mylib@")


def test_an_entry_naming_no_source_is_still_a_reference():
    # Naming no source is a reading rather than a failure: the entry may still
    # be a declared name, which is matched by whoever holds the project.
    reference = refer("bosot")

    assert reference.text == "bosot"
    assert not reference.names_a_source


def test_a_path_with_nothing_there_carries_the_path_it_read(tmp_path):
    # The useful half of the refusal: a typo would otherwise become a dependency
    # on a path nobody wrote, failing much later.
    #
    # Read against a real directory rather than the default: a bare `/proj` picks
    # up the current drive on Windows, so the expected path would have to compose
    # one to compare against.
    read = refer("bosot", str(tmp_path))

    assert read.missing_path == str(tmp_path / "bosot")
    assert read.refused_by is None
    assert "does not exist" in read.explain()


def test_a_reference_the_grammar_refuses_carries_what_it_said():
    # Read once, so the reason cannot disagree with the decision to refuse.
    read = refer("git+@boost")

    assert read.refused_by is not None
    assert not read.missing_path
    assert read.explain() == str(read.refused_by)


def test_a_reference_asks_for_a_source_qualified_further_than_itself():
    identity = SourceId.parse("@boost@boostorg@github.com")

    assert refer("@boost").is_asking_for_the_source(identity)
    assert refer("@boost@boostorg").is_asking_for_the_source(identity)
    assert refer("@boost@boostorg@github.com").is_asking_for_the_source(identity)


def test_a_reference_qualified_further_than_a_source_does_not_ask_for_it():
    # A reference reaches a declaration by being less qualified than it, never
    # more, so the full URL never reaches a recipe-shortened declaration.
    identity = SourceId.parse("@boost")

    assert not refer("@boost@boostorg").is_asking_for_the_source(identity)
    assert not refer("https://github.com/boostorg/boost.git").is_asking_for_the_source(
        identity
    )


def declare(**fields):
    """A dependency as a project file spells it, read against a project."""
    dependency = Dependency(**fields)
    dependency.update_source("/proj", identity_allowed=True)
    return dependency


def find(text, *dependencies):
    return dependency_reference.find_dependency_referred_to(
        text, list(dependencies), "/proj"
    )


def imply(texts, *dependencies):
    return dependency_reference.find_references_to_imply(
        texts, list(dependencies), "/proj"
    )


def test_a_reference_reaches_the_dependency_whose_source_it_asks_for():
    dependency = declare(location="@boost@boostorg@github.com")

    assert find("@boost", dependency) is dependency
    assert find("@boost@boostorg@github.com", dependency) is dependency


def test_a_reference_reaches_no_dependency_golem_added_itself():
    # An entry names what a project file declared, and a transitive entry carries
    # the local name of the project that declared it.
    dependency = declare(name="boost", location="@boost")
    dependency.dynamically_added = True

    assert find("boost", dependency) is None


def test_a_name_wins_over_the_source_it_would_otherwise_be_read_as():
    named = declare(name="@boost", location="@boost@myfork")
    other = declare(location="@boost@boostorg")

    assert find("@boost", named, other) is named


def test_a_reference_naming_two_dependencies_is_refused():
    with pytest.raises(RuntimeError) as refusal:
        find(
            "@boost",
            declare(location="@boost@boostorg"),
            declare(location="@boost@myfork"),
        )

    assert "@boost@boostorg" in str(refusal.value)
    assert "@boost@myfork" in str(refusal.value)


def test_a_reference_naming_one_of_two_rung_sharing_dependencies_is_answered():
    forked = declare(location="@boost@myfork")

    assert find("@boost@myfork", declare(location="@boost@boostorg"), forked) is forked


def test_a_reference_contradicting_a_declared_version_is_refused():
    with pytest.raises(RuntimeError) as refusal:
        find("@boost#^1.87.0", declare(location="@boost", version="^1.80.0"))

    assert "^1.87.0" in str(refusal.value)
    assert "^1.80.0" in str(refusal.value)


def test_an_entry_no_dependency_answers_is_implied():
    assert [reference.text for reference in imply(["@boost"])] == ["@boost"]


def test_a_declaration_claims_an_entry_rather_than_a_second_being_implied():
    assert imply(["@boost"], declare(location="@boost@boostorg")) == []


def test_two_entries_naming_one_source_imply_one_dependency():
    # The dependency an earlier entry implies is not declared yet, so the entries
    # are compared to each other.
    assert [
        reference.text for reference in imply(["@boost", "@boost@boostorg@github.com"])
    ] == ["@boost", "@boost@boostorg@github.com"]
    assert [reference.text for reference in imply(["@boost", "@boost"])] == ["@boost"]


def test_two_entries_asking_two_versions_imply_two_dependencies():
    # The negative of the one above: the version is part of what an entry asks
    # for, so neither passes by the matching being too eager.
    assert [
        reference.version
        for reference in imply(["@boost#^1.87.0", "@boost#^1.80.0", "@boost"])
    ] == ["^1.87.0", "^1.80.0", ""]


def test_an_entry_naming_neither_a_dependency_nor_a_source_is_refused():
    with pytest.raises(RuntimeError) as refusal:
        imply(["bosot"], declare(name="lib", location="@boost"))

    assert "bosot" in str(refusal.value)
    assert "lib" in str(refusal.value)
    assert "does not exist" in str(refusal.value)
