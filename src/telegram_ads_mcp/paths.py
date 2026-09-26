from __future__ import annotations

import os
import stat
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
    """Create the session file if absent and force owner-only permissions.

    `auth_state.json` is credential-equivalent (it holds live session cookies),
    so the mode matters. Two details are deliberate:

    * The file is created with `O_CREAT | O_EXCL` and mode `0o600` in one step
      rather than `touch()` then `chmod()`, so there is no window in which it
      exists with looser permissions.
    * A pre-existing symlink is refused. Playwright writes through this path,
      so a symlink planted by another local user would redirect credential
      writes to a location of their choosing.

    Permissions are best-effort on filesystems without POSIX modes (Windows,
    some network mounts); callers should not treat this as a guarantee.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    if path.is_symlink():
        raise OSError(
            f"Refusing to use {path}: it is a symlink. Remove it and re-run "
            "`telegram-ads-auth` to create a real session file."
        )

    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # Already exists (possibly just created by Playwright): just tighten it.
        pass
    except OSError:
        # Unsupported FS: fall back to touch, then best-effort chmod below.
        path.touch()
    else:
        os.close(fd)

    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows / unsupported FS: best-effort only
        pass
