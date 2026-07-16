# Telegram Ads MCP OSS Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the working Playwright Telegram Ads MCP into a solid MIT-licensed GitHub v0.1 package with src-layout, safety annotations, docs, tests, and CI.

**Architecture:** Keep the existing FastMCP stdio server and Playwright client. Relocate code under `src/telegram_ads_mcp/`, centralize auth-state path resolution, annotate tools, document dual install (clone primary, git one-liner secondary), and cover behavior with offline unit tests plus GitHub Actions.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP), Playwright, hatchling, pytest, ruff, pyright (basic), GitHub Actions.

## Global Constraints

- Version: `0.1.0`
- Requires Python: `>=3.11`
- Runtime deps only: `mcp`, `playwright`
- License: MIT
- Docs language: English only
- Transport: stdio only (no remote HTTP)
- Full current tool surface must remain public
- Mutating/download tools default to `confirm=False` dry-run (structured preview, no exception)
- Never commit `auth_state.json` or secrets
- No PyPI / MCP Registry / Docker / audit log / rate limits in this plan
- Omit `server.json` until a later registry task
- Prefer clone + venv install for Playwright; also document `uvx`/`pip install git+...`
- Pyright mode: basic (not strict)

## File Map

| Path | Responsibility |
|------|----------------|
| `src/telegram_ads_mcp/__init__.py` | Package version export |
| `src/telegram_ads_mcp/__main__.py` | `python -m telegram_ads_mcp` entry |
| `src/telegram_ads_mcp/paths.py` | Auth-state path resolution + secure write helper |
| `src/telegram_ads_mcp/exceptions.py` | `AuthExpiredError` |
| `src/telegram_ads_mcp/parsing.py` | Number/ID parsing helpers |
| `src/telegram_ads_mcp/client.py` | Playwright `TelegramAdsClient` (moved from root) |
| `src/telegram_ads_mcp/auth_setup.py` | Interactive login → save storage state |
| `src/telegram_ads_mcp/mcp_server.py` | FastMCP tools + annotations |
| `tests/test_parsing.py` | Parsing unit tests |
| `tests/test_auth_paths.py` | Path resolution unit tests |
| `tests/test_dry_run.py` | Dry-run contract for mutating tools |
| `tests/test_tool_annotations.py` | Tool list + annotation checks |
| `pyproject.toml` | Package metadata, scripts, optional/dev deps, hatch src layout |
| `.gitignore` | Secrets, venv, caches |
| `LICENSE` | MIT |
| `README.md` | Install, config, tools, warnings |
| `SECURITY.md` | Session/spend threat model |
| `CONTRIBUTING.md` | Dev + PR rules |
| `.github/workflows/ci.yml` | Lint, typecheck, test, wheel |

Delete after move (root leftovers): `telegram_ads_client.py`, `mcp_server.py`, `auth_setup.py`, `exceptions.py`, `parsing.py` (once src copies exist and imports work).

---

### Task 1: Auth path resolver (TDD)

**Files:**
- Create: `src/telegram_ads_mcp/paths.py`
- Create: `tests/test_auth_paths.py`
- Create: `src/telegram_ads_mcp/__init__.py` (minimal, so imports work once package exists)

**Interfaces:**
- Produces:
  - `resolve_auth_state_path(env: Mapping[str, str] | None = None, cwd: Path | None = None, home: Path | None = None) -> Path`
  - `ensure_secure_file(path: Path) -> None` — create parent dirs; if file exists or after write, `chmod 0o600` when supported
- Consumes: stdlib only

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth_paths.py
from pathlib import Path
from telegram_ads_mcp.paths import resolve_auth_state_path, ensure_secure_file


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/artemmelnikov/vscode/telegram-ads-mcp && .venv/bin/python -m pytest tests/test_auth_paths.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_ads_mcp'` or import error for `paths`.

- [ ] **Step 3: Minimal package + implementation**

```python
# src/telegram_ads_mcp/__init__.py
__version__ = "0.1.0"
```

```python
# src/telegram_ads_mcp/paths.py
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
```

Also create a temporary `pyproject.toml` update so editable installs find the package (full packaging lands in Task 2). At minimum for this task:

```toml
[project]
name = "telegram-ads-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mcp>=1.0.0", "playwright>=1.40.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/telegram_ads_mcp"]
```

