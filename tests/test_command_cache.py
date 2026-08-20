import os

from conftest import make_source
from golemcpp.golem import cache_configuration
from golemcpp.golem import resource_manifest
from golemcpp.golem import command_cache
from golemcpp.golem import helpers


def seed_resource(cache_root, subdir, name, *, kind=None, source=None, size=64,
                  fetched=None, cache_key=None):
    resource_root = os.path.join(cache_root, subdir, name)
    # Under the root the way an installed resource holds it, so a seeded resource
    # is not reported as an install that never finished.
    source_dir = cache_configuration.source_path(resource_root)
    os.makedirs(source_dir, exist_ok=True)
    with open(os.path.join(source_dir, 'payload'), 'w', encoding='utf-8') as fp:
        fp.write('x' * size)
    if kind is not None:
        resource_manifest.write_manifest(
            resource_root=resource_root,
            kind=kind,
            cache_key=cache_key or name,
            source=source or make_source(),
            fetched=fetched)
    return resource_root


def run(cache_root, *args):
    return command_cache.handle_cache_command(
        project_dir='',
        args=list(args) + ['--cache-directory=' + str(cache_root)])


def test_help(capsys):
    result = command_cache.handle_cache_command(project_dir='', args=['--help'])
    assert result == 0
    out = capsys.readouterr().out
    assert 'Usage: golem cache list' in out
    assert 'golem cache purge' in out
    assert 'unidentified' in out


def test_no_action_prints_help(capsys):
    result = command_cache.handle_cache_command(project_dir='', args=[])
    assert result == 0
    assert 'Usage: golem cache list' in capsys.readouterr().out


def test_unknown_action_is_error(capsys, tmp_path):
    result = run(tmp_path, 'frobnicate')
    assert result == 1
    assert 'unsupported cache command' in capsys.readouterr().out


def test_list_reports_resources(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY,
                  source=make_source(locator='https://github.com/nlohmann/json.git',
                                     reference='v3.12.0',
                                     revision='cafebabe' * 5),
                  fetched={'head': 'cafebabe' * 5, 'mode': 'blobless'})

    result = run(tmp_path, 'list')
    assert result == 0
    out = capsys.readouterr().out

    # One line per resource: what it is, which one, which version of it, how it
    # was obtained, how big it is and how long ago it was used.
    assert 'dependency  json@com.github.nlohmann+abc  v3.12.0 cafebabe  blobless' in out
    assert '1 resource(s),' in out


def test_list_tells_the_versions_of_one_dependency_apart(capsys, tmp_path):
    # Two entries of the same dependency differ by the commit they hold, which is
    # the whole reason both are in the cache.
    for revision in ('9cca280a' * 5, '65ee6845' * 5):
        seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR,
                      'json@com.github.nlohmann+' + revision[:8],
                      kind=resource_manifest.ResourceKind.DEPENDENCY,
                      source=make_source(reference='main', revision=revision))

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out
    assert 'main 9cca280a' in out
    assert 'main 65ee6845' in out


def test_list_says_how_a_resource_was_obtained(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.OVERLAYS_SUBDIR, 'overlay-a@fsys.tmp+',
                  kind=resource_manifest.ResourceKind.OVERLAY,
                  source=make_source(locator='file:///tmp/overlay-a', reference='',
                                     revision='', source_type='directory'))
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'heavy@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY,
                  fetched={'head': 'cafebabe' * 5, 'mode': 'shallow'})

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out

    # A copied directory has no version and no history to obtain part of; a
    # repository says how much of it was fetched.
    assert 'overlay-a@fsys.tmp+  -                directory' in out
    assert 'heavy@h+abc          v1.0.0 cafebabe  shallow' in out


def test_list_flags_an_install_that_never_finished(capsys, tmp_path):
    resource_root = seed_resource(
        str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY)
    helpers.remove_tree(cache_configuration.source_path(resource_root))

    assert run(tmp_path, 'list') == 0
    assert 'incomplete' in capsys.readouterr().out


