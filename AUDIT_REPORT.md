# CinderACE Sessions — Read-Only Code Audit Report

**Project path:** `/home/seren/CinderACE - Sessions/`  
**Version audited:** `2.0.0` (`pyproject.toml`, `cinderace_sessions/__init__.py`)  
**Audit date:** 2026-06-18  
**Scope:** All target files listed by request, plus metadata/docs/tests.  
**Test suite:** `python -m pytest tests/ -v` → **46 passed, 0 failed**.

---

## Executive Summary

The codebase is a pywebview-based desktop app that discovers AI CLI sessions (Claude Code, Codex, Fire Forge, Gemini CLI, and custom directories), parses them, and exports/summarizes the contents. The architecture is reasonably modular (detector → parser → renderer → summarizer). Tests pass, but there are several critical/high-severity issues that should be addressed before public release or production use: hardcoded local paths and usernames, inconsistent path handling, a known pywebview RCE-equivalent debug mode enabled, unresolved stub code, a potential DB lock leak, and several instances of silent error swallowing that hide failure modes.

Findings are grouped by **severity** (Critical, High, Medium, Low). For each finding: file path, line numbers, issue, why it matters, and recommended fix.

---

## Critical Severity

### C1. `controller_app.py` runs pywebview with `debug=True`, which re-enables dev tools and weakens security boundaries

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 708–711
- **Code:**
  ```python
  webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
  api._window = window
  webview.start(debug=True)
  ```
- **Issue:** The code deliberately enables `debug=True` to receive `contextmenu` events (commented lines 705–707), then tries to suppress the DevTools popup with `OPEN_DEVTOOLS_IN_DEBUG = False`. pywebview's `debug=True` exposes the underlying browser engine's debug surface, and `OPEN_DEVTOOLS_IN_DEBUG` is an internal setting that may not reliably block all debug entrypoints across WebView2/Edge/QT/GTK backends. This is essentially accepting a known debug attack surface in a production app.
- **Why it matters:** A local attacker (or malicious webpage/script loaded into the app) can open DevTools or otherwise access the debug interface, leading to arbitrary code execution in the renderer context, leakage of config API keys from the JS side, or privilege escalation through the JS bridge.
- **Suggested fix:** Run `debug=False` in production. Implement the custom context menu without needing debug mode. If right-click suppression is backend-specific, conditionally enable debug only when an environment variable like `CINDERACE_SESSIONS_DEBUG=1` is set, and document that it is insecure.

### C2. Hardcoded system username `/home/seren` embedded in test fixtures and renderer examples

- **Files:**
  - `cinderace_sessions/renderer/markdown.py` line 23 docstring: `"e.g. \"Read: /home/seren/src/app.ts\""`
  - `tests/test_jsonl_parser.py` line 48: `_codex_user_line(text, cwd="/home/seren", ...)`
  - `tests/test_jsonl_parser.py` line 60: `_codex_meta_line(session_id="test-123", cwd="/home/seren/projects/myapp")`
  - `tests/test_jsonl_parser.py` line 144: `<cwd>/home/seren</cwd>`
  - `tests/test_jsonl_parser.py` line 156: `instructions for /home/dev`
- **Issue:** A real user home directory (`/home/seren`) and project path are embedded in source/tests. While `/home/dev` is a deliberate test fixture, `/home/seren` matches the actual project owner path and appears in both runtime docstrings and unit test data.
- **Why it matters:** Public repos should not leak the author's actual home directory. It exposes filesystem layout, username, and makes it harder for other developers/tests to run in a clean environment.
- **Suggested fix:** Replace `/home/seren` in tests with `~` expansion or generic placeholders (e.g. `/home/user`, `/tmp`). Remove the docstring example path or make it clearly fictional.

### C3. `summarizer/engine.py` and `model_catalog.py` send real API keys over HTTP without validating TLS or allowing proxy/custom certificate configuration

- **File:** `cinderace_sessions/summarizer/engine.py`, `cinderace_sessions/summarizer/model_catalog.py`
- **Lines:** OpenAI/Anthropic/OpenRouter request calls (e.g. 82–95, 155–168, 234–249, etc.); `urllib.request.urlopen` at `model_catalog.py:105`
- **Issue:** `requests` and `urllib` default to system certificate stores, but there is no `verify=True` pinning, no proxy support, no request/response logging redaction, and API keys are passed directly via headers. The `custom` provider allows any URL, including plain `http://`.
- **Why it matters:** Users on untrusted networks or with misconfigured TLS may leak keys. Custom endpoints entered as `http://` will transmit keys in cleartext. There is no audit trail if a key is accidentally logged.
- **Suggested fix:** Enforce HTTPS for non-local custom endpoints. Allow optional `verify`/`proxy` config. Redact keys in any logging. Document that `custom` over plain HTTP is unsafe.