Then: `.venv/bin/pip install -e ".[dev]"` once extras exist; for now `.venv/bin/pip install -e .`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_auth_paths.py -v`

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/telegram_ads_mcp/__init__.py src/telegram_ads_mcp/paths.py tests/test_auth_paths.py pyproject.toml
git commit -m "$(cat <<'EOF'
Add auth state path resolver with secure file mode.

EOF
)"
```

---

### Task 2: Move code into src-layout and wire entrypoints

**Files:**
- Create: `src/telegram_ads_mcp/exceptions.py` (move)
- Create: `src/telegram_ads_mcp/parsing.py` (move)
- Create: `src/telegram_ads_mcp/client.py` (move from `telegram_ads_client.py`)
- Create: `src/telegram_ads_mcp/auth_setup.py` (move + use paths)
- Create: `src/telegram_ads_mcp/mcp_server.py` (move + fix imports)
- Create: `src/telegram_ads_mcp/__main__.py`
- Modify: `pyproject.toml`
- Delete: root `telegram_ads_client.py`, `mcp_server.py`, `auth_setup.py`, `exceptions.py`, `parsing.py`

**Interfaces:**
- Consumes: `resolve_auth_state_path`, `ensure_secure_file` from Task 1
- Produces:
  - `TelegramAdsClient` importable as `from telegram_ads_mcp.client import TelegramAdsClient`
  - CLI: `telegram-ads-mcp` and `python -m telegram_ads_mcp`
  - Auth CLI still runnable via `python -m telegram_ads_mcp.auth_setup`

- [ ] **Step 1: Write a failing import/entrypoint smoke test**

```python
# tests/test_package_entry.py
def test_package_exports_version():
    import telegram_ads_mcp
    assert telegram_ads_mcp.__version__ == "0.1.0"


def test_client_importable():
    from telegram_ads_mcp.client import TelegramAdsClient
    assert TelegramAdsClient is not None


def test_main_module_has_main():
    from telegram_ads_mcp import mcp_server
    assert callable(mcp_server.main)
```

- [ ] **Step 2: Run to verify failure for missing client module**

Run: `.venv/bin/python -m pytest tests/test_package_entry.py -v`

Expected: FAIL on `telegram_ads_mcp.client` until move completes.

- [ ] **Step 3: Move modules and fix imports**

1. Copy root files into `src/telegram_ads_mcp/` with renames:
   - `telegram_ads_client.py` → `client.py`
   - keep `mcp_server.py`, `auth_setup.py`, `exceptions.py`, `parsing.py`
2. In `client.py`, change:
   - `from exceptions import ...` → `from telegram_ads_mcp.exceptions import ...`
   - `from parsing import ...` → `from telegram_ads_mcp.parsing import ...`
   - Replace `DEFAULT_AUTH_STATE = Path(__file__).parent / "auth_state.json"` with:

```python
from telegram_ads_mcp.paths import resolve_auth_state_path

DEFAULT_AUTH_STATE = resolve_auth_state_path()
```

   - Wherever storage state is written after account select, call `ensure_secure_file(path)` after `storage_state(...)`.

3. In `mcp_server.py`:

```python
from telegram_ads_mcp.exceptions import AuthExpiredError
from telegram_ads_mcp.client import (
    DEFAULT_AUTH_STATE,
    AdStatus,
    StatsPeriod,
    TargetType,
    TelegramAdsClient,
)
```

   Use `resolve_auth_state_path()` when constructing the client if env can change after import; preferred:

```python
from telegram_ads_mcp.paths import resolve_auth_state_path

_client = TelegramAdsClient(storage_state=resolve_auth_state_path(), headless=True)
```

4. Rewrite `auth_setup.py` to resolve path, save, chmod:

```python
from telegram_ads_mcp.paths import ensure_secure_file, resolve_auth_state_path

def main() -> None:
    auth_path = resolve_auth_state_path()
    # ... launch headed browser, wait for Enter ...
    context.storage_state(path=str(auth_path))
    ensure_secure_file(auth_path)
    print(f"Session saved to {auth_path}")
```

5. `__main__.py`:

```python
from telegram_ads_mcp.mcp_server import main

if __name__ == "__main__":
    main()
```

6. Finalize `pyproject.toml`:

