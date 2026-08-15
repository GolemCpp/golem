import pytest

from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.locator import Locator


def test_dependency_accepts_repository_keyword():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    assert dep.repository == 'https://example.com/json.git'
    assert dep.directory == ''
    assert dep.is_non_git_directory() is False


def test_dependency_accepts_directory_keyword(tmp_path):
    dep = Dependency(name='mylib', directory='./mylib')
    assert dep.directory == './mylib'
    assert dep.repository == ''
    assert dep.is_non_git_directory() is True
    # A directory dependency has no version to resolve, and resolving one names
    # nothing rather than standing something in for it.
    assert dep.resolve() == ResolvedVersion()
    assert not dep.resolved
    # Idempotent, and never serialized: there is nothing to record.
    assert dep.resolve() == ResolvedVersion()
    assert 'resolved' not in Dependency.serialize_to_json(dep)

    # As a Source only once the path has been resolved against the project it was
    # declared in, which is what every reader of a dependency does first.
    dep.update_source(str(tmp_path))
    source = dep.to_source()
    assert source.type == 'directory'
    assert source.locator == Locator((tmp_path / 'mylib').resolve().as_uri())


def test_a_dependency_is_not_a_source_before_it_is_resolved_against_a_project():
    # `./mylib` means nothing without the project it was written in, so building
    # a Source from it is refused rather than producing one nothing can locate.
    with pytest.raises(ValueError) as error:
        Dependency(name='mylib', directory='./mylib').to_source()

    assert 'resolved against a project first' in str(error.value)


def test_dependency_serializes_and_round_trips_repository():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload['repository'] == 'https://example.com/json.git'
    assert 'url' not in payload

    restored = Dependency.unserialize_from_json(payload)
    assert restored.repository == 'https://example.com/json.git'


def test_dependency_serializes_directory():
    dep = Dependency(name='mylib', directory='./mylib')
    payload = Dependency.serialize_to_json(dep, avoid_lists=True)
    assert payload['directory'] == './mylib'

    restored = Dependency.unserialize_from_json(payload)
    assert restored.directory == './mylib'


def test_a_dependency_starts_without_a_cached_resource():
    # A DependencyManager fills it in; a dependency restored from a
    # dependencies.json comes back without one.
    assert Dependency(
        name='json', repository='https://example.com/json.git').cached_resource is None


def test_a_location_may_name_the_version(tmp_path):
    dep = Dependency(name='json', location='git+https://host/json.git#^3.0.0')
    dep.update_source(str(tmp_path))

    assert dep.repository == 'https://host/json.git'
    assert dep.version == '^3.0.0'


def test_a_location_naming_no_version_leaves_the_version_alone(tmp_path):
    # Empty means the latest release for a dependency, which is not what a git
    # location with nothing named should silently turn into.
    dep = Dependency(name='json', location='git+https://host/json.git')
    dep.update_source(str(tmp_path))

    assert dep.version == ''


def test_a_declared_version_survives_a_location_naming_none(tmp_path):
    dep = Dependency(
        name='json', location='git+https://host/json.git', version='^3.0.0')
    dep.update_source(str(tmp_path))

    assert dep.version == '^3.0.0'


def test_a_dependency_asking_for_two_versions_is_refused(tmp_path):
    dep = Dependency(
        name='json', location='git+https://host/json.git#v1', version='^3.0.0')

    with pytest.raises(ValueError) as error:
        dep.update_source(str(tmp_path))

    assert "asks for exactly one" in str(error.value)
    assert "'^3.0.0'" in str(error.value)
    assert "'v1'" in str(error.value)
