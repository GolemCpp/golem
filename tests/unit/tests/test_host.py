import sys

import pytest

import host
from host import has_windows_msvc_toolchain
from host import require_cxx_compiler


def test_has_windows_msvc_toolchain_accepts_vswhere_installation(monkeypatch, tmp_path):
    installer_root = tmp_path / 'Program Files (x86)'
    vswhere_path = (
        installer_root / 'Microsoft Visual Studio' / 'Installer' / 'vswhere.exe'
    )
    vswhere_path.parent.mkdir(parents=True)
    vswhere_path.write_text('', encoding='utf-8')

    monkeypatch.setenv('ProgramFiles(x86)', str(installer_root))
    monkeypatch.setattr(sys, 'platform', 'win32')
    # Patched on `host`, which is where the caller reads it. Patching it here
    # would leave the real one in place and let the machine decide the answer.
    monkeypatch.setattr(host, 'command_exists', lambda command: False)

    assert has_windows_msvc_toolchain() is True


def test_require_cxx_compiler_skips_on_windows_without_any_detected_toolchain(
    monkeypatch, tmp_path
):
    installer_root = tmp_path / 'Program Files (x86)'
    installer_root.mkdir()

    monkeypatch.setenv('ProgramFiles(x86)', str(installer_root))
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(host, 'command_exists', lambda command: False)

    with pytest.raises(pytest.skip.Exception, match=r'No C\+\+ compiler available'):
        require_cxx_compiler()
