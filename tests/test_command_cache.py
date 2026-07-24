import os

from golemcpp.golem import cache
from golemcpp.golem import cache_manifest
from golemcpp.golem import command_cache
from golemcpp.golem import helpers


def seed_resource(cache_root, subdir, name, *, kind=None, identity=None, size=64):
    resource_root = os.path.join(cache_root, subdir, name)
    os.makedirs(resource_root, exist_ok=True)
    with open(os.path.join(resource_root, 'payload'), 'w', encoding='utf-8') as fp:
        fp.write('x' * size)
    if kind is not None:
        cache_manifest.write_manifest(
            resource_root=resource_root,
            kind=kind,
            cache_key=name,
            identity=identity or {})
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
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY,
                  identity={'name': 'json', 'resolved_version': 'v3.12.0'})

    result = run(tmp_path, 'list')
    assert result == 0
    out = capsys.readouterr().out
    assert '[dependency] json v3.12.0' in out


def test_list_empty(capsys, tmp_path):
    assert run(tmp_path, 'list') == 0
    assert 'No cached resources found.' in capsys.readouterr().out


def test_caches_lists_configured_location(capsys, tmp_path):
    assert run(tmp_path, 'caches') == 0
    out = capsys.readouterr().out
    assert 'Configured caches:' in out
    assert str(tmp_path) in out
    assert 'writable' in out


def test_size_totals(capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'a@h+1',
                  kind=cache_manifest.ResourceKind.DEPENDENCY, size=100)
    assert run(tmp_path, 'size') == 0
    out = capsys.readouterr().out
    assert 'Cache storage usage:' in out
    assert 'By kind:' in out
    assert 'dependency:' in out


def test_unidentified_lists_and_removes(monkeypatch, capsys, tmp_path):
    seed_resource(str(tmp_path), cache.RECIPES_SUBDIR, 'mystery@host+main')  # no manifest
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'unidentified') == 0
    out = capsys.readouterr().out
    assert 'mystery@host+main' in out
    assert 'json@h+abc' not in out

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: True)
    assert run(tmp_path, 'unidentified', '--remove') == 0
    assert not os.path.exists(os.path.join(str(tmp_path), cache.RECIPES_SUBDIR, 'mystery@host+main'))
    # Identified resource is untouched.
    assert os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_requires_pattern(capsys, tmp_path):
    assert run(tmp_path, 'remove') == 1
    assert 'remove requires a path or regex pattern' in capsys.readouterr().out


def test_remove_with_yes_deletes_match(capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'remove', 'nlohmann', '--yes') == 0
    out = capsys.readouterr().out
    assert 'Removed 1 resource(s)' in out
    assert not os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@com.github.nlohmann+abc'))
    assert os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'fmt@com.github.fmtlib+def'))


def test_remove_declined_keeps_resource(monkeypatch, capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: False)
    assert run(tmp_path, 'remove', 'json') == 0
    out = capsys.readouterr().out
    assert 'Aborted' in out
    assert os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_dry_run_keeps_resource(capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'remove', 'json', '--dry-run') == 0
    out = capsys.readouterr().out
    assert 'Dry run' in out
    assert os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_remove_no_match(capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)
    assert run(tmp_path, 'remove', 'nonexistent', '--yes') == 0
    assert 'No matching resources.' in capsys.readouterr().out


def test_purge_removes_everything(capsys, tmp_path):
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'a@h+1',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)
    seed_resource(str(tmp_path), cache.TOOLS_SUBDIR, 'cppfront',
                  kind=cache_manifest.ResourceKind.TOOL,
                  identity={'name': 'cppfront', 'version': 'v0.8.1'})

    assert run(tmp_path, 'purge', '--yes') == 0
    assert 'Removed 2 resource(s)' in capsys.readouterr().out
    assert run(tmp_path, 'list') == 0
    assert 'No cached resources found.' in capsys.readouterr().out


def test_unidentified_lists_and_removes_legacy_flat_entry(monkeypatch, capsys, tmp_path):
    # Legacy flat resource stored directly at the cache root (pre-subdir layout).
    seed_resource(str(tmp_path), '', 'mylogger@fsys.home+-')
    # A well-formed resource that must be left alone.
    seed_resource(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc',
                  kind=cache_manifest.ResourceKind.DEPENDENCY)

    assert run(tmp_path, 'unidentified') == 0
    out = capsys.readouterr().out
    assert 'mylogger@fsys.home+-' in out
    assert 'json@h+abc' not in out

    monkeypatch.setattr(helpers, 'confirm', lambda prompt, assume_yes=False: True)
    assert run(tmp_path, 'unidentified', '--remove') == 0
    assert not os.path.exists(os.path.join(str(tmp_path), 'mylogger@fsys.home+-'))
    assert os.path.exists(os.path.join(str(tmp_path), cache.DEPENDENCIES_SUBDIR, 'json@h+abc'))


def test_purge_removes_legacy_flat_entry(capsys, tmp_path):
    seed_resource(str(tmp_path), '', 'mylogger@fsys.home+-')

    assert run(tmp_path, 'purge', '--yes') == 0
    assert 'Removed 1 resource(s)' in capsys.readouterr().out
    assert not os.path.exists(os.path.join(str(tmp_path), 'mylogger@fsys.home+-'))
