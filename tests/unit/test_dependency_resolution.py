from golemcpp.golem.dependency_resolution import DependencyResolution
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source_id import SourceId


def test_a_resolution_that_worked_nothing_out_says_so():
    assert not DependencyResolution()


def test_reading_a_location_is_already_something_worked_out():
    # True before anything is resolved, therefore a caller asking whether a
    # version was found has to ask for the version.
    settled = DependencyResolution(locator='https://host.xz/r.git', kind='git')

    assert settled
    assert not settled.version


def test_settling_where_a_source_is_composes_what_names_it():
    # The identity follows from the locator, therefore settling one without the
    # other would leave a resolution disagreeing with itself.
    settled = DependencyResolution().settle_locator(
        'https://github.com/nlohmann/json.git', 'git')

    assert settled.identity == SourceId.parse('@json@nlohmann@github.com')


def test_settling_a_field_keeps_what_an_earlier_pass_worked_out():
    # Two passes fill one of these: reading the location, then resolving.
    read = DependencyResolution(locator='https://host.xz/r.git', kind='git')

    resolved = read.settle_version(
        ResolvedVersion(reference='v1', revision='abc'))

    assert resolved.locator == 'https://host.xz/r.git'
    assert resolved.kind == 'git'
    assert resolved.version == ResolvedVersion(reference='v1', revision='abc')


def test_a_resolution_survives_a_round_trip():
    settled = DependencyResolution(
        locator='https://github.com/nlohmann/json.git',
        kind='git',
        identity=SourceId.parse('@json@nlohmann@github.com'),
        version=ResolvedVersion(reference='v3.12.0', revision='55f9368'))

    assert DependencyResolution.from_dict(settled.to_dict()) == settled


def test_an_identity_comes_back_as_an_identity():
    # Written out it is text, and everything reading one takes it for an
    # identity rather than a string that looks like one.
    settled = DependencyResolution(identity=SourceId.parse('@boost'))

    assert DependencyResolution.from_dict(settled.to_dict()).identity == \
        SourceId.parse('@boost')


def test_nothing_recorded_is_nothing_worked_out():
    assert not DependencyResolution.from_dict({})
    assert not DependencyResolution.from_dict(None)
