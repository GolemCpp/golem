from golemcpp.golem.dependency import Dependency
from golemcpp.golem.project import Project


STUB_REVISION = '65ee68451d8eb2b5f3a30b410476ab83deb3289b'


def make_project(*dependencies):
    project = Project(project_dir='/proj')
    project.deps = list(dependencies)
    return project


def declare(**declared):
    '''A dependency as a project file spells it, read against a project.'''
    dependency = Dependency(**declared)
    dependency.update_source('/proj', identity_allowed=True)
    return dependency


def record(locator='https://host/json.git', revision=STUB_REVISION, **declared):
    '''What a dependencies.json holds for one dependency.'''
    return {
        'name': 'json',
        'repository': locator,
        'resolved': {
            'locator': locator,
            'kind': 'git',
            'version': {'reference': 'v3.12.0', 'revision': revision},
        },
        **declared,
    }


def test_a_cached_entry_for_this_dependency_is_restored():
    project = make_project(declare(name='json', repository='https://host/json.git',
                                   version='^3.0.0'))

    project.deps_load_json([record(version='^3.0.0')])

    assert project.deps[0].resolved.version.revision == STUB_REVISION


def test_an_edited_version_leaves_a_cached_entry_stale(capsys):
    # The revision was resolved from `^3.0.0`, therefore restoring it for
    # `^4.0.0` would hand back a version nobody is asking for.
    project = make_project(declare(name='json', repository='https://host/json.git',
                                   version='^4.0.0'))

    project.deps_load_json([record(version='^3.0.0')])

    assert not project.deps[0].resolved.version
    assert 'no cached version' in capsys.readouterr().out


def test_an_edited_version_regex_leaves_one_stale_too(capsys):
    # It filters the tags a range is matched against, so changing it can select
    # another tag for a spec that never moved.
    project = make_project(declare(name='json', repository='https://host/json.git',
                                   version='^3.0.0', version_regex=r'^v\d'))

    project.deps_load_json([record(version='^3.0.0', version_regex='')])

    assert not project.deps[0].resolved.version
    assert 'no cached version' in capsys.readouterr().out


def test_an_edited_source_leaves_a_cached_entry_stale(capsys):
    # A revision was resolved out of one repository, therefore restoring it for
    # another would name a commit that repository may not hold.
    project = make_project(declare(name='json', repository='https://host/new.git',
                                   version='^3.0.0'))

    project.deps_load_json([record(locator='https://host/old.git',
                                   version='^3.0.0')])

    assert not project.deps[0].resolved.version
    assert 'no cached version' in capsys.readouterr().out


def test_an_identity_is_compared_as_it_was_declared():
    # A dependency named by one has no resolved locator until a cookbook
    # answers it, and needs none: the declaration is on both sides.
    project = make_project(declare(name='json', location='@json@nlohmann',
                                   version='^3.0.0'))

    project.deps_load_json([record(location='@json@nlohmann', repository='',
                                   version='^3.0.0')])

    assert project.deps[0].resolved.version.revision == STUB_REVISION
    assert project.deps[0].resolved.locator == 'https://host/json.git'


def test_an_edited_identity_leaves_a_cached_entry_stale(capsys):
    project = make_project(declare(name='json', location='@json@acme',
                                   version='^3.0.0'))

    project.deps_load_json([record(location='@json@nlohmann', repository='',
                                   version='^3.0.0')])

    assert not project.deps[0].resolved.version
    assert 'no cached version' in capsys.readouterr().out


def test_a_copied_directory_is_never_asked_for_a_cached_version(capsys):
    # It has no version to have cached, so reporting one missing would name a
    # failure that cannot happen.
    project = make_project(declare(name='mylib', directory='/srv/mylib'))

    project.deps_load_json([])

    assert 'no cached version' not in capsys.readouterr().out


def test_a_cached_entry_for_another_dependency_is_not_read(capsys):
    project = make_project(declare(name='json', repository='https://host/json.git',
                                   version='^3.0.0'))

    project.deps_load_json([record(name='boost', version='^3.0.0')])

    assert not project.deps[0].resolved.version
    assert 'no cached version' in capsys.readouterr().out
