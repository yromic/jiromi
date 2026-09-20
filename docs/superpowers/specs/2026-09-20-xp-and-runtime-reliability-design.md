# XP and Runtime Reliability Design

## Goal

Make voice and chat XP updates reliable, observable, and consistent across the database, commands, and profile views. Improve adjacent runtime reporting, weekly recap delivery, backup shutdown behavior, and event placeholders identified in the repository audit.

The existing XP level formula in `utils/math_utils.py`, including its log multiplier of 3, is explicitly out of scope and must remain byte-for-byte unchanged.

## Current failure points

- Voice XP updates an existing `users` row but does not create one first, so the first voice heartbeat for a new user can be lost.
- Voice XP and weekly statistics are written separately. Later failures can leave XP persisted while counters or weekly data say the operation failed.
- Admin XP rates accept negative integers, which can subtract XP. Config updates can silently affect zero rows when a guild config row does not exist.
- Direct XP grants use a read/compute/write sequence that can overwrite concurrent automatic XP.
- XP health status checks configuration and reward roles, but not whether the leveling cog and heartbeat are actually running.
- Voice eligibility skips are mostly silent. Database read failures are converted to empty results, hiding the difference between no data and a query failure.
- Profile estimates chat count from total XP even though total XP includes voice XP.
- XP reset copy promises more than the SQL changes: XP and level reset, while voice minutes and weekly history remain.
- Weekly recap marks the period claimed before delivery succeeds. Backup loops may overlap a final shutdown backup. Event formatting docs mention `{count}` although the formatter does not provide it.

## Design

### XP and database writes

Add a migration for a cumulative chat-event counter. Add a safe user-row ensure operation using `INSERT OR IGNORE`. Voice XP, voice minutes, level recalculation, weekly XP, and weekly voice minutes are updated in a single database write transaction while holding the existing write lock. Accepted chat XP events, XP, last-chat timestamp, and weekly fields are committed consistently in their corresponding operation.

Direct grant `add` mode uses an atomic SQL increment under the write lock; `set` remains an atomic replacement. Existing callers continue receiving old and new level values. Reuse the existing `calculate_level` call as-is; do not edit `utils/math_utils.py`.

Configuration writes ensure a guild row exists before applying values. Both command validation and database methods reject negative rates and invalid member thresholds; zero XP rate remains a valid way to disable that XP source.

### Eligibility and health reporting

Keep the existing participant policy: only human, non-self-deaf voice members enter the minimum-member count; channel and role filters are applied to XP eligibility. Make the status output list the min-member threshold, XP rates, and filter state, plus cog/loop state, database-read health, last heartbeat time, and aggregate skip counts. The minimum count remains based on active channel participants, including participants whose roles are later excluded, to avoid silently changing the established anti-farm rule.

Add bounded aggregate counters for skip reasons and XP commits. Do not emit one success log per member. Update the committed-XP counter immediately after the database transaction, before badges, role grants, streaks, or announcements. Treat those later actions as secondary work whose failure cannot make the XP commit appear unsuccessful.

Required leveling-cog load failure must be visible as unhealthy and prevent the bot from claiming XP service is ready. Other optional cog failures remain isolated and reported.

Database read helpers must no longer silently turn operational errors into valid empty filter/config results. Callers should distinguish query failure from an empty result, and failures should reach structured logging with query context that does not expose credentials.

### Configuration, reset, and profile

Use nonnegative slash-command bounds and repeat validation at the database boundary. The XP status command must identify whether the rate is disabled and whether the heartbeat is running; it must not label config-only health as full runtime health.

Keep reset behavior non-destructive beyond its current SQL scope: reset XP and level only. Update confirmation and result text to say explicitly that lifetime voice minutes and weekly history remain.

Add a cumulative `total_chat_events` column and increment it only for messages accepted by the existing chat XP eligibility, length, and cooldown checks. Display that stored count in the profile instead of estimating chat count from total XP.

### Logging and adjacent modules

Write JSONL before attempting console output. Handle console encoding errors without interrupting file logging. Continue to use structured event types and include heartbeat/cog lifecycle errors.

For weekly recap delivery, persist a retryable delivery state and only mark a recap posted after Discord accepts the send. Use a stale-claim timeout so a process crash during delivery does not permanently suppress retries. Delivery is at-least-once if Discord accepts a message but the process loses the response before recording success.

Cancel and await the auto-backup loop before starting the final shutdown backup. Keep temporary database and zip cleanup in guaranteed cleanup paths.

Support the documented `{count}` event placeholder as an alias for guild member count, and document the supported placeholders consistently.

## Compatibility and migration

Increment the database schema version and add `total_chat_events` with default zero for existing users. Migration must be idempotent. No changes are made to existing XP values, level values, voice-minute totals, filters, or badge/title data.

The weekly recap delivery-state table is additive and does not delete existing weekly configuration. Existing `last_posted_week_key` values are retained and imported as posted state where possible so upgrades do not resend already completed recaps.

## Acceptance criteria

- A first-time voice-only user receives XP and voice minutes on the first eligible heartbeat.
- Each eligible heartbeat changes lifetime and weekly voice totals consistently with its XP commit.
- Concurrent voice/chat XP and owner grants do not overwrite one another.
- Negative XP rates cannot be saved through commands or database methods; zero remains a supported disabled rate.
- A missing guild config row is created before setup values are written.
- XP status reports a stopped/missing leveling heartbeat as unhealthy even when rates are configured.
- Skip reasons and committed XP are visible as bounded aggregate diagnostics; secondary badge/announcement failures do not falsify commit metrics.
- Database read errors are not treated as empty filters/config.
- Profile chat count reflects accepted chat events and is independent of voice XP.
- Reset copy accurately describes retained voice minutes and weekly history.
- Failed weekly recap delivery can be retried after a bounded claim lease; successful delivery is not routinely duplicated.
- Shutdown does not run auto-backup and final backup concurrently.
- `{count}` event templates format to guild member count.
- `utils/math_utils.py` remains unchanged.

## Scope exclusions

- Do not change XP-to-level mathematics or the log multiplier in `utils/math_utils.py`.
- Do not redesign XP earning rates, chat eligibility thresholds, mute policy, or anti-farm participant policy.
- Do not modify existing database or log artifacts in the developer workspace.