```toml
[project]
name = "telegram-ads-mcp"
version = "0.1.0"
description = "MCP server for Telegram Ads via Playwright"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = [
  "mcp>=1.0.0",
  "playwright>=1.40.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "pyright>=1.1"]

[project.scripts]
telegram-ads-mcp = "telegram_ads_mcp.mcp_server:main"
telegram-ads-auth = "telegram_ads_mcp.auth_setup:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/telegram_ads_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: hits real ads.telegram.org (disabled by default)"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pyright]
include = ["src"]
pythonVersion = "3.11"
typeCheckingMode = "basic"
```

7. Delete the old root modules listed above.
8. Reinstall: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 4: Run smoke tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_package_entry.py tests/test_auth_paths.py -v
.venv/bin/python -c "import telegram_ads_mcp.mcp_server as m; print(m.mcp.name)"
.venv/bin/telegram-ads-mcp --help >/dev/null || true
```

Expected: pytest PASS; mcp name prints `telegram-ads`. If CLI has no `--help`, verifying the script exists via `which telegram-ads-mcp` is enough.

- [ ] **Step 5: Commit**

```bash
git add -A src tests pyproject.toml
git add -u
git commit -m "$(cat <<'EOF'
Restructure package to src layout with installable entrypoints.

EOF
)"
```

---

### Task 3: Tool annotations + dry-run contract tests

**Files:**
- Modify: `src/telegram_ads_mcp/mcp_server.py`
- Create: `tests/test_dry_run.py`
- Create: `tests/test_tool_annotations.py`

**Interfaces:**
- Consumes: existing client methods with `confirm: bool = False`
- Produces: FastMCP tools annotated with `ToolAnnotations(...)`

- [ ] **Step 1: Write failing annotation + dry-run tests**

```python
# tests/test_tool_annotations.py
from mcp.types import ToolAnnotations
from telegram_ads_mcp.mcp_server import mcp


def _tools_by_name():
    # FastMCP exposes tools via tool manager
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def test_read_tools_marked_readonly():
    tools = _tools_by_name()
    for name in ("list_accounts", "list_ads", "get_ad_info", "get_account_budget"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True


def test_budget_tools_marked_destructive():
    tools = _tools_by_name()
    for name in ("increase_budget", "set_budget"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is True
        assert ann.openWorldHint is True


def test_non_budget_writes_not_destructive():
    tools = _tools_by_name()
    for name in ("set_cpm", "set_status", "update_ad", "create_ad", "get_ad_stats_csv"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is False
```

```python
# tests/test_dry_run.py
import asyncio
from telegram_ads_mcp.client import TelegramAdsClient


class DummyClient(TelegramAdsClient):
    def __init__(self):
        # Skip browser startup; only exercise dry-run branches
        self._storage_state = None  # type: ignore
        self._headless = True
        self._account_name = "Artem"
        self._p = None
        self.browser = None
        self.context = None
        self.page = None
        self._account_ready = False
        import asyncio
        self._lock = asyncio.Lock()


def test_set_cpm_dry_run_default():
    c = DummyClient()
    result = asyncio.get_event_loop().run_until_complete(c.set_cpm(3, 0.25))
    assert result["dry_run"] is True
    assert result["action"] == "set_cpm"
    assert result["cpm"] == 0.25


def test_increase_budget_dry_run_default():
    c = DummyClient()
    result = asyncio.get_event_loop().run_until_complete(c.increase_budget(3, 1.0))
    assert result["dry_run"] is True
    assert result["delta_ton"] == 1.0


def test_create_ad_dry_run_default():
    c = DummyClient()
    result = asyncio.get_event_loop().run_until_complete(
        c.create_ad(
            title="t",
            text="x",
            url="t.me/bot",
            cpm=0.2,
            initial_budget=1.0,
        )
    )
    assert result["dry_run"] is True
    assert result["action"] == "create_ad"


def test_get_ad_stats_csv_dry_run_default():
    c = DummyClient()
    result = asyncio.get_event_loop().run_until_complete(c.get_ad_stats_csv(3))
    assert isinstance(result, dict)
    assert result["dry_run"] is True
```

If `DummyClient.__init__` is awkward because `TelegramAdsClient.__init__` requires an existing auth file, prefer constructing via `__new__` in the test file:

```python
def make_client() -> TelegramAdsClient:
    c = TelegramAdsClient.__new__(TelegramAdsClient)
    # set only attributes needed by dry-run methods
    return c
```

Dry-run methods must not call `_ensure_started` before the `confirm` check (audit client code; move dry-run return before any browser I/O if needed).

- [ ] **Step 2: Run tests expecting annotation failures**

Run: `.venv/bin/python -m pytest tests/test_tool_annotations.py tests/test_dry_run.py -v`

Expected: annotation tests FAIL (`annotations is None`); dry-run may already PASS.

- [ ] **Step 3: Add annotations on every `@mcp.tool`**

Import and apply, example:

```python
from mcp.types import ToolAnnotations

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True, title="...")
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True, title="...")
SPEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True, title="...")

