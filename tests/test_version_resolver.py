from golemcpp.golem import version_resolver
from golemcpp.golem.version_resolver import VersionResolver


def test_find_version_matches_semver_spec():
    assert VersionResolver.find_version(['1.2.2', '1.2.3', '1.2.4'], '~1.2.0') == '1.2.4'


def test_find_version_accepts_major_only_tags_in_version_list():
    assert VersionResolver.find_version(['1', '1.2', '2.0.0'], '1') == '1.2'


def test_find_version_accepts_major_minor_tags_in_version_list():
    assert VersionResolver.find_version(['1.2', '1.2.9', '1.3'], '1.2') == '1.2.9'


def test_find_version_preserves_existing_full_semver_behavior():
    assert VersionResolver.find_version(['1.2.2', '1.2.3', '1.2.4'], '1.2.3') == '1.2.3'


def test_find_version_accepts_major_only_tag_with_full_semver_query():
    assert VersionResolver.find_version(['1', '2'], '^1.0.0') == '1'


def test_find_version_accepts_openssl_style_suffix_tags():
    assert VersionResolver.find_version(
        ['OpenSSL_1_1_1i', 'OpenSSL_1_1_1j'], '~1.1.1') == 'OpenSSL_1_1_1j'


def test_find_version_accepts_v_prefixed_major_tag():
    assert VersionResolver.find_version(['v1', 'v2'], '1') == 'v1'


def test_find_version_accepts_v_prefixed_major_minor_tag():
    assert VersionResolver.find_version(['v5.1', 'v5.2'], '5.2') == 'v5.2'


def test_find_version_accepts_boost_style_prerelease_suffix_tag():
    assert VersionResolver.find_version(
        ['boost-1.91.0-1', 'boost-1.90.0'], '>=1.91.0-0 <1.92.0') == 'boost-1.91.0-1'


def test_find_version_accepts_prefixed_short_underscore_tag():
    assert VersionResolver.find_version(['foo_1_1', 'foo_1_2'], '1.2') == 'foo_1_2'


def test_resolve_returns_dash_for_local_non_git_directory(monkeypatch):
    monkeypatch.setattr(
        version_resolver.Source, 'parse_local_non_git_repository',
        staticmethod(lambda url: '/some/local/dir'))
    assert VersionResolver.resolve('file:///some/local/dir', '') == ('-', '-')


def test_resolve_matches_tag_and_returns_hash(monkeypatch):
    monkeypatch.setattr(
        version_resolver.Source, 'parse_local_non_git_repository',
        staticmethod(lambda url: None))

    def fake_git(args, cwd):
        if '--tags' in args and args[-1].startswith('refs/tags/'):
            return 'cafebabecafebabe\trefs/tags/v3.12.0\n'
        if '--tags' in args:
            return 'deadbeef\trefs/tags/v3.11.0\ncafebabe\trefs/tags/v3.12.0\n'
        return ''

    monkeypatch.setattr(version_resolver.helpers, 'check_git_output', fake_git)

    resolved_version, resolved_hash = VersionResolver.resolve(
        'https://github.com/nlohmann/json.git', '^3.0.0')
    assert resolved_version == 'v3.12.0'
    assert resolved_hash == 'cafebabecafebabe'


def test_resolve_falls_back_to_branch_head(monkeypatch):
    monkeypatch.setattr(
        version_resolver.Source, 'parse_local_non_git_repository',
        staticmethod(lambda url: None))

    def fake_git(args, cwd):
        if '--tags' in args:
            return ''  # no tags
        if '--heads' in args:
            return 'abc123\trefs/heads/main\n'
        return ''

    monkeypatch.setattr(version_resolver.helpers, 'check_git_output', fake_git)

    resolved_version, resolved_hash = VersionResolver.resolve(
        'https://example.com/x.git', 'main')
    assert resolved_version == 'main'
    assert resolved_hash == 'abc123'
