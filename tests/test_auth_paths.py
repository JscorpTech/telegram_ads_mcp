from pathlib import Path

import pytest

from telegram_ads_mcp.paths import ensure_secure_file, resolve_auth_state_path


def test_env_overrides_everything(tmp_path: Path):
    custom = tmp_path / "custom" / "auth_state.json"
    result = resolve_auth_state_path(
        env={"TELEGRAM_ADS_AUTH_STATE": str(custom)},
        cwd=tmp_path / "cwd",
        home=tmp_path / "home",
    )
    assert result == custom


def test_uses_xdg_config_when_present(tmp_path: Path):
    home = tmp_path / "home"
    config = home / ".config" / "telegram-ads-mcp" / "auth_state.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    result = resolve_auth_state_path(env={}, cwd=tmp_path / "cwd", home=home)
    assert result == config


def test_falls_back_to_cwd_file(tmp_path: Path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    local = cwd / "auth_state.json"
    local.write_text("{}")
    result = resolve_auth_state_path(env={}, cwd=cwd, home=tmp_path / "home")
    assert result == local


def test_default_is_xdg_path_even_if_missing(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = resolve_auth_state_path(env={}, cwd=cwd, home=home)
    assert result == home / ".config" / "telegram-ads-mcp" / "auth_state.json"


def test_ensure_secure_file_sets_mode(tmp_path: Path):
    path = tmp_path / "sec" / "auth_state.json"
    path.parent.mkdir()
    path.write_text("{}")
    ensure_secure_file(path)
    assert (path.stat().st_mode & 0o777) == 0o600


def test_ensure_secure_file_creates_with_restrictive_mode(tmp_path: Path):
    """Created 0600 up front, not touched loosely and chmod-ed afterwards."""
    path = tmp_path / "sec" / "auth_state.json"
    ensure_secure_file(path)
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_ensure_secure_file_creates_parent_directory(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "auth_state.json"
    ensure_secure_file(path)
    assert path.parent.is_dir()


def test_ensure_secure_file_refuses_a_symlink(tmp_path: Path):
    """A planted symlink would redirect credential writes to an attacker's path."""
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    target.chmod(0o644)
    link = tmp_path / "auth_state.json"
    link.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        ensure_secure_file(link)

    # The real file must be untouched: the chmod did not follow the link.
    assert (target.stat().st_mode & 0o777) == 0o644
