from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def resolve_auth_state_path(
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else Path(cwd)
    home = Path.home() if home is None else Path(home)

    override = env.get("TELEGRAM_ADS_AUTH_STATE")
    if override:
        return Path(override).expanduser()

    xdg = home / ".config" / "telegram-ads-mcp" / "auth_state.json"
    local = cwd / "auth_state.json"
    if xdg.exists():
        return xdg
    if local.exists():
        return local
    return xdg


def ensure_secure_file(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    try:
        path.chmod(0o600)
    except OSError:
        # Windows / unsupported FS: best-effort only
        pass