---

## High Severity

### H1. `single_instance.py` may leave a database/file lock open or leak the lock handle on Windows

- **File:** `cinderace_sessions/single_instance.py`
- **Lines:** 20–67
- **Code:**
  ```python
  self.handle = self.path.open("a+")
  ...
  except OSError:
      self.close()
      return False
  ```
- **Issue:**
  1. `self.path.open("a+")` is a `Path.open()` call without `encoding` (high-severity consistency issue in itself).
  2. On Windows, if `msvcrt.locking` fails, `self.close()` is called. But on success path, `acquire()` does **not** store the `InstanceLock` object anywhere; in `controller_app.py:run_gui` the lock is assigned to a local variable `lock`. When `run_gui` exits, nothing explicitly releases the lock. The OS will release it when the process terminates, but a long-running GUI that restarts could hold stale locks.
  3. There is no `__del__` or `atexit` cleanup. The `finally` in `close()` calls `self.handle.close()` even if `self.acquired` is False, which can double-close the handle.
- **Why it matters:** Duplicate instances may launch if the lock is garbage-collected. On Windows, closing an unlocked handle that was never locked is harmless but still poor hygiene. More importantly, a crash in `run_gui()` before the lock is persisted could allow a second instance to start.
- **Suggested fix:** Add context-manager support (`__enter__`/`__exit__`) and use `atexit` to release the lock. Ensure the lock object is stored in a module/global singleton so it survives for the process lifetime.

### H2. `controller_app.py` exposes a method `ingest_session` that sends session content to an unauthenticated local HTTP endpoint with a hardcoded default

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 298–348
- **Code:**
  ```python
  ember_url = config.get("ember_memory_url", "http://localhost:2214").rstrip("/")
  ...
  resp = requests.post(
      f"{ember_url}/tools/memory_store",
      json={
          "content": content[:8000],
          ...
      },
      timeout=30,
  )
  return resp.status_code == 200
  ```
- **Issue:** The default `ember_memory_url` is plaintext HTTP on a fixed port with no authentication. The `content[:8000]` truncation silently drops the rest of the session, and errors are reduced to a boolean. The `get_ember_status` method checks for an `ember-memory` MCP server but the actual ingest uses HTTP anyway.
- **Why it matters:** A local attacker on the same machine can listen on port 2214 and receive full session summaries. There is no indication to the user that data is being transmitted over HTTP. Truncation can lose critical context.
- **Suggested fix:** Default to HTTPS where available, require explicit user confirmation before ingesting, surface ingest errors to the UI rather than returning a boolean, and allow disabling the feature entirely.

### H3. `_parse_session` silently swallows all parse exceptions and returns `None, None`

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 635–663
- **Code:**
  ```python
  except Exception as e:
      logger.error("Parse session failed for %s (%s): %s", filepath, source, e, exc_info=True)
      return None, None
  ```
- **Issue:** Any parser crash (including corrupted files, bad encoding, malformed Forge DB, or Gemini large-file edge cases) is logged but hidden from the user. `get_session_detail` and `export_session` then return `None` or a generic error string.
- **Why it matters:** Users cannot distinguish between "file not found", "permission denied", "unsupported format", "file corrupted", or "parser bug". This makes debugging and support very difficult.
- **Suggested fix:** Return structured error information (error type + message) to the frontend and display it in the UI. Consider a "report this session" debug path.

### H4. `CustomCLIDetector.find_sessions` and `registry.scan_all` silently ignore `OSError` and all per-file exceptions

- **File:** `cinderace_sessions/detector/registry.py`
- **Lines:** 91–112 (custom detector), 188–216 (`scan_all`)
- **Issue:** All OS-level errors (permission denied, broken symlinks, unreadable directories) are swallowed with `except OSError: pass` or `except Exception: logger.debug(..., exc_info=True)`. No visibility is given to the user.
- **Why it matters:** A user who points CinderACE at a directory with wrong permissions will see "No sessions found" instead of a useful permission-denied message.
- **Suggested fix:** Collect warnings during scanning and expose them via a `get_scan_warnings()` API for the CLI Status tab. Do not swallow `PermissionError` silently.

