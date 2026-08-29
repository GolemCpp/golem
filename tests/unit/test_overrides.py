import json

from golemcpp.golem.dependency import Dependency
from golemcpp.golem.overrides import apply_overrides
from golemcpp.golem.overrides import merge_overrides
from golemcpp.golem.overrides import read_overrides
from golemcpp.golem.overrides import write_overrides
from golemcpp.golem.overrides import OVERRIDDEN_MEMBERS


def write_configuration(directory, entries, name="overrides.json"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


def make_dependency(**kwargs):
    dependency = Dependency(**kwargs)
    dependency.update_source("")
    return dependency


# -- reading and writing ----------------------------------------------------


def test_read_overrides_names_the_source_the_way_a_project_file_does(tmp_path):
    lib_dir = tmp_path / "mylib"
    lib_dir.mkdir()
    path = write_configuration(
        tmp_path / "overlay",
        [
            {"repository": "https://host/json.git", "version": "^3.0.0"},
            {"location": "mylib"},
        ],
    )

    overrides = read_overrides(path, str(tmp_path))

    assert overrides[0].resolved.locator == "https://host/json.git"
    # A `location` is read against the project, so a relative path lands on it.
    assert overrides[1].resolved.locator == lib_dir.resolve().as_uri()
    assert overrides[1].resolved.kind == "directory"


def test_write_overrides_round_trips_through_read_overrides(tmp_path):
    path = write_configuration(
        tmp_path / "overlay",
        [{"repository": "https://host/json.git", "version": "^3.0.0", "shallow": True}],
    )
    overrides = read_overrides(path, str(tmp_path))

    written = write_overrides(overrides, str(tmp_path / "build" / "overrides.json"))
    reread = read_overrides(written, str(tmp_path))

    assert [override.repository for override in reread] == ["https://host/json.git"]
    assert reread[0].version == "^3.0.0"
    assert reread[0].shallow is True


def test_write_overrides_creates_the_directory_it_writes_into(tmp_path):
    path = write_overrides([], str(tmp_path / "missing" / "overrides.json"))

    assert json.loads(open(path).read()) == []


# -- layering ---------------------------------------------------------------


def test_merge_overrides_writes_only_the_members_a_layer_sets():
    first = make_dependency(
        repository="https://host/json.git", version="^3.0.0", shallow=True
    )
    second = make_dependency(repository="https://host/json.git", version="^4.0.0")

    merged = merge_overrides([[first], [second]])

    assert len(merged) == 1
    assert merged[0].version == "^4.0.0"
    assert merged[0].shallow is True


def test_merge_overrides_keeps_declaration_order():
    first = make_dependency(repository="https://host/json.git", version="^3.0.0")
    second = make_dependency(repository="https://host/fmt.git", version="^10.0.0")
    third = make_dependency(repository="https://host/json.git", shallow=True)

    merged = merge_overrides([[first, second], [third]])

    assert [override.repository for override in merged] == [
        "https://host/json.git",
        "https://host/fmt.git",
    ]


def test_merge_overrides_separates_entries_by_the_source_they_override():
    repository = make_dependency(repository="https://host/mylib.git", version="^1.0.0")
    directory = make_dependency(directory="/srv/mylib", version="^2.0.0")

    merged = merge_overrides([[repository, directory]])

    assert len(merged) == 2


def test_merge_overrides_of_nothing_is_nothing():
    assert merge_overrides([]) == []
    assert merge_overrides([[], []]) == []


# -- applying ---------------------------------------------------------------


def test_apply_overrides_patches_the_dependency_from_the_same_source():
    dependency = make_dependency(repository="https://host/json.git", version="^3.0.0")
    override = make_dependency(repository="https://host/json.git", version="^4.0.0")
    override.variant = ["release"]

    apply_overrides([override], [dependency])

    assert dependency.version == "^4.0.0"
    assert dependency.variant == ["release"]


def test_apply_overrides_leaves_an_unnamed_dependency_alone():
    dependency = make_dependency(repository="https://host/fmt.git", version="^10.0.0")
    override = make_dependency(repository="https://host/json.git", version="^4.0.0")

    apply_overrides([override], [dependency])

    assert dependency.version == "^10.0.0"


def test_apply_overrides_matches_a_directory_dependency():
    dependency = make_dependency(directory="/srv/mylib", version="^1.0.0")
    override = make_dependency(directory="/srv/mylib", version="^2.0.0")

    apply_overrides([override], [dependency])

    assert dependency.version == "^2.0.0"


def test_apply_overrides_keeps_what_an_override_does_not_set():
    dependency = make_dependency(repository="https://host/json.git", version="^3.0.0")
    dependency.link = ["static"]
    override = make_dependency(repository="https://host/json.git")
    override.variant = ["release"]

    apply_overrides([override], [dependency])

    assert dependency.version == "^3.0.0"
    assert dependency.link == ["static"]
    assert dependency.variant == ["release"]


def test_apply_overrides_never_writes_the_source_members():
    # An override says which dependency is meant by its source; overwriting it
    # would repoint the dependency instead of patching it.
    assert "repository" not in OVERRIDDEN_MEMBERS
    assert "directory" not in OVERRIDDEN_MEMBERS
    assert "location" not in OVERRIDDEN_MEMBERS
    assert "name" not in OVERRIDDEN_MEMBERS
