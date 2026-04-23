from golemcpp.golem.version import Version


def test_parse_git_hash_accepts_short_and_long_hashes():
    assert Version.parse_git_hash('abcdef1') == ('abcdef1', 'abcdef1')
    assert Version.parse_git_hash('abcdef1234567890') == ('abcdef1', 'abcdef1234567890')


def test_parse_git_hash_rejects_non_hash_values():
    assert Version.parse_git_hash('v1.2.3') is None


def test_parse_semver_accepts_standard_semver():
    parsed = Version.parse_semver('1.2.3-beta+build.5')

    assert parsed is not None
    assert parsed[0] == '1.2.3-beta+build.5'


def test_parse_semver_normalizes_alternative_separators():
    parsed = Version.parse_semver('1_2_3-rc_1+build.5')

    assert parsed is not None
    assert parsed[0] == '1.2.3-rc_1+build.5'


def test_parse_semver_fills_missing_minor_and_patch_with_zeroes():
    parsed = Version.parse_semver('7')

    assert parsed is not None
    assert parsed[0] == '7.0.0'


def test_force_version_updates_semver_fields_and_build_metadata():
    version = Version(build_number=42)

    version.force_version('v1.2.3-rc.1')

    assert version.semver == '1.2.3-rc.1+42'
    assert version.semver_short == '1.2.3'
    assert version.major == 1
    assert version.minor == 2
    assert version.patch == 3
    assert version.prerelease == 'rc.1'
    assert version.buildmetadata == '42'