### H5. `config.py` `load_config` swallows corrupt `settings.json` and custom CLI files silently

- **File:** `cinderace_sessions/config.py`
- **Lines:** 48–54, 102–107
- **Code:**
  ```python
  except (json.JSONDecodeError, OSError):
      pass
  ```
- **Issue:** If `settings.json` is malformed or unreadable, the app silently falls back to defaults. The user may not realize their settings (including output directory or API keys) are being ignored.
- **Why it matters:** Silent data loss of user configuration. A typo in the JSON file means the app behaves like a fresh install with no warning.
- **Suggested fix:** Log a warning (visible in UI) when config files cannot be read. Offer to reset or repair the file. At minimum, expose the last error in the settings/status UI.

### H6. `forge.py` and `forge_parser.py` hold SQLite connections but use `except Exception: pass` patterns that can leave connections open

- **Files:** `cinderace_sessions/detector/forge.py` (lines 47–99), `cinderace_sessions/parser/forge_parser.py` (lines 103–123)
- **Issue:** Both modules open `sqlite3.connect`, then wrap the whole block in a broad `except Exception: ...` and return. `conn.close()` is called inside the happy path but not in exception paths. The detector returns `[]`; the parser returns `[]` after logging. There is no context-manager usage.
- **Why it matters:** Repeated failed queries (e.g. if `forge.db` is locked by another process) can exhaust SQLite connection handles or keep WAL files open.
- **Suggested fix:** Use context managers (`with sqlite3.connect(...) as conn:`) or `try/finally` blocks that guarantee `conn.close()`.

### H7. `ollama.py` hardcodes `http://localhost:11434` with no authentication or configurable endpoint in the UI

- **File:** `cinderace_sessions/summarizer/ollama.py`
- **Lines:** 16, 23–27, 33–44, 80, 95, 111, 124
- **Issue:** `OLLAMA_BASE_URL` is hardcoded. The `OllamaProvider` constructor accepts a `base_url`, but the UI/config does not expose it (the only summarizer URL setting is for custom endpoints). The Ollama API has no built-in authentication by default; this app sends prompts to it unauthenticated.
- **Why it matters:** Users running Ollama on a different host/port cannot use the feature. A malicious or misconfigured local service on 11434 can intercept prompts.
- **Suggested fix:** Add `ollama_url` to config and UI. Validate that the URL is local/loopback by default unless the user explicitly opts into a remote endpoint.

---

## Medium Severity

### M1. `controller_app.py` imports `webview` unconditionally at module import time, making CLI-only usage fail without pywebview installed

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 16
- **Code:** `import webview`
- **Issue:** `controller_app.py` is imported by `__main__.py` only when the `controller` command runs, but `webview` is a heavy dependency. More importantly, `controller_app.py` also defines `SessionsAPI` and many backend methods that are conceptually useful even outside the GUI. The unconditional import forces any consumer of this module to install pywebview.
- **Why it matters:** Consumers who only want to use `SessionsAPI` programmatically must install a GUI dependency. It also complicates headless testing.
- **Suggested fix:** Move the `import webview` inside `run_gui()` and `browse_directory()` where it is actually used.

### M2. `controller_app.py` has several functions that duplicate source-detection logic (`_validate_filepath` + source lookup loops)

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 122–133, 141–146, 195–199, 304–308, 473–477
- **Issue:** The same pattern (`for s in self._sessions_cache: if s.get("filepath") == filepath: source = ...`) is repeated in `get_session_detail`, `export_session`, `ingest_session`, and `summarize_session`. `_validate_filepath` only validates the path; callers then re-iterate to find the source.
- **Why it matters:** Duplication increases maintenance cost and risk of inconsistency. If validation rules change, multiple call sites need updating.
- **Suggested fix:** Create a single helper `_get_session_record(filepath)` that returns the cached dict or `None`. Use it everywhere.

### M3. `controller_app.py` and `__main__.py` mix `os.path.join` and `pathlib.Path`; path handling is inconsistent

