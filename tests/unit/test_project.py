import json
from types import SimpleNamespace

from golemcpp.golem.dependency import Dependency
from golemcpp.golem.project import Project
from golemcpp.golem.source_id import SourceId

STUB_REVISION = "65ee68451d8eb2b5f3a30b410476ab83deb3289b"


def make_project(*dependencies):
    project = Project(project_dir="/proj")
    project.deps = list(dependencies)
    return project


def declare(**declared):
    """A dependency as a project file spells it, read against a project."""
    dependency = Dependency(**declared)
    dependency.update_source("/proj", identity_allowed=True)
    return dependency


def record(locator="https://host/json.git", revision=STUB_REVISION, **declared):
    """What a dependencies.json holds for one dependency."""
    return {
        "name": "json",
        "repository": locator,
        "resolved": {
            "locator": locator,
            "kind": "git",
            "version": {"reference": "v3.12.0", "revision": revision},
        },
        **declared,
    }


def test_a_cached_entry_for_this_dependency_is_restored():
    project = make_project(
        declare(name="json", repository="https://host/json.git", version="^3.0.0")
    )

    project.deps_load_json([record(version="^3.0.0")])

    assert project.deps[0].resolved.version.revision == STUB_REVISION


def test_an_edited_version_leaves_a_cached_entry_stale(capsys):
    # The revision was resolved from `^3.0.0`, therefore restoring it for
    # `^4.0.0` would hand back a version nobody is asking for.
    project = make_project(
        declare(name="json", repository="https://host/json.git", version="^4.0.0")
    )

    project.deps_load_json([record(version="^3.0.0")])

    assert not project.deps[0].resolved.version
    assert "no cached version" in capsys.readouterr().out


def test_an_edited_version_regex_leaves_one_stale_too(capsys):
    # It filters the tags a range is matched against, so changing it can select
    # another tag for a spec that never moved.
    project = make_project(
        declare(
            name="json",
            repository="https://host/json.git",
            version="^3.0.0",
            version_regex=r"^v\d",
        )
    )

    project.deps_load_json([record(version="^3.0.0", version_regex="")])

    assert not project.deps[0].resolved.version
    assert "no cached version" in capsys.readouterr().out


def test_an_edited_source_leaves_a_cached_entry_stale(capsys):
    # A revision was resolved out of one repository, therefore restoring it for
    # another would name a commit that repository may not hold.
    project = make_project(
        declare(name="json", repository="https://host/new.git", version="^3.0.0")
    )

    project.deps_load_json([record(locator="https://host/old.git", version="^3.0.0")])

    assert not project.deps[0].resolved.version
    assert "no cached version" in capsys.readouterr().out


def test_an_identity_is_compared_as_it_was_declared():
    # A dependency named by one has no resolved locator until a cookbook
    # answers it, and needs none: the declaration is on both sides.
    project = make_project(
        declare(name="json", location="@json@nlohmann", version="^3.0.0")
    )

    project.deps_load_json(
        [record(location="@json@nlohmann", repository="", version="^3.0.0")]
    )

    assert project.deps[0].resolved.version.revision == STUB_REVISION
    assert project.deps[0].resolved.locator == "https://host/json.git"


def test_an_edited_identity_leaves_a_cached_entry_stale(capsys):
    project = make_project(
        declare(name="json", location="@json@acme", version="^3.0.0")
    )

    project.deps_load_json(
        [record(location="@json@nlohmann", repository="", version="^3.0.0")]
    )

    assert not project.deps[0].resolved.version
    assert "no cached version" in capsys.readouterr().out


def test_a_copied_directory_is_never_asked_for_a_cached_version(capsys):
    # It has no version to have cached, so reporting one missing would name a
    # failure that cannot happen.
    project = make_project(declare(name="mylib", directory="/srv/mylib"))

    project.deps_load_json([])

    assert "no cached version" not in capsys.readouterr().out


def test_a_cached_entry_for_another_dependency_is_not_read(capsys):
    project = make_project(
        declare(name="json", repository="https://host/json.git", version="^3.0.0")
    )

    project.deps_load_json([record(name="boost", version="^3.0.0")])

    assert not project.deps[0].resolved.version
    assert "no cached version" in capsys.readouterr().out


def make_chain(name, cookbook):
    """A resolved recipe, as the resolver hands one over."""
    return SimpleNamespace(
        chain=(
            SimpleNamespace(
                rung=SourceId.parse(name), cookbook=SimpleNamespace(cache_key=cookbook)
            ),
        )
    )


