# XP and Runtime Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make XP persistence, diagnostics, profile statistics, weekly recap delivery, shutdown backup, and event formatting behave consistently without changing the existing level formula.

**Architecture:** Keep the existing `DatabaseHandler` as the shared persistence boundary and use its write lock to make each XP operation atomic. Add additive SQLite migrations for chat-event totals and weekly recap delivery state, then update the cogs and runtime status to consume those operations. Keep badge, role, and notification actions downstream from committed XP.

**Tech Stack:** Python, discord.py application commands and task loops, aiosqlite, SQLite WAL.

**Spec:** `docs/superpowers/specs/2026-09-20-xp-and-runtime-reliability-design.md`

## Global Constraints

- `utils/math_utils.py`, its XP-to-level formula, and log multiplier 3 must remain unchanged.
- Add only backward-compatible SQLite migrations; preserve existing XP, level, voice minutes, filters, badge, and title records.
- Keep XP and weekly aggregate writes atomic under `DatabaseHandler._write_lock`.
- The minimum voice participant count remains based on humans who are not self-deaf, before role filters.
- Zero XP rate is valid; negative XP rates and invalid minimum-member thresholds are rejected.
- Do not modify `database/schema.db*` or `logs/jiromi.jsonl` as part of implementation.
- No tests are added or run in this session; verify changes by reviewing the complete diff and relevant call paths.

## Review Focus

- A first-time voice-only user has no `users` row before their first eligible heartbeat.
- A profile read and first XP write happen concurrently for the same new user.
- The configured XP rate is zero, negative, or saved before a guild configuration row exists.
- XP commits successfully, then a weekly-stat, badge, reward, or announcement operation fails.
- A weekly recap send fails, times out after Discord accepts it, or the process exits while holding a pending claim.

---

### Task 1: Add schema migrations and transactional database primitives

**Files:**
- Modify: `utils/db_handler.py`

**Interfaces:**
- Add `_ensure_user_tx(user_id: int, guild_id: int) -> None`; caller must already hold `_write_lock`.
- Add `_upsert_weekly_stats_tx(guild_id: int, user_id: int, xp_add: int, voice_mins_add: int, chat_xp_add: int) -> None`; caller must already hold `_write_lock`.
- Add migration v5 for `users.total_chat_events INTEGER NOT NULL DEFAULT 0`.
- Add migration v6 for `weekly_recap_deliveries(guild_id, week_key, status, claimed_at, posted_at, attempts, last_error)` with primary key `(guild_id, week_key)`.

- [ ] **Step 1: Add idempotent migration v5.** Inspect `PRAGMA table_info(users)` and only issue `ALTER TABLE` when `total_chat_events` is absent. Register version 5 in `MIGRATIONS`.
- [ ] **Step 2: Add migration v6 and preserve completed recaps.** Create the delivery table if missing. Copy each nonempty `weekly_config.last_posted_week_key` into the new table with `status='posted'`, using `INSERT OR IGNORE`; register version 6.
- [ ] **Step 3: Add transaction-only helpers.** Implement `_ensure_user_tx` with `INSERT OR IGNORE` and `_upsert_weekly_stats_tx` with the existing weekly upsert SQL, without calling public `execute` from inside the write lock.
- [ ] **Step 4: Review migration and lock ordering.** Confirm every migration is registered in ascending order, existing v2–v4 behavior is unchanged, transaction helpers never reacquire `_write_lock`, and new columns have defaults for existing users.

### Task 2: Make voice and chat XP operations atomic

**Files:**
- Modify: `utils/db_handler.py`
- Modify: `cogs/leveling.py`

**Interfaces:**
- Preserve `add_voice_time(user_id, guild_id, minutes, xp_per_min) -> {old_level, new_level}` and ensure it creates the row before update.
- Preserve `add_chat_xp(user_id, guild_id, xp_amount)` return values and add one `total_chat_events` increment per accepted chat event.
- Add optional `chat_xp_add` to `add_chat_xp` or a dedicated argument so `weekly_chat_xp` records the actual awarded amount in the same transaction.

- [ ] **Step 1: Make `add_voice_time` one transaction.** Under `_write_lock`, ensure the row, read its current XP/level, update XP and `total_voice_mins`, calculate the new level by calling the existing `calculate_level` unchanged, update the level, upsert weekly voice/XP totals, then commit once. On any exception, rollback and re-raise.

```python
async with self._write_lock:
    await self._conn.execute("BEGIN IMMEDIATE")
    try:
        await self._ensure_user_tx(user_id, guild_id)
        # Read current row, apply XP/minutes, recalculate level, and upsert weekly totals.
        await self._conn.commit()
    except Exception:
        await self._conn.rollback()
        raise
```