- **Files:** `cinderace_sessions/controller_app.py` (lines 40, 218–220, 234, 241, 248, 255, 262, etc.), `cinderace_sessions/__main__.py` (lines 12, 32–34, 47)
- **Issue:** The code switches between `os.path.expanduser("~")`, `Path.home()`, and `Path(__file__).parent / "controller_assets"`. Some places use `os.path.join(...)` with `expanduser`, others use `Path` objects. The `output_directory` string is then passed to `os.makedirs` and `os.path.join` for output files.
- **Why it matters:** Inconsistent path handling can cause subtle bugs on Windows (slash direction, drive letters, spaces in usernames). `output_directory` from the UI is not normalized or validated.
- **Suggested fix:** Standardize on `pathlib.Path` everywhere. Add a helper `_normalize_output_dir(path_str)` that expands user, resolves relative paths, and validates that it is a writable directory.

### M4. `controller_app.py` `export_session` returns `f"Error: {str(e)}"` as a string from an API that otherwise returns a path string or `None`

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 271–273
- **Code:**
  ```python
  except Exception as e:
      logger.error("Export failed for %s: %s", filepath, e, exc_info=True)
      return f"Error: {str(e)}"
  ```
- **Issue:** The JS caller checks `result && !result.startsWith('Error:')`. This is fragile: a legitimate output path could theoretically start with `Error:` on a misconfigured system, and the frontend can accidentally treat a successful path as an error.
- **Why it matters:** Ambiguous return types make API contracts hard to trust. Error conditions should be distinguishable from success.
- **Suggested fix:** Return a structured dict `{success: bool, path?: str, error?: str}` from the backend, and update the JS to consume it.

### M5. `__main__.py` `launch_app_detached` closes the launch log handle in `finally` immediately after `Popen`, possibly before the child reads environment/stdout setup

- **File:** `cinderace_sessions/__main__.py`
- **Lines:** 44–65
- **Code:**
  ```python
  log_handle = _open_launch_log("controller_launch.log")
  ...
  try:
      return subprocess.Popen(command, **popen_kwargs)
  finally:
      log_handle.close()
  ```
- **Issue:** Closing the file handle immediately after `Popen` is generally safe on POSIX because the child has inherited a duplicate FD, but it is still risky if the handle is the only reference. More importantly, `launch_app_detached` returns the `Popen` object, but `main()` calls it and ignores the return value, so callers cannot check whether the child started.
- **Why it matters:** A failed launch is invisible. The log handle is owned by the child only because of inheritance, but this pattern is fragile across platforms.
- **Suggested fix:** Verify the child process started (e.g. check `proc.pid`) and surface launch errors. Consider using `subprocess.Popen` with `close_fds=False` explicitly, and only close the parent's copy after confirming the child is alive.

### M6. `config.py` env-var override map only covers a subset of settings

- **File:** `cinderace_sessions/config.py`
- **Lines:** 57–65
- **Issue:** The `env_map` converts `CINDERACE_SESSIONS_*` variables to config keys, but only for: output dir, export format, HTML theme, include thinking/tools, and role labels. It does **not** support env overrides for `summarizer_provider`, `summarizer_api_key`, `summarizer_model`, `ember_memory_url`, `default_ember_collection`, or `output_directory` via env.
- **Why it matters:** Documentation/behavior mismatch. Users might reasonably expect all settings to be overrideable via env vars.
- **Suggested fix:** Either document the limited env-var support or add a generic loop over all `DEFAULTS` keys that converts `CINDERACE_SESSIONS_<UPPER_KEY>` to each config key. Be careful to redact the API key in logs.

### M7. `jsonl_parser.py` `parse_jsonl_transcript` skips malformed JSON lines silently

- **File:** `cinderace_sessions/parser/jsonl_parser.py`
- **Lines:** 42–45
- **Code:**
  ```python
  try:
      record = json.loads(line)
  except json.JSONDecodeError:
      continue
  ```
- **Issue:** Malformed lines are dropped without counting or reporting. This is acceptable for robustness but means a corrupted file can produce a partial session without any warning.
- **Why it matters:** Data integrity is silently compromised. Export stats will not match the original file.
- **Suggested fix:** Add an optional `strict` mode or at least log/return the number of skipped lines so the UI can warn the user.

### M8. `gemini_parser.py` `_parse_jsonl_large` reads the entire large file line-by-line but still accumulates all message entries in memory

