import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import resource_manifest
from golemcpp.golem import command_cache
from golemcpp.golem import helpers


def seed_resource(cache_root, subdir, name, *, kind=None, source=None, size=64):
    resource_root = os.path.join(cache_root, subdir, name)
    os.makedirs(resource_root, exist_ok=True)
    with open(os.path.join(resource_root, 'payload'), 'w', encoding='utf-8') as fp:
        fp.write('x' * size)
    if kind is not None:
        resource_manifest.write_manifest(
            resource_root=resource_root,
            kind=kind,
            cache_key=name,
            source=source or {})
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
                  source={'type': 'git',
                            'locator': 'https://github.com/nlohmann/json.git',
                            'resolved': {'reference': 'v3.12.0',
                                         'revision': 'cafebabe'}})

    result = run(tmp_path, 'list')
    assert result == 0
    out = capsys.readouterr().out
    assert '[dependency] https://github.com/nlohmann/json.git v3.12.0' in out


def test_list_empty(capsys, tmp_path):
    assert run(tmp_path, 'list') == 0
    assert 'No cached resources found.' in capsys.readouterr().out


def test_list_shows_path_without_long(capsys, tmp_path):
    resource_root = seed_resource(
        str(tmp_path), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        source={'name': 'json', 'resolved_version': 'v3.12.0'})

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out

    # The path is shown without asking for --long.
    assert 'path: {}'.format(resource_root) in out
    # The resource is listed under a per-cache header (the cache location).
    assert '{}:'.format(str(tmp_path)) in out
    # The redundant inline "cache:" annotation is gone.
    assert 'cache: ' not in out


def test_list_separates_resources_per_cache(capsys, tmp_path, monkeypatch):
    primary = tmp_path / 'primary'
    secondary = tmp_path / 'secondary'

    primary_resource = seed_resource(
        str(primary), cache_configuration.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        source={'name': 'json', 'resolved_version': 'v3.12.0'})
    secondary_resource = seed_resource(
        str(secondary), cache_configuration.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
        kind=resource_manifest.ResourceKind.DEPENDENCY,
        source={'name': 'fmt', 'resolved_version': 'v10.0.0'})

    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', str(secondary))

    assert run(primary, 'list') == 0
    out = capsys.readouterr().out

    # Each cache is a separate group header, and each resource shows under its own
    # cache with its full path.
    assert '{}:'.format(str(primary)) in out
    assert '{}:'.format(str(secondary)) in out
    assert 'path: {}'.format(primary_resource) in out
    assert 'path: {}'.format(secondary_resource) in out


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
                  source={'type': 'git',
                          'locator': 'https://github.com/golemcpp/recipes.git',
                          'resolved': {'reference': 'main', 'revision': 'cafebabe'}})

    assert run(tmp_path, 'list') == 0
    out = capsys.readouterr().out
    assert 'recipes-repository' not in out
    assert '[unknown] a30a9ffd (unidentified)' in out


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
