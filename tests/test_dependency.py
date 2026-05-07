from golemcpp.golem.dependency import Dependency


def test_find_version_accepts_major_only_tags_in_version_list():
    version = Dependency.find_version(['1', '1.2', '2.0.0'], '1')

    assert version == '1.2'


def test_find_version_accepts_major_minor_tags_in_version_list():
    version = Dependency.find_version(['1.2', '1.2.9', '1.3'], '1.2')

    assert version == '1.2.9'


def test_find_version_preserves_existing_full_semver_behavior():
    version = Dependency.find_version(['1.2.2', '1.2.3', '1.2.4'], '1.2.3')

    assert version == '1.2.3'


def test_find_version_accepts_major_only_tag_with_full_semver_query():
    version = Dependency.find_version(['1', '2'], '^1.0.0')

    assert version == '1'


def test_find_version_accepts_openssl_style_suffix_tags():
    version = Dependency.find_version(['OpenSSL_1_1_1i', 'OpenSSL_1_1_1j'], '~1.1.1')

    assert version == 'OpenSSL_1_1_1j'


def test_find_version_accepts_v_prefixed_major_tag():
    version = Dependency.find_version(['v1', 'v2'], '1')

    assert version == 'v1'


def test_find_version_accepts_v_prefixed_major_minor_tag():
    version = Dependency.find_version(['v5.1', 'v5.2'], '5.2')

    assert version == 'v5.2'


def test_find_version_accepts_boost_style_prerelease_suffix_tag():
    version = Dependency.find_version(['boost-1.91.0-1', 'boost-1.90.0'], '>=1.91.0-0 <1.92.0')

    assert version == 'boost-1.91.0-1'


def test_find_version_accepts_prefixed_short_underscore_tag():
    version = Dependency.find_version(['foo_1_1', 'foo_1_2'], '1.2')

    assert version == 'foo_1_2'