- **File:** `cinderace_sessions/parser/gemini_parser.py`
- **Lines:** 328–366
- **Issue:** The function is intended to avoid loading the full file into memory, but it appends every message to a local `messages: list[dict]` and then calls `_parse_chat_messages(messages)`, which builds a second `turns` list. For a very large session, memory use is still O(n).
- **Why it matters:** The 8MB guard is bypassed for files that are JSONL, but a JSONL session with hundreds of thousands of messages can still spike memory.
- **Suggested fix:** Stream directly into `Turn` objects or use generators. If streaming is not feasible, document the memory bound.

### M9. `model_catalog.py` `_read_json` does not set a default timeout for `urllib.request.urlopen`

- **File:** `cinderace_sessions/summarizer/model_catalog.py`
- **Lines:** 101–106
- **Code:**
  ```python
  def _read_json(url: str, headers: dict | None = None,
               timeout: int = 15) -> dict:
      req = urllib.request.Request(url, headers=headers or {})
      with urllib.request.urlopen(req, timeout=timeout) as resp:
          return json.loads(resp.read().decode())
  ```
- **Issue:** Actually a default timeout is provided (15s). However, callers `fetch_*_models` invoke `_read_json` without passing a timeout, relying on the default. The issue is that there is no handling of large response bodies; `resp.read()` loads the entire model list into memory.
- **Why it matters:** OpenRouter can return a multi-megabyte model list. Loading it all at once can cause UI freezes or memory spikes.
- **Suggested fix:** Cap read size or stream the response. Add a progress indicator in the UI rather than blocking.

### M10. `html.py` `escape_html` escapes `/` even though the generated HTML is not inside a `<script>` or `<style>` context that requires it

- **File:** `cinderace_sessions/renderer/html.py`
- **Lines:** 23–30
- **Code:**
  ```python
  def escape_html(text: str) -> str:
      return (text.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;")
                  .replace("/", "&#x2F;"))
  ```
- **Issue:** Escaping `/` is unnecessary for HTML body content and can corrupt URLs and paths in the exported document (e.g. `/home/user/file.py` becomes `&#x2F;home&#x2F;user&#x2F;file.py`).
- **Why it matters:** Exported HTML readability is degraded. Paths and URLs inside message text are mangled.
- **Suggested fix:** Remove the `/` replacement unless rendering inside a specific context where it is required (e.g. closing `</script>`). Use Python's `html.escape` with `quote=True`.

### M11. `markdown_parser.py` uses unusual `Path(filepath if '.' in filepath else '').stem` logic

- **File:** `cinderace_sessions/parser/markdown_parser.py`
- **Lines:** 127
- **Code:** `meta.session_id = Path(filepath if '.' in filepath else '').stem or "markdown-session"`
- **Issue:** If the filepath does not contain a `.`, `Path('').stem` is used, which yields `''`. The logic is convoluted and not obviously correct. The check `'/' in filepath` in `text_extract_meta` similarly misuses string checks instead of `Path` methods.
- **Why it matters:** Edge-case filenames (e.g. `README` without extension) produce confusing session IDs.
- **Suggested fix:** Use `Path(filepath).stem` directly; `Path` handles the empty/nameless case. Add tests for filenames without extensions.

### M12. `summarizer/ollama.py` imports `.engine` via relative import but `engine.py` uses `requests` while `ollama.py` re-implements `list_models`

- **File:** `cinderace_sessions/summarizer/ollama.py`
- **Lines:** 12, 92–101, 104–119
- **Issue:** The class has a `list_models` instance method and there is a standalone `list_models` function, plus `model_catalog.py` calls the standalone function. The relative import `from .engine import ...` works, but the duplication is confusing.
- **Why it matters:** Maintenance risk; changes to model listing logic must be made in two places.
- **Suggested fix:** Have `OllamaProvider.list_models` delegate to the standalone `list_models` function. Remove duplication.

### M13. `controller_assets/ui.js` caches model lists keyed by a base64 snippet of the API key

- **File:** `cinderace_sessions/controller_assets/ui.js`
- **Lines:** 700–706
- **Code:**
  ```javascript
  const cacheKey = provider + ':' + (apiKey ? btoa(apiKey).slice(0, 8) : 'nokey');
  if (modelCache[cacheKey]) { ... }
  ```
