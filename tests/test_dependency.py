from golemcpp.golem.dependency import Dependency


def test_dependency_accepts_repository_keyword():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    assert dep.repository == 'https://example.com/json.git'
    assert dep.directory == ''
    assert dep.is_non_git_directory() is False


def test_dependency_accepts_directory_keyword():
    dep = Dependency(name='mylib', directory='./mylib')
    assert dep.directory == './mylib'
    assert dep.repository == ''
    assert dep.is_non_git_directory() is True
    # A directory dependency has no version to resolve.
    assert dep.resolve() == '-'
    source = dep.to_source()
    assert source.type == 'directory'
    assert source.location == './mylib'


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