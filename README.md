# Codex Usage for Cinnamon

A native Cinnamon panel applet for Linux Mint 22.3 / Cinnamon 6.6. Python's standard library collects local statistics; Cinnamon only renders small JSON results. No network requests, credential access, dependencies to install, or GNOME Shell APIs.

## Install

From this checkout (commands work from fish too):

```sh
./install.sh
```

This creates a development symlink from `~/.local/share/cinnamon/applets/codex-usage@pila` to this checkout's `src` directory. Keep the checkout in place. The installer is idempotent and refuses to overwrite any other installation. No sudo is needed.

Right-click a Cinnamon panel → **Applets** → find **Codex Usage** → select it and press **+**. Right-click the applet → **Configure** to choose **Panel display** → **Rate limits** (default) or **Daily tokens**, change refresh interval (default 45 seconds), or snapshot freshness (default 5 minutes). Switching panel display applies immediately without running the collector again; the popup always shows both limits and token statistics. Source changes are immediately available through the symlink, but loaded JavaScript requires removing/re-adding the applet or restarting Cinnamon. On X11: Alt+F2, `r`, Enter; on Wayland log out and back in.

To reinstall, run `./install.sh` again. To uninstall, first remove the applet from the panel, then run `./uninstall.sh`. Only this checkout's symlink is removed; cache and preferences remain.

## Data sources and semantics

Inspected local JSONL files use a `timestamp`, optional `ordinal`, `type`, `payload` envelope and contain:

- `token_usage_record`: per-response `usage`, cumulative thread/turn usage, response/thread identifiers. Unique response IDs deduplicate repeated events, copied sessions and inherited response history.
- `event_msg` / `token_count`: cumulative `info.total_token_usage`, last usage, and observed `rate_limits`. Both record types share a cumulative baseline; snapshots are differenced rather than summed, avoiding duplicates and supporting format transitions.
- `turn_context`: last observed model and reasoning effort.
- `session_meta`: session identity, used internally only as a hash.

Both `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/**/*.jsonl` are scanned when present. The latter was absent on the inspected machine. Codex configuration and authentication are not needed at runtime and are not read by the collector.

**Total = input + output.** Cached input is a subset of input; reasoning output is a subset of output. They must not be added to total again. Cache share is cached input / input. Sessions means distinct threads with token activity during the selected period, including agent threads, not the number of JSONL files or CLI invocations.

Daily, weekly and monthly totals use the computer's local calendar; weeks start Monday. Usage is attributed to the timestamp of the reported response/snapshot, not the start of a session. The latest observed model/effort is not necessarily the model of another concurrently active session.

### Account limits

Observed snapshots include `used_percent`, `window_minutes`, and `resets_at`: 300-minute primary and 10,080-minute secondary windows on this machine. The applet reports **percentage USED**, not remaining. These are account snapshots, not limits calculated from local token totals.

The default panel always shows limits: `Codex 5h 73% · W 41%`. Outdated, expired, or cached-after-refresh-failure values remain visible with an asterisk per window, for example `Codex 5h 73%* · W 41%*`; the tooltip explains the marker. Unavailable windows show `—`. There is no automatic fallback to daily tokens. Select **Daily tokens** in the applet settings for `Codex 1.84M today`; a failed refresh marks cached tokens with `*` instead. The popup retains old limits explicitly marked **stale**, including their observation time. Passing a reset never fabricates a new 0% value. Model-specific windows or unexpected durations are not presented as the standard account windows.

The installed CLI exposes an app-server account-rate-limit protocol but no direct offline `/status` command. This applet deliberately does not start an authenticated app-server, contact OpenAI, or wake the CLI to refresh account data. Thus limits may be unavailable or stale until Codex writes a new snapshot, and usage on other devices is not included in local token statistics.

## Performance and privacy

The first run reads existing JSONL files. Later runs stat the session tree, reopen only changed files, and seek to cached byte offsets. A private SQLite database under `${XDG_CACHE_HOME:-~/.cache}/codex-usage-applet/` stores only hashed identifiers, offsets, token counters, timestamps and allowlisted model/limit metadata. The cache directory is mode 700 and the database 600. File paths, prompts, responses, code and credentials are never included in the cache or output.

Parsing runs in an asynchronous child process outside Cinnamon's UI thread. Unchanged history is not reparsed. Directory/stat work is proportional to file count; aggregate database queries are proportional to usage events in the current month. Source files are opened read-only, and no files under `~/.codex` are changed or removed.

Incomplete trailing lines are deferred; malformed and unexpected records are skipped. Removed history stays in the statistical cache; cache deletion forces a rebuild from currently available files. A replaced/truncated file is replayed with event-ID deduplication. Snapshot-only legacy forks lack response IDs, so inherited snapshots can be ambiguous. Missing archived history cannot be reconstructed. This is a local estimate, not a billing ledger.

## Debug and test

```sh
./scripts/codex-usage
python3 -m unittest discover -s tests -v
node --check src/applet.js
node tests/test_applet.js
```

The standalone command prints statistical JSON only. `bytes_read` should be zero on a second run without session changes. For isolated tests without touching the default cache:

```sh
./scripts/codex-usage --cache-dir /tmp/codex-usage-check
```

`--codex-home` supports synthetic fixtures. A cache is bound to one source directory; use a separate cache per source. Python 3 is required at runtime; Node is only used for developer syntax/mock tests. Synthetic tests never require actual conversations and never modify Codex files. Development validation also compared the collector against unique-response usage from actual local files, with exact totals; exercised the async subprocess under installed CJS; and checked installer idempotence and refusal to overwrite unrelated directories. Full visual validation requires adding the applet to the panel.

If Cinnamon reports an error: open **Looking Glass** using Alt+F2 → `lg` → **Log**, or inspect the current user journal with `journalctl --user -b`. Confirm the development symlink points to this checkout, `python3` runs, and the collector command succeeds. Remove/re-add the applet after JavaScript changes. Do not post your Codex session files or authentication data in bug reports; the collector intentionally emits only a generic error if cache access fails.

## Layout

- `src/applet.js`, `stylesheet.css`: native Cinnamon UI and async lifecycle.
- `src/metadata.json`, `settings-schema.json`: Cinnamon installation/settings.
- `src/collector.py`: incremental, read-only Python collector.
- `scripts/codex-usage`: standalone collector entry point.
- `install.sh`, `uninstall.sh`: non-destructive symlink management.
- `tests/`: synthetic collector and mock UI tests.