def test_list_shows_the_most_recently_used_first(capsys, tmp_path):
    for name, last_used in (('old@h+abc', '2020-01-01T00:00:00+00:00'),
                            ('recent@h+abc', '2030-01-01T00:00:00+00:00')):
        root = seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, name,
                             kind=resource_manifest.ResourceKind.DEPENDENCY)
        manifest = resource_manifest.ResourceManifest.read_from_root(root)
        manifest.last_used_at = last_used
        manifest.write_to_root(root)
    # An unidentified resource has no timestamp at all.
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'mystery@h+abc')

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out
    assert out.index('recent@h+abc') < out.index('old@h+abc') < out.index('mystery@h+abc')


def test_list_long_details_every_resource(capsys, tmp_path):
    resource_root = seed_resource(
        str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        source=make_source(locator='https://github.com/nlohmann/json.git',
                           reference='v3.12.0', revision='cafebabe' * 5),
        fetched={'head': 'deadbeef' * 5, 'mode': 'blobless'})

    assert run(tmp_path, 'list', '--long') == 0
    out = capsys.readouterr().out

    assert 'source    git https://github.com/nlohmann/json.git' in out
    # The commit is abbreviated in the listing line and whole in the details.
    assert 'version   v3.12.0 {}'.format('cafebabe' * 5) in out
    assert 'fetched   {}, blobless'.format('deadbeef' * 5) in out
    assert 'manifest  version {}'.format(resource_manifest.MANIFEST_VERSION) in out
    assert 'path      {}'.format(resource_root) in out


def test_list_empty(capsys, tmp_path):
    assert run(tmp_path, 'list') == 0
    assert 'No cached resources found.' in capsys.readouterr().out


def test_list_shows_the_path_under_long(capsys, tmp_path):
    resource_root = seed_resource(
        str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out

    # The listing names a resource by its cache key, which is also what `remove`
    # matches. The path is a detail, therefore it waits for --long.
    assert 'json@com.github.nlohmann+abc' in out
    assert resource_root not in out
    # The resource is listed under a per-cache header (the cache location).
    assert '{}:'.format(str(tmp_path)) in out

    assert run(tmp_path, 'list', '-l') == 0
    assert resource_root in capsys.readouterr().out


def test_list_separates_resources_per_cache(capsys, tmp_path, monkeypatch):
    primary = tmp_path / 'primary'
    secondary = tmp_path / 'secondary'

    seed_resource(
        str(primary), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY, size=100)
    seed_resource(
        str(secondary), cache_configuration.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
        kind=resource_manifest.ResourceKind.DEPENDENCY, size=100)

    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', str(secondary))

    assert run(primary, 'list') == 0
    out = capsys.readouterr().out

    # Each cache is a header of its own, saying what it holds, and the listing
    # closes on what every cache holds together.
    assert '{}: 1 resource(s),'.format(str(primary)) in out
    assert '{}: 1 resource(s),'.format(str(secondary)) in out
    assert 'Total: 2 resource(s),' in out
    assert out.index(str(primary)) < out.index('json@com.github.nlohmann+abc')
    assert out.index(str(secondary)) < out.index('fmt@com.github.fmtlib+def')


def test_caches_lists_configured_location(capsys, tmp_path):
    assert run(tmp_path, 'caches') == 0
    out = capsys.readouterr().out
    assert 'Configured caches:' in out
    assert str(tmp_path) in out
    assert 'writable' in out


def test_size_totals(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'a@h+1',
                  kind=resource_manifest.ResourceKind.DEPENDENCY, size=100)
    assert run(tmp_path, 'size') == 0
    out = capsys.readouterr().out
    assert 'Cache storage usage:' in out
    assert 'By kind:' in out
    assert 'dependency:' in out


def test_unidentified_lists_and_removes(monkeypatch, capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.COOKBOOKS_SUBDIR, 'mystery@host+main')  # no manifest
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'unidentified') == 0
    out = capsys.readouterr().out
    assert 'mystery@host+main' in out
    assert 'json@h+abc' not in out

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: True)
    assert run(tmp_path, 'unidentified', '--remove') == 0
    assert not os.path.exists(os.path.join(str(tmp_path), cache_configuration.COOKBOOKS_SUBDIR, 'mystery@host+main'))
    # Identified resource is untouched.
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_requires_pattern(capsys, tmp_path):
    assert run(tmp_path, 'remove') == 1
    assert 'remove requires a path or regex pattern' in capsys.readouterr().out