- [ ] **Step 2: Make chat XP and chat-event count atomic.** Ensure the row, increment XP and `total_chat_events`, set `last_chat_ts`, recalculate level with the unchanged helper, upsert weekly XP/chat totals, and commit under one lock/transaction.
- [ ] **Step 3: Remove duplicate weekly writes from the cog.** Remove the separate `update_weekly_stats` calls after `add_voice_time` and `add_chat_xp`; those aggregates are now part of each committed XP operation.
- [ ] **Step 4: Separate committed XP metrics from secondary failures.** Increment the committed voice counter immediately after `add_voice_time` returns. Keep streaks, badges, intros, roles, and announcements after that point; log their failures without reclassifying the committed XP as failed.
- [ ] **Step 5: Review first-time and concurrent-user flows.** Trace first voice heartbeat, first chat message, simultaneous `/profile` access, and later downstream exceptions. Confirm no path can perform `UPDATE users` before `_ensure_user_tx`.

### Task 3: Validate XP configuration and make owner grants atomic

**Files:**
- Modify: `cogs/admin_config.py`
- Modify: `cogs/setup_wizard.py`
- Modify: `utils/db_handler.py`
- Modify: `cogs/owner_recovery.py`

**Interfaces:**
- `update_config(guild_id, announce_id, voice_xp, chat_xp)` rejects negative rates and upserts a guild row.
- `update_min_members_voice(guild_id, value)` accepts only positive integers and upserts a guild row.
- `update_user_xp_direct(user_id, guild_id, xp_value, mode)` performs `add` and `set` while holding one write lock and returns `(old_level, new_level, new_xp)`.

- [ ] **Step 1: Validate command arguments.** Set `/xp setup` rate parameter minimums to zero and maximums to a safe Discord integer limit. Reject owner grant amounts below zero as well as above `MAX_XP_ACTION`.
- [ ] **Step 2: Validate at the database boundary.** Reject negative rates in `update_config`; reject `min_members_voice < 1`; call `INSERT OR IGNORE` for the guild config before applying updates. Keep zero rate valid.
- [ ] **Step 3: Make direct grant atomic.** Under `_write_lock`, ensure the user row, read old XP/level, compute add or set value, clamp the result to zero, recalculate the level using the unchanged helper, update XP/level, and commit once.
- [ ] **Step 4: Review missing-row and boundary cases.** Confirm setup succeeds on a guild with no config row, zero rate remains storable, negative rates/grants fail before writing, and simultaneous auto-XP cannot be overwritten by a grant.

### Task 4: Surface database read failures instead of returning fake empty data

**Files:**
- Modify: `utils/db_handler.py`
- Modify: `main.py`
- Modify: cogs that call `fetch_one` or `fetch_all` where a database exception needs a user-facing response or a loop-level error record.

**Interfaces:**
- `DatabaseHandler` receives an optional logger at construction.
- `fetch_one`/`fetch_all` keep returning `None`/`[]` for successful empty reads, but log structured `DB_READ_FAIL` and re-raise operational errors.
- `execute` logs structured `DB_WRITE_FAIL` and re-raises operational errors.

- [ ] **Step 1: Pass the bot logger into the database.** Change `init_db` to accept the bot logger and construct `DatabaseHandler(logger=...)`; update the sole startup call in `main.py`.
- [ ] **Step 2: Log and propagate read/write errors.** Add structured DB failure events with operation names and parameterized SQL text, excluding bound values. Preserve original exception chaining with `raise`, not `raise e`.
- [ ] **Step 3: Review consumers of empty results.** Inspect call sites that use `None`/`[]` to mean “not configured”; ensure operational errors propagate to an existing command/loop handler instead of being interpreted as no filters, no users, or no config.
- [ ] **Step 4: Review fail-open behavior.** Confirm a filter read error cannot be silently treated as an empty filter list and that a successful empty query still behaves as before.

### Task 5: Add runtime health and bounded voice diagnostics

**Files:**
- Modify: `main.py`
- Modify: `cogs/leveling.py`
- Modify: `cogs/admin_config.py`
- Modify: `cogs/monitor.py`

**Interfaces:**
- Add `bot.voice_health` state with `last_heartbeat_at`, `committed_voice_events`, and counters for `below_min_members`, `self_deaf_or_bot`, `channel_filter`, `role_filter`, `muted_limit`, and `member_error`.
- Expose cog/loop state and last heartbeat through `/xp status`.

- [ ] **Step 1: Initialize health state.** Add a typed, bounded dictionary or small dataclass on `PresenceBot`; store UTC heartbeat time at the start of every completed voice loop pass.
- [ ] **Step 2: Count skip reasons.** Increment aggregate counters at the existing skip branches. Check channel filters before per-member role checks, retain the documented minimum-member policy, and avoid per-member success logs.
- [ ] **Step 3: Detect required cog load failure.** In `setup_hook`, retain `COG_FAIL` reporting; if `Leveling` failed or is absent after loading, raise a startup error so the process does not claim XP readiness. Keep other cog failures isolated.
- [ ] **Step 4: Expand XP status.** Show rates, member threshold, allow/exclude filters, leveling cog presence, heartbeat loop state, last heartbeat age, and aggregate interval counters. If the DB health read raises, report unhealthy rather than green.
- [ ] **Step 5: Review misleading-success scenarios.** Trace configured rates with a stopped loop, a failed leveling cog, an empty guild config, and a running loop whose users are all filtered. Each must have a distinct visible status or counter.