@mcp.tool(annotations=READ)
async def list_ads() -> list[dict]:
    """List all ads with full table columns. Read-only."""
    ...

@mcp.tool(annotations=SPEND)
async def increase_budget(ad_id: int, amount: float, confirm: bool = False) -> dict:
    """Add TON to ad budget (delta). Requires confirm=True to execute; default is dry-run."""
    ...
```

Apply to all tools per Design §2 table. Ensure every mutating docstring mentions `confirm=True`.

Audit client methods so dry-run returns before Playwright starts.

- [ ] **Step 4: Re-run tests**

Run: `.venv/bin/python -m pytest tests/test_tool_annotations.py tests/test_dry_run.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/telegram_ads_mcp/mcp_server.py src/telegram_ads_mcp/client.py tests/test_tool_annotations.py tests/test_dry_run.py
git commit -m "$(cat <<'EOF'
Annotate MCP tools and lock dry-run defaults with tests.

EOF
)"
```

---

### Task 4: Parsing tests + .gitignore hardening

**Files:**
- Create: `tests/test_parsing.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `parse_int_commas`, `parse_decimal`, `extract_ad_id` from `telegram_ads_mcp.parsing`

- [ ] **Step 1: Write failing/missing parsing tests**

```python
# tests/test_parsing.py
from telegram_ads_mcp.parsing import extract_ad_id, parse_decimal, parse_int_commas


def test_parse_int_commas():
    assert parse_int_commas("10,788") == 10788
    assert parse_int_commas("-") == 0


def test_parse_decimal_strips_currency():
    assert parse_decimal("💎0.20") == 0.2
    assert parse_decimal("–") == 0.0


def test_extract_ad_id():
    assert extract_ad_id("/account/ad/3/stats") == 3
    assert extract_ad_id("https://ads.telegram.org/account/ad/7") == 7
    assert extract_ad_id("/choose_account/x") is None
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_parsing.py -v`

Expected: PASS if parsing already correct; if any fail, fix `parsing.py` minimally.

- [ ] **Step 3: Harden `.gitignore`**

Ensure these entries exist:

```gitignore
auth_state.json
**/auth_state.json
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
dist/
build/
*.egg-info/
.env
.DS_Store
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_parsing.py .gitignore
git commit -m "$(cat <<'EOF'
Add parsing tests and harden gitignore for session secrets.

EOF
)"
```

---

### Task 5: Public docs (LICENSE, README, SECURITY, CONTRIBUTING)

**Files:**
- Create: `LICENSE`
- Create: `README.md`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: package name `telegram-ads-mcp`, scripts `telegram-ads-mcp` / `telegram-ads-auth`
- Produces: English docs matching Design §3

- [ ] **Step 1: Add MIT LICENSE**

Use standard MIT text with copyright `Copyright (c) 2026 Artem Melnikov` (or the GitHub owner name if different).

- [ ] **Step 2: Write README.md with these exact sections**

1. Title + one-paragraph description  
2. **Security warning** callout about `auth_state.json` and spend tools  
3. Requirements (Python 3.11+, Chromium via Playwright, Telegram Ads account)  
4. Quick start — **recommended clone path**:

```bash
git clone https://github.com/OWNER/telegram-ads-mcp.git
cd telegram-ads-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
telegram-ads-auth
```

5. Cursor `mcp.json` example using absolute venv python path and env vars:

```json
{
  "mcpServers": {
    "telegram-ads": {
      "command": "/ABS/PATH/telegram-ads-mcp/.venv/bin/telegram-ads-mcp",
      "env": {
        "TELEGRAM_ADS_ACCOUNT": "Artem",
        "TELEGRAM_ADS_AUTH_STATE": "/ABS/PATH/to/auth_state.json"
      }
    }
  }
}
```

6. Secondary one-liner (git install) note: still run `playwright install chromium` in an environment that can download browsers; Playwright + ephemeral `uvx` envs is fragile, so clone remains recommended.