def test_remove_with_yes_deletes_match(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'remove', 'nlohmann', '--yes') == 0
    out = capsys.readouterr().out
    assert 'Removed 1 resource(s)' in out
    assert not os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc'))
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def'))


def test_remove_declined_keeps_resource(monkeypatch, capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: False)
    assert run(tmp_path, 'remove', 'json') == 0
    out = capsys.readouterr().out
    assert 'Aborted' in out
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_dry_run_keeps_resource(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'remove', 'json', '--dry-run') == 0
    out = capsys.readouterr().out
    assert 'Dry run' in out
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_no_match(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)
    assert run(tmp_path, 'remove', 'nonexistent', '--yes') == 0
    assert 'No matching resources.' in capsys.readouterr().out


def test_purge_removes_everything(capsys, tmp_path):
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'a@h+1',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)
    seed_resource(str(tmp_path), cache_configuration.TOOLS_SUBDIR, 'cppfront',
                  kind=resource_manifest.ResourceKind.TOOL,
                  source={'name': 'cppfront', 'version': 'v0.8.1'})

    assert run(tmp_path, 'purge', '--yes') == 0
    assert 'Removed 2 resource(s)' in capsys.readouterr().out
    assert run(tmp_path, 'list') == 0
    assert 'No cached resources found.' in capsys.readouterr().out


def test_unidentified_lists_and_removes_legacy_flat_entry(monkeypatch, capsys, tmp_path):
    # Legacy flat resource stored directly at the cache root (pre-subdir layout).
    seed_resource(str(tmp_path), '', 'mylogger@fsys.home+-')
    # A well-formed resource that must be left alone.
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'unidentified') == 0
    out = capsys.readouterr().out
    assert 'mylogger@fsys.home+-' in out
    assert 'json@h+abc' not in out

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: True)
    assert run(tmp_path, 'unidentified', '--remove') == 0
    assert not os.path.exists(os.path.join(str(tmp_path), 'mylogger@fsys.home+-'))
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_list_reports_a_legacy_kind_as_unidentified(capsys, tmp_path):
    # A manifest left by an earlier Golem version naming a kind this one does not
    # have. Its name is not one the listing may report, therefore the resource is
    # unidentified and its kind unknown.
    seed_resource(str(tmp_path), '', 'a30a9ffd',
                  kind='recipes-repository',
                  source=make_source(locator='https://github.com/golemcpp/recipes.git',
                                     reference='main'))

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out
    assert 'recipes-repository' not in out
    assert 'unknown  a30a9ffd  unidentified' in out


def test_unidentified_lists_and_removes_a_legacy_kind(monkeypatch, capsys, tmp_path):
    seed_resource(str(tmp_path), '', 'a30a9ffd', kind='recipes-repository')
    seed_resource(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=resource_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'unidentified') == 0
    out = capsys.readouterr().out
    assert 'a30a9ffd' in out
    assert 'json@h+abc' not in out

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: True)
    assert run(tmp_path, 'unidentified', '--remove') == 0
    assert not os.path.exists(os.path.join(str(tmp_path), 'a30a9ffd'))
    assert os.path.exists(os.path.join(str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_purge_removes_legacy_flat_entry(capsys, tmp_path):
    seed_resource(str(tmp_path), '', 'mylogger@fsys.home+-')

    assert run(tmp_path, 'purge', '--yes') == 0
    assert 'Removed 1 resource(s)' in capsys.readouterr().out
    assert not os.path.exists(os.path.join(str(tmp_path), 'mylogger@fsys.home+-'))
