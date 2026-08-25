from support import ROOT


def test_windows_launcher_quotes_script_path_and_pythonpath():
    launcher = ROOT / 'golem.bat'
    content = launcher.read_text(encoding='utf-8')

    assert 'set "PYTHONPATH=%~dp0src;%~dp0waflib\\waf;%PYTHONPATH%"' in content
    assert 'python3 "%~dp0src\\golemcpp\\golem" %*' in content


def test_posix_launcher_quotes_script_path_and_arguments():
    launcher = ROOT / 'golem'
    content = launcher.read_text(encoding='utf-8')

    assert 'python3 "$SCRIPT_DIR/src/golemcpp/golem" "$@"' in content