def shared_cache(tmp_path, *entries):
    path = tmp_path / "all_dependencies.json"
    path.write_text(json.dumps(list(entries)), encoding="utf-8")
    return str(path)


def read_shared_cache(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_shared_cache_records_which_recipe_served_a_dependency(tmp_path):
    # The entries were written before anything was fetched, so they carry no
    # recipe until the chain is known.
    dependency = declare(
        name="json", repository="https://host/json.git", version="^3.0.0"
    )
    dependency.resolved = dependency.resolved.settle_recipe(make_chain("@json", "base"))
    path = shared_cache(tmp_path, record(name=None, version="^3.0.0"))

    make_project(dependency).record_recipes(path)

    assert read_shared_cache(path)[0]["resolved"]["recipe"] == [
        {"name": "@json", "cookbook": "base"}
    ]


def test_the_shared_cache_keeps_what_the_sub_invocations_added(tmp_path):
    # Every sub-invocation appends to the same file, therefore writing back what
    # this project holds would drop their entries.
    dependency = declare(
        name="json", repository="https://host/json.git", version="^3.0.0"
    )
    dependency.resolved = dependency.resolved.settle_recipe(make_chain("@json", "base"))
    path = shared_cache(
        tmp_path,
        record(name=None, version="^3.0.0"),
        record(name=None, locator="https://host/gsl.git", version="*"),
    )

    make_project(dependency).record_recipes(path)

    cached = read_shared_cache(path)
    assert [entry["resolved"]["locator"] for entry in cached] == [
        "https://host/json.git",
        "https://host/gsl.git",
    ]
    assert "recipe" not in cached[1]["resolved"]


def test_an_entry_for_another_request_is_left_alone(tmp_path):
    # Matched on the locator and the version asked of it, which is what
    # identifies an entry there once save_cache has nulled the names.
    dependency = declare(
        name="json", repository="https://host/json.git", version="^3.0.0"
    )
    dependency.resolved = dependency.resolved.settle_recipe(make_chain("@json", "base"))
    path = shared_cache(tmp_path, record(name=None, version="^2.0.0"))

    make_project(dependency).record_recipes(path)

    assert "recipe" not in read_shared_cache(path)[0]["resolved"]


def test_recording_recipes_where_there_is_no_shared_cache_does_nothing(tmp_path):
    make_project().record_recipes(str(tmp_path / "absent.json"))
    make_project().record_recipes("")


def test_a_request_is_identified_by_its_version_regex_too(tmp_path, monkeypatch):
    # The regex filters the candidate tags before the range is matched, so two
    # requests differing only in it can land on different revisions.
    project = make_project(
        declare(
            name="json",
            repository="https://host/json.git",
            version="^3.0.0",
            version_regex="^release-(.*)$",
        )
    )
    path = shared_cache(tmp_path, record(name=None, version="^3.0.0"))

    resolved = []
    monkeypatch.setattr(Dependency, "resolve", lambda self: resolved.append(self.name))
    project.resolve(global_config_file=path, dependencies_to_keep=[])

    assert resolved == ["json"]
    assert len(read_shared_cache(path)) == 2


def test_a_request_already_answered_is_not_resolved_again(tmp_path, monkeypatch):
    project = make_project(
        declare(name="json", repository="https://host/json.git", version="^3.0.0")
    )
    path = shared_cache(tmp_path, record(name=None, version="^3.0.0"))

    resolved = []
    monkeypatch.setattr(Dependency, "resolve", lambda self: resolved.append(self.name))
    project.resolve(global_config_file=path, dependencies_to_keep=[])

    assert resolved == []
    assert len(read_shared_cache(path)) == 1
    assert project.deps[0].resolved.version.reference == "v3.12.0"


def test_a_project_read_from_json_holds_its_definitions_and_exports():
    # The golemfile.json path is exercised end to end by the integration suite
    # alone, so a name gone wrong in it survives `pytest tests/unit` — which is
    # the loop run while editing. `targets` and `exports` stay the written keys;
    # only what a Project calls them changed.
    project = Project.unserialize_from_json(
        json_object={
            "targets": [
                {"name": "mylib", "type": "library"},
                {"name": "hello", "type": "program"},
            ],
            "exports": [{"name": "mylib"}],
        },
        project_dir="/proj",
    )

    assert [definition.name for definition in project.definitions] == ["mylib", "hello"]
    assert [export.name for export in project.exports] == ["mylib"]
    assert all(export.export for export in project.exports)
    assert not any(definition.export for definition in project.definitions)
