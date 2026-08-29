from golemcpp.golem import command_config
from golemcpp.golem import config_store


def _isolate_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


def _project_dir(tmp_path):
    project_dir = tmp_path / "demo-project"
    project_dir.mkdir()
    return str(project_dir)


def test_handle_config_command_prints_help(capsys, tmp_path):
    result = command_config.handle_config_command(
        project_dir=_project_dir(tmp_path), args=["--help"]
    )

    assert result == 0
    stdout = capsys.readouterr().out
    assert "Usage: golem config <key>" in stdout
    assert "overlays.locations" in stdout
    assert "GOLEM_OVERLAYS_LOCATIONS" in stdout


def test_set_defaults_to_local_scope(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["overlays.locations", "/local/overrides"]
    )

    assert result == 0
    assert (
        config_store.get_scoped_value(
            "overlays.locations", config_store.LOCAL_SCOPE, project_dir
        )
        == "/local/overrides"
    )
    assert (
        config_store.get_scoped_value(
            "overlays.locations", config_store.GLOBAL_SCOPE, project_dir
        )
        is None
    )


def test_set_global_scope(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir,
        args=["--global", "overlays.locations", "/global/overrides"],
    )

    assert result == 0
    assert (
        config_store.get_scoped_value(
            "overlays.locations", config_store.GLOBAL_SCOPE, project_dir
        )
        == "/global/overrides"
    )


def test_set_refuses_a_value_the_setting_cannot_read(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["cache.minimization.length", "eight"]
    )

    assert result == 1
    assert "expects an integer" in capsys.readouterr().out
    assert (
        config_store.get_scoped_value(
            "cache.minimization.length", config_store.LOCAL_SCOPE, project_dir
        )
        is None
    )


def test_get_prints_resolved_value(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)
    config_store.set_value(
        "overlays.locations",
        "/global/overrides",
        config_store.GLOBAL_SCOPE,
        project_dir,
    )
    config_store.set_value(
        "overlays.locations", "/local/overrides", config_store.LOCAL_SCOPE, project_dir
    )

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["overlays.locations"]
    )

    assert result == 0
    assert capsys.readouterr().out.strip() == "/local/overrides"


def test_get_unset_key_returns_error(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["overlays.locations"]
    )

    assert result == 1
    assert capsys.readouterr().out.strip() == ""


def test_list_merges_scopes(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)
    config_store.set_value(
        "cache.directory", "/global/cache", config_store.GLOBAL_SCOPE, project_dir
    )
    config_store.set_value(
        "overlays.locations", "/local/overrides", config_store.LOCAL_SCOPE, project_dir
    )

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["--list"]
    )

    assert result == 0
    stdout = capsys.readouterr().out
    assert "cache.directory=/global/cache" in stdout
    assert "overlays.locations=/local/overrides" in stdout


def test_unset_removes_local_value(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)
    config_store.set_value(
        "overlays.locations", "/local/overrides", config_store.LOCAL_SCOPE, project_dir
    )

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["--unset", "overlays.locations"]
    )

    assert result == 0
    assert (
        config_store.get_scoped_value(
            "overlays.locations", config_store.LOCAL_SCOPE, project_dir
        )
        is None
    )


def test_unknown_key_is_rejected(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["bogus.key", "value"]
    )

    assert result == 1
    assert "unknown configuration key: bogus.key" in capsys.readouterr().out


def test_global_and_local_together_is_rejected(monkeypatch, capsys, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = _project_dir(tmp_path)

    result = command_config.handle_config_command(
        project_dir=project_dir, args=["--global", "--local", "overlays.locations"]
    )

    assert result == 1
    assert "--global and --local cannot be combined" in capsys.readouterr().out