- **Issue:** A partial base64 of an API key is still derived from the key and stored in memory. While not a severe leak, it is unnecessary and could appear in heap dumps or debugging snapshots.
- **Why it matters:** API key material should not be transformed into cache keys, even partially.
- **Suggested fix:** Cache by provider only, or use a one-way hash with a random salt if per-key caching is required. Document that caching is per-provider.

### M14. `controller_assets/ui.js` `escapeHtml` uses `&#39;` for single quotes but the backend uses `&#x27;`

- **File:** `cinderace_sessions/controller_assets/ui.js`
- **Lines:** 1037–1046
- **Issue:** Slight inconsistency between frontend and backend escaping. Not a bug in practice, but a sign of duplicated logic that could diverge.
- **Why it matters:** Minor, but duplicated escaping logic should be centralized or use a shared utility.
- **Suggested fix:** Use a shared escape function or rely on DOM `textContent` rather than manual escaping where possible.

### M15. `controller_assets/ui.js` relies on `document.execCommand` for cut/copy/paste in the custom context menu

- **File:** `cinderace_sessions/controller_assets/ui.js`
- **Lines:** 1096
- **Code:** `document.execCommand(cmd);`
- **Issue:** `document.execCommand` is deprecated and may not work reliably in all pywebview backends. The fallback clipboard copy already catches errors but gives a misleading "Copy not supported" message.
- **Why it matters:** Native context-menu functionality may break in future browser/WebView versions.
- **Suggested fix:** Use the modern Clipboard API with a fallback. Ensure the pywebview bridge exposes a native copy method if the web APIs are unavailable.

---

## Low Severity

### L1. Unused imports

- **`tests/test_jsonl_parser.py` line 4:** `import os` — never used.
- **`tests/test_jsonl_parser.py` line 5:** `import tempfile` — never used (fixture uses `tmp_path`).
- **`tests/test_gemini_parser.py` line 4:** `import os` — never used.
- **`tests/test_gemini_parser.py` line 5:** `import tempfile` — never used.
- **`cinderace_sessions/__main__.py` line 7:** `from datetime import datetime` — used only inside `_open_launch_log`.
- **`cinderace_sessions/controller_app.py` line 14:** `from typing import Any` — used only in type hints; can be kept, but `dict`/`list` builtins are used in most places.
- **`cinderace_sessions/detector/codex.py` line 11:** `import os` — used for `os.environ`; okay.
- **`cinderace_sessions/parser/jsonl_parser.py` line 12:** `import os` — **unused**.
- **`cinderace_sessions/parser/markdown_parser.py` line 11:** `from datetime import datetime` — used.
- **`cinderace_sessions/renderer/json_export.py` line 6:** `from datetime import datetime` — used.
- **`cinderace_sessions/renderer/jsonl_export.py` line 9:** `from datetime import datetime` — used.
- **Suggested fix:** Run `ruff check --select F401` and remove unused imports.

### L2. Dead / stub code

- **File:** `controller/tray.py` — entire file is a Phase 7 stub that just prints a message.
- **File:** `controller/__main__.py` — imports the stub and calls `tray_main()`.
- **File:** `cinderace_sessions/__main__.py` lines 101–103: `install-desktop`, `uninstall-desktop`, `desktop-status` commands print "not yet implemented".
- **Why it matters:** Stubs are fine during development but should be tracked in an issue/TODO before release. They are not mentioned in the README/CHANGELOG.
- **Suggested fix:** Remove stubs if not shipping soon, or clearly document them as placeholders.

### L3. Commented-out code / old patterns

- **File:** `cinderace_sessions/controller_assets/ui.css` lines 34–35: empty comment block `/* CLI badge colors (used in .cli-badge classes below) */` with no actual variables.
- **File:** `cinderace_sessions/controller_assets/ui.js` lines 288–290: `startAutoRefresh` is defined but the auto-refresh interval re-renders the entire list every 30 seconds; this is acceptable but not documented.
- **Suggested fix:** Remove empty CSS comment or add actual badge CSS variables. Document the 30s auto-refresh behavior.

### L4. Debug logging in production

- **File:** `cinderace_sessions/__main__.py` lines 16–27 — `logging.basicConfig` always logs to `~/.cinderace-sessions/cinderace-sessions.log` and stderr at `INFO` level.
- **Issue:** This is appropriate for a desktop app, but there is no way to disable or tune it. Sensitive content (session previews, paths, API key presence) may be logged.
- **Suggested fix:** Add a `--verbose` / `--quiet` flag. Ensure API keys are never logged even partially.