```bash
pip install "git+https://github.com/OWNER/telegram-ads-mcp.git"
playwright install chromium
```

7. Tools table covering every tool, Read/Write, and whether `confirm` is required  
8. Config: `TELEGRAM_ADS_AUTH_STATE`, `TELEGRAM_ADS_ACCOUNT`  
9. Limitations (Fragment, schedule widgets, targeting immutable, no CI live tests)  
10. License MIT  

Replace `OWNER` with the actual GitHub user/org when publishing.

- [ ] **Step 3: Write SECURITY.md**

Must include: session secrecy, `0600`, revoke steps (delete auth file + Log Out on ads.telegram.org), warning that `confirm=True` can spend TON, annotations are hints not security.

- [ ] **Step 4: Write CONTRIBUTING.md**

Must include: `pip install -e ".[dev]"`, `playwright install chromium`, `pytest`, `ruff check .`, `pyright`, never commit auth state, PR checklist.

- [ ] **Step 5: Commit**

```bash
git add LICENSE README.md SECURITY.md CONTRIBUTING.md
git commit -m "$(cat <<'EOF'
Add MIT license and English OSS documentation.

EOF
)"
```

---

### Task 6: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `pip install -e ".[dev]"`, pytest/ruff/pyright entrypoints from earlier tasks

- [ ] **Step 1: Add workflow**

```yaml
name: CI
on:
  push:
    branches: [master, main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install
        run: |
          python -m pip install -U pip
          pip install -e ".[dev]"
      - name: Ruff
        run: ruff check src tests
      - name: Pyright
        run: pyright
      - name: Pytest
        run: pytest -v
      - name: Build wheel
        run: |
          pip install build
          python -m build
          pip install dist/*.whl
          python -c "import telegram_ads_mcp; print(telegram_ads_mcp.__version__)"
```

Do **not** install Playwright browsers in CI for v0.1 (offline tests only).

- [ ] **Step 2: Run local equivalent before commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/pyright
.venv/bin/pytest -v
.venv/bin/pip install build && .venv/bin/python -m build
```

Expected: all green. Fix any lint/type issues discovered.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
Add GitHub Actions CI for lint, types, tests, and wheel install.

EOF
)"
```

---

### Task 7: Release readiness check

**Files:**
- Modify: none unless fixes found
- Verify: whole repo

- [ ] **Step 1: Full local verification**

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check src tests
.venv/bin/pyright
.venv/bin/pytest -v
.venv/bin/python -c "from telegram_ads_mcp.mcp_server import mcp; print(sorted(t.name for t in mcp._tool_manager.list_tools()))"
test ! -f auth_state.json || git check-ignore -v auth_state.json
```

Expected:
- Tool list includes all 11 tools from the design (`list_accounts`, `list_ads`, `get_ad_info`, `get_account_budget`, `update_ad`, `set_cpm`, `set_status`, `increase_budget`, `set_budget`, `get_ad_stats_csv`, `create_ad`)
- Auth state ignored if present
- Tests green

- [ ] **Step 2: Optional tag (only after user confirms remote repo exists)**

```bash
git tag v0.1.0
# git push -u origin HEAD
# git push origin v0.1.0
```

Do not force-push. Do not push unless user asks.

- [ ] **Step 3: Final commit only if verification required code fixes**

Otherwise no commit.

---

## Spec Coverage Checklist

| Spec requirement | Task |
|------------------|------|
| src-layout package | Task 2 |
| `telegram-ads-mcp` / `-m` entrypoints | Task 2 |
| Auth path env → XDG → cwd | Task 1 |
| Secure `0600` auth file | Task 1, Task 2 auth_setup |
| Full tool surface | Task 3 (preserve) + Task 7 verify |
| Dry-run defaults | Task 3 |
| Tool annotations | Task 3 |
| MIT + English docs | Task 5 |
| Dual install docs | Task 5 |
| Parsing/auth/dry-run/annotation tests | Tasks 1, 3, 4 |
| CI matrix + wheel | Task 6 |
| No registry/Docker/PyPI | Global constraints / omitted |
| No live CI E2E | Task 6 note |

## Plan decisions for former open points

1. **Install one-liner:** Document `pip install git+...` as secondary; **clone + venv recommended** because Playwright browser downloads are unreliable in ephemeral `uvx` environments.
2. **`server.json`:** Omit in v0.1.
3. **Pyright:** `typeCheckingMode = "basic"`.