### Task 6: Correct profile chat count and reset wording

**Files:**
- Modify: `cogs/profile.py`
- Modify: `cogs/admin_config.py`
- Modify: `utils/db_handler.py` only if a profile query needs `total_chat_events` selected.

- [ ] **Step 1: Display stored chat events.** Read `total_chat_events` through `get_user_data` and display it in `/profile`; remove the `xp // 5` estimate. Leave `/rank` and level display unchanged.
- [ ] **Step 2: Clarify reset copy.** Update confirmation and success text for `/xp reset`, and the success response for `/xp reset_user`, to say XP and level reset while lifetime voice minutes and weekly history remain.
- [ ] **Step 3: Review profile and reset consistency.** Confirm the profile count is independent of voice XP and that reset text matches the existing SQL columns changed.

### Task 7: Make weekly recap delivery retryable

**Files:**
- Modify: `utils/db_handler.py`
- Modify: `cogs/weekly_stats.py`

**Interfaces:**
- `claim_weekly_recap(guild_id, week_key, now_ts, lease_seconds) -> bool` atomically claims missing/failed deliveries and stale pending claims, but never a posted or empty delivery.
- `finish_weekly_recap(guild_id, week_key, status, error=None) -> None` records `posted`, `empty`, or `failed`; posted status also updates legacy `weekly_config.last_posted_week_key`.

- [ ] **Step 1: Implement atomic lease claim.** Use one `INSERT ... ON CONFLICT DO UPDATE ... WHERE` statement so only one process claims a delivery unless a pending lease has expired.
- [ ] **Step 2: Mark empty recaps terminal.** If no prior-week stats exist, persist `empty` so the loop does not reprocess the same empty week every 30 minutes.
- [ ] **Step 3: Mark success only after send returns.** Send the recap, then persist `posted`. On send errors persist `failed` and the concise error, allowing a retry on the next interval.
- [ ] **Step 4: Preserve at-least-once caveat.** Document in code that a Discord-accepted send followed by process loss before `posted` can be delivered again after the lease expires.
- [ ] **Step 5: Review claim-state transitions.** Check missing, pending, stale pending, failed, empty, posted, and legacy `last_posted_week_key` cases for correct retry or suppression behavior.

### Task 8: Prevent auto-backup overlap and guarantee artifact cleanup

**Files:**
- Modify: `main.py`
- Modify: `cogs/owner_backup.py`

- [ ] **Step 1: Stop the scheduled loop before final backup.** During graceful shutdown, cancel the `OwnerBackup.auto_backup_task` and await its task completion before calling `perform_backup_logic`.
- [ ] **Step 2: Guarantee temporary-file cleanup.** Put temporary database and zip cleanup in `finally` paths for failed DB validation and failed Discord upload. Preserve zip files only where the user explicitly downloads them.
- [ ] **Step 3: Review shutdown ordering.** Trace normal SIGINT/SIGTERM cleanup and unexpected `connect()` return; confirm one final backup at most and no scheduled backup overlaps it.

### Task 9: Align event placeholders and help text

**Files:**
- Modify: `cogs/server_events.py`
- Modify: `cogs/help.py`

- [ ] **Step 1: Add `{count}` alias.** Add `count: guild.member_count` to `_format_text` data while retaining `member_count` and `boost_count`.
- [ ] **Step 2: Document supported placeholders.** Make event help text list `{member}`, `{username}`, `{server}`, `{member_count}`, `{boost_count}`, and `{count}` consistently for message and embed fields.
- [ ] **Step 3: Review unknown placeholders.** Confirm a typo does not crash the event listener and that valid `{count}` formats to the current guild member count.

### Task 10: Final static review and scope check

**Files:**
- Review all changed Python files and the plan/spec.
- Do not modify: `utils/math_utils.py`, `database/schema.db*`, `logs/jiromi.jsonl`.

- [ ] **Step 1: Review the complete diff.** Trace voice, chat, grant, reset, status, profile, weekly recap, and shutdown code paths against the accepted spec.
- [ ] **Step 2: Check the protected formula file.** Confirm `git diff -- utils/math_utils.py` is empty and the log multiplier remains unchanged.
- [ ] **Step 3: Check workspace artifacts.** Confirm no database or JSONL log file was edited by implementation.
- [ ] **Step 4: Report verification limits.** Summarize static checks performed and state clearly that no tests were added or run in this session.