### L5. `pyproject.toml` declares `pywebview[qt]` for Linux but does not handle headless environments

- **File:** `pyproject.toml` lines 16–17
- **Issue:** `pywebview[qt]` pulls in PyQt6 on Linux, which can fail in headless/WSL/container environments. The app has no headless fallback.
- **Suggested fix:** Document headless limitations. Provide a CLI-only mode that does not import pywebview.

### L6. Tests do not cover renderers, controller API, detector scanning, or summarizer engine

- **Files:** `tests/test_gemini_parser.py`, `tests/test_jsonl_parser.py`, `tests/test_model_catalog.py`
- **Issue:** 46 tests cover only three modules. The renderer, detector, controller app, config, single instance, summarizer engine, and UI assets are untested.
- **Why it matters:** Critical paths (export HTML/JSON/ZIP, custom CLI scanning, config save/load, session detail API) have no automated regression protection.
- **Suggested fix:** Add tests for at least:
  - `renderer/markdown.py`, `renderer/html.py`, `renderer/json_export.py`, `renderer/zip_export.py`
  - `config.py` with temporary config dir
  - `detector/registry.py` with temporary fake CLI directories
  - `controller_app.py` `_session_info_to_dict` and `_parse_session` with sample files

### L7. `README.md` and `FORGE.md` disagree on architecture/features

- **README.md** line 41 says Fire Forge default location is `~/.forge/`.
- **FORGE.md** architecture diagram does not list `forge.py` / `forge_parser.py` (they exist and are implemented), and the Sources table in README is out of date compared to the actual detector (`~/.local/share/forge/forge.db`).
- **README.md** line 104 lists only 3 commands, while `__main__.py` exposes 5+ commands including `setup` and stub desktop commands.
- **Suggested fix:** Update README Sources table to `~/.local/share/forge/forge.db`. Add `forge` entries to the FORGE.md architecture list. Document all commands consistently.

### L8. `CHANGELOG.md` version history does not match current version

- **File:** `CHANGELOG.md`
- **Issue:** The latest entry is `0.4.0 — 2026-03-20`. The package now reports `2.0.0` in `__init__.py` and `pyproject.toml`. There is no changelog entry for the v2 desktop rewrite, summarizer, ember-memory bridge, or Fire Forge support.
- **Why it matters:** Users and contributors cannot understand what changed between 0.4.0 and 2.0.0.
- **Suggested fix:** Add a `## 2.0.0` section summarizing the desktop app migration, new detectors/parsers, summarizer, and ember-memory integration.

### L9. `.gitignore` does not cover all generated/test artifacts

- **File:** `.gitignore`
- **Missing entries:** `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `.tox/`, `*.egg-info/` (actually present), `venv/`, `.venv/`, `__pycache__/` (present). It also references VS Code extension artifacts (`node_modules/`, `out/`, `*.vsix`) that no longer apply to this Python-only v2.
- **Suggested fix:** Add Python-specific cache/venv entries and remove obsolete VS Code build entries (or keep them if they are intentional for historical reasons).

### L10. `cinderace_sessions/__main__.py` and `controller/__main__.py` duplicate command routing intent

- **Files:** `cinderace_sessions/__main__.py`, `controller/__main__.py`
- **Issue:** `python -m controller` is a separate entry point for the stub tray. The `cinderace_sessions.__main__` module already handles `tray`. Two entry points increase confusion.
- **Suggested fix:** Deprecate `python -m controller` and route everything through `cinderace_sessions.__main__`.

### L11. `controller_assets/__init__.py` is empty

- **File:** `cinderace_sessions/controller_assets/__init__.py`
- **Issue:** The file is empty. It is not harmful, but it signals the directory is treated as a package. Because `package-data` in `pyproject.toml` explicitly lists the asset files, the `__init__.py` is unnecessary.
- **Suggested fix:** Remove empty `__init__.py` if not needed, or keep for clarity.

### L12. `cinderace_sessions/summarizer/engine.py` and `ollama.py` use `logger.exception` inside `except Exception` blocks, which logs full stack traces including potentially sensitive prompts

- **Files:** `cinderace_sessions/summarizer/engine.py` lines 116, 194, 270; `ollama.py` line 73
- **Issue:** `logger.exception` includes the exception message and traceback. If the exception message contains the prompt content (e.g. a long string interpolation in a third-party library), it may be written to disk.
- **Why it matters:** Session content could leak to the log file.
- **Suggested fix:** Replace `logger.exception(...)` with `logger.error("...: %s", type(e).__name__)` or log only sanitized error details. Do not log the full exception text for LLM-related errors.

### L13. Hardcoded model IDs and API URLs throughout `model_catalog.py` and `engine.py`

- **Files:** `cinderace_sessions/summarizer/model_catalog.py`, `cinderace_sessions/summarizer/engine.py`
- **Issue:** Provider base URLs, default models, and preferred model lists are hardcoded. This is acceptable for a small app but makes updates difficult when providers rename or deprecate models (e.g. `claude-sonnet-4-20250514` is a dated snapshot ID).
- **Suggested fix:** Move provider metadata to a JSON/YAML config file loaded at runtime, and fetch defaults from the provider's model list when possible.

### L14. `cinderace_sessions/controller_app.py` `_session_info_to_dict` returns `entrypoint` as raw string instead of `.value`

- **File:** `cinderace_sessions/controller_app.py`
- **Lines:** 665–679
- **Code:**
  ```python
  return {
      ...
      "entrypoint": s.entrypoint,
      ...
  }
  ```
- **Issue:** `SessionInfo.entrypoint` is typed as `str` in `base.py` (line 121), but detectors assign enum `.value` strings. The function is consistent with the dataclass type, but the JSON serializability is only guaranteed by convention.
- **Suggested fix:** No functional bug, but consider making `entrypoint` a `SessionEntrypoint` enum in `SessionInfo` and serializing `.value` explicitly.

### L15. `gemini_parser.py` uses `uuid4()` for every `logs.json` turn with `sessionId`

- **File:** `cinderace_sessions/parser/gemini_parser.py`
- **Lines:** 172
- **Code:** `turn_uuid = entry.get("sessionId", str(uuid4()))`
- **Issue:** The UUID is generated per turn only if `sessionId` is missing. This means different turns from the same `logs.json` file will share the same `sessionId` value as their UUID, which may be intentional (session-level identifier) but is semantically odd.
- **Suggested fix:** Clarify whether `uuid` on a `Turn` is meant to be message-level or session-level. If message-level, generate a UUID per message. If session-level, rename the field to avoid confusion.

### L16. `jsonl_parser.py` imports `os` but never uses it

- **File:** `cinderace_sessions/parser/jsonl_parser.py`
- **Line:** 12
- **Suggested fix:** Remove `import os`.

---

## Summary Table

| Severity | Count | Key Themes |
|----------|-------|------------|
| Critical | 3 | Debug mode security, leaked usernames/paths, API key transport safety |
| High | 7 | Resource leaks, silent error swallowing, hardcoded/insecure endpoints, inconsistent path handling |
| Medium | 15 | Duplicate logic, mixed path libs, ambiguous API return types, memory/streaming issues, inconsistent escaping |
| Low | 16 | Unused imports, stub code, test gaps, documentation drift, logging hygiene |
| **Total** | **41** | |

---

## Test Results

```text
============================= test session starts ==============================
platform linux -- Python 3.12.12, pytest-8.3.5, pluggy-1.6.0 -- /home/seren/miniconda3/bin/python
cachedir: .pytest_cache
rootdir: /home/seren/CinderACE - Sessions
configfile: pyproject.toml
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.3.0
collected 46 items

... (all 46 tests passed) ...

============================== 46 passed in 0.06s ==============================
```

**Coverage gaps identified:** No tests for HTML/JSON/JSONL/ZIP renderers, controller API, detector scanning, config persistence, single-instance locking, summarizer engine, or UI assets.

---

## Recommendations Priority

1. **Before any public release:** Address C1 (debug mode), C2 (username leakage), C3 (API key/TLS), H1 (lock leak), H2 (HTTP ingest), H6 (SQLite connection leaks).
2. **Before beta:** Address H3/H4/H5 (silent failures), H7 (Ollama hardcoded URL), M1/M4 (API return types), M3 (pathlib standardization), M10 (HTML slash escaping).
3. **Before stable:** Fill test gaps (L6), update CHANGELOG/README/FORGE (L7/L8), clean up stubs/unused imports (L2/L1), and add env-var/config documentation (M6).

---

*Report generated by read-only audit. No files were modified.*
