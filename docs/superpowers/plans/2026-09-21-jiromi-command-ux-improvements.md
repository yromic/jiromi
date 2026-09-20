# Jiromi Command UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve every user-facing slash command and help flow in Jiromi so users can understand status, prevent mistakes, recover from failures, and use a smaller, consistent icon system.

**Architecture:** Keep the current slash-command groups and Discord components, while establishing shared response, copy, and icon rules. Update help content alongside command behavior, make multi-field configuration changes validate and save atomically, and give each status surface clear health and recovery guidance. Preserve the existing XP formula and gamification badge artwork.

**Tech Stack:** Python, discord.py application commands and UI views, SQLite through `DatabaseHandler`, Markdown documentation.

**Design basis:** The approved ten-heuristic audit and recommendations from the preceding conversation. This plan includes member, administrator, event, weekly recap, and bot-owner commands.

**Heuristic targets:** Visibility 5/5; real-world language 4/5; user control 5/5; consistency 5/5; error prevention 5/5; recognition 5/5; flexibility 4/5; aesthetic minimalism 4/5; error recovery 5/5; help 5/5. Treat these as review goals, not scores to claim without manual Discord QA.

## Global Constraints

- User-facing copy remains in clear Indonesian; retain English only for established Discord labels or terms that are explained in Indonesian.
- Use one shared visual and response pattern across slash commands, embeds, views, and errors.
- Reduce decorative icons throughout the bot. Preserve meaningful rank medals, earned badge/title artwork, and icons that convey a unique status.
- Do not change XP earning rules, level math, stored XP semantics, or the existing `utils/math_utils.py` formula as part of UX work.
- Do not change existing runtime database or JSONL log artifacts.
- Validate all inputs for a configuration operation before persisting any of its fields.
- Do not expose SQL, exception text, stack traces, or internal event names to ordinary users.
- Add or run automated tests only if separately requested; implementation verification in this plan is a static review and manual Discord QA checklist.

## Review Focus

- A database or Discord API failure after an interaction has been deferred must still produce one useful user response.
- An invalid event color, placeholder, or image URL must not leave part of the event configuration changed.
- A destructive command must show the exact target and data affected before execution.
- A reset, clear, or cancel action must state which settings or records remain unchanged.
- A user viewing help on mobile must be able to find the correct command and parameter names without knowing internal terminology.
- Removing decorative icons must not remove meaningful badge identity, ranking meaning, or status distinctions.

---

### Task 1: Define shared command copy, response, and icon rules

**Files:**
- Create: `docs/superpowers/specs/2026-09-21-jiromi-command-ux-guidelines.md`
- Create: `utils/interaction_responses.py`
- Modify: `utils/views.py`

**Interfaces:**
- Add `send_interaction_message(interaction, *, content=None, embed=None, ephemeral=True, view=None)` to send an initial response or followup according to `interaction.response.is_done()`.
- Add `send_interaction_error(interaction, message, *, ephemeral=True)` as the shared user-facing error path.
- These helpers must not display raw exception details. Callers log technical context through `bot.logger`.

- [ ] **Step 1: Record the copy and icon guide.** Define Indonesian terminology for XP, level, voice, cooldown, filter, recap, backup, and status. State that command names and option names use no decorative emoji; command descriptions use plain text; embed titles use at most one semantic icon when it improves scanning; body rows and bullets use no decorative icons. Keep medals and earned badge/title artwork because they carry product meaning. Use text labels such as `Aktif`, `Nonaktif`, `Perlu diperiksa`, and `Gagal` so color or icon is never the only status signal.
- [ ] **Step 2: Add the shared response helpers.** The helper checks `interaction.response.is_done()` and chooses `response.send_message` or `followup.send`. Preserve the requested ephemeral flag and support content, embed, and view arguments. It must not attempt a second initial response.
- [ ] **Step 3: Standardize view access and timeout feedback.** Keep the current executor-only interaction check. Route its denial through the shared helper. Use one concise timeout message and disable expired controls without replacing useful configuration or progress details.
- [ ] **Step 4: Review response timing.** Inspect deferred command and component callbacks before using the helper; ensure no path acknowledges an interaction twice or silently returns after an exception.
- [ ] **Step 5: Review the icon guide against all existing UI surfaces.** Confirm the guide distinguishes decorative icons from identity/status icons and does not remove rank medals, badge artwork, or useful status information.

### Task 2: Make `/help` the accurate command guide

**Files:**
- Modify: `cogs/help.py`
- Create: `utils/help_content.py` if the help content is split from the command/view implementation.

**Interfaces:**
- Keep `/help` and its `topik` option. Every documented command must use its actual registered slash path and option names.

- [ ] **Step 1: Build and review the command inventory.** Cover member commands: `/profile`, `/rank`, `/level`, `/leaderboard`, `/title list`, `/title select`, `/weekly_leaderboard`, and `/global leaderboard`. Cover server-admin commands: `/setup`, `/xp setup`, `/xp status`, `/xp announcement`, `/xp role ...`, `/xp channel ...`, `/xp filter reset`, `/xp reward ...`, `/xp reset`, `/xp reset_user`, `/xp refresh_cache`, `/xp grant_tenure`, `/event ...`, and `/weekly ...`. Mark `/owner ...`, `/recovery ...`, and `/guilds` as bot-owner tools rather than ordinary server-admin commands.
- [ ] **Step 2: Correct current help inaccuracies.** Describe `/profile` as the journey/badge view and `/rank` as rank position; state the actual leaderboard size (Top 50); document `/level` and title commands; document weekly recap administration; explain that `/setup` is the interactive path and `/xp setup` is the direct configuration path.
- [ ] **Step 3: Explain exact XP eligibility and reset behavior.** State the actual chat length and cooldown rules, voice participant threshold policy, self-deafen and mute behavior, role/channel filters, and which data XP resets retain. Avoid implying that a single status indicator proves every XP source works.
- [ ] **Step 4: Complete event help.** Document setup, toggle, message, embed, image, preview/test, show, clear, placeholders, valid image link expectations, and how to recover when an event cannot send. Include `{member}`, `{username}`, `{server}`, `{member_count}`, `{count}`, and `{boost_count}`.
- [ ] **Step 5: Reduce icons and improve scanning in help.** Remove decorative emoji prefixes from topic labels, headings, and every bullet. Keep only icons with semantic value and use short sections, exact examples, and concise Indonesian copy.
- [ ] **Step 6: Review every help example against command declarations.** Check command paths, option names, permission requirements, defaults, and displayed limits against the corresponding cog source.

### Task 3: Improve member profile, rank, title, and leaderboard UX

**Files:**
- Modify: `cogs/profile.py`

**Interfaces:**
- Preserve current slash paths and data meanings. Keep profile and rank as separate commands with distinct descriptions.

- [ ] **Step 1: Clarify command descriptions.** Describe `/profile` as a member journey, activity, and achievement view; describe `/rank` as server rank and nearby members; describe `/level` as current level and remaining XP. Use plain Indonesian and no decorative emoji in command descriptions.
- [ ] **Step 2: Make member targeting explicit.** Ensure optional member parameters say whether an admin/member can inspect another member and use the same option name (`member`) in `/rank`, `/profile`, and `/level` where the signatures allow it.
- [ ] **Step 3: Simplify profile presentation.** Use a predictable order: member identity, level/progress, voice/chat activity, badges, active title. Keep chat count visibly labeled as accepted XP chat events if that is the stored counter’s meaning. Remove decorative icons from field labels and prose while retaining earned badge art.
- [ ] **Step 4: Improve title selection feedback.** Show the current title before selection, keep the remove-title choice, and return a concise confirmation that names the selected or removed title.
- [ ] **Step 5: Improve leaderboard mobile scanning.** Keep rows short and consistent, retain rank medals, and make pagination controls say `Sebelumnya` and `Selanjutnya`. Explain page and total member counts in plain text.
- [ ] **Step 6: Review empty, self, other-member, and expired-view states.** Each should give a short explanation and the next useful action without decorative icon clutter.

### Task 4: Improve XP administration, setup, and destructive actions

**Files:**
- Modify: `cogs/admin_config.py`
- Modify: `cogs/setup_wizard.py`
- Modify: `cogs/owner_recovery.py`

**Interfaces:**
- Keep `/setup` as the beginner wizard and `/xp setup` as direct setup. Reuse one validated configuration write path where practical.
- Add a confirmation view for `/xp reset_user` that names the member and describes retained data before reset.

- [ ] **Step 1: Make setup modes distinct.** Update `/setup` and `/xp setup` descriptions to say who each is for and which fields it changes. Show preset XP values and notification behavior before selection. Include the minimum voice participant setting in the wizard introduction and final summary.
- [ ] **Step 2: Improve wizard control.** Keep start, back, cancel, restart, and apply controls. On apply failure retain the draft, explain that settings were not fully saved, and allow retry/cancel. Before apply, make the summary state channel, notification mode, rates, and participant threshold in plain language.
- [ ] **Step 3: Add reset-user confirmation.** Display the exact member, XP/level reset scope, retained voice minutes and weekly history, and whether reward roles are retained. Require explicit `Reset` or `Cancel` actions.
- [ ] **Step 4: Add reward level validation.** Constrain `/xp reward add` to positive levels and show the allowed range in the option description. Preserve existing role hierarchy and managed-role checks, with concise corrective guidance.
- [ ] **Step 5: Make `/xp status` scannable.** Separate chat status and voice status, configuration, filters, rewards, and next action. State the period for interval counters. Present text health labels in addition to color; do not report all XP as inactive when only voice is unhealthy.
- [ ] **Step 6: Improve owner grant confirmations and progress.** Confirm add versus set semantics, target, old/new XP where available, maximum amount, and the effect of setting a value lower than current XP. For mass grant, show progress and a final successful/failed count.
- [ ] **Step 7: Remove decorative icons in XP admin UI.** Keep only clear status marks where they materially help; remove emoji from routine labels, button names, descriptions, and repeated bullets.
- [ ] **Step 8: Review permissions and all rejection paths.** Confirm administrator and owner denial messages are ephemeral, concise, and safe after interaction acknowledgement.

### Task 5: Make event configuration safe, previewable, and reversible

**Files:**
- Modify: `cogs/server_events.py`
- Modify: `utils/db_handler.py` only if an atomic event-config update or clear operation is needed.
- Modify: `cogs/help.py` and `utils/help_content.py` from Task 2 for matching command help.

**Interfaces:**
- Add one atomic database operation for saving the selected event fields, for example `update_event_config(guild_id, event_type, values)`, if command updates currently require multiple writes.
- Add a clear/reset action that can clear selected event content without deleting unrelated event settings.

- [ ] **Step 1: Validate before writing.** Validate color format/range, placeholder names, field lengths, and image URL format before any database update. Return field-specific feedback and preserve the previous configuration on invalid input.
- [ ] **Step 2: Save multi-field event updates atomically.** Validate all supplied fields first, then persist the embed toggle, title, description, and color in one transaction. Do not partially update if any field is invalid.
- [ ] **Step 3: Add clear and restore controls.** Provide a command path to clear message text, embed content, or image URL, plus an explicit reset of one event configuration. Confirm before clearing the whole event; do not silently erase its channel or enabled state when clearing content.
- [ ] **Step 4: Add a private preview.** Preview the rendered output to the invoking administrator before public test delivery. Make `/event test` clearly state the target channel and send only after explicit confirmation, or keep it as a public test with an explicit warning and confirmation.
- [ ] **Step 5: Improve `/event show`.** Display enabled state, channel, message/embed mode, full relevant content, image, and preview. Distinguish missing configuration from missing channel or missing send/embed permissions.
- [ ] **Step 6: Make event feedback consistent.** Use shared response helpers. State whether a save succeeded, whether the event is enabled, and what action comes next. Reduce decorative event icons while retaining at most one useful status indicator.
- [ ] **Step 7: Review every event type and placeholder.** Cover welcome, leave, ban, and boost. Ensure an unknown placeholder is caught before save and the user sees how to fix it.

### Task 6: Improve weekly recap and backup controls

**Files:**
- Modify: `cogs/weekly_stats.py`
- Modify: `cogs/owner_backup.py`
- Modify: `cogs/owner_tools.py` if its owner-only command descriptions or denial feedback need the shared pattern.
- Modify: `cogs/help.py` and `utils/help_content.py` from Task 2.

- [ ] **Step 1: Clarify weekly command paths.** Describe `/weekly_leaderboard` as member/server activity for the current week; describe `/global leaderboard` as anonymous cross-server ranking. Keep setup controls under `/weekly` and make enable/disable wording explicit about whether configuration is retained.
- [ ] **Step 2: Improve `/weekly status`.** Show enabled state, destination channel, next recap timing, previous successful recap, current activity preview, and any retry/failure state with a human-readable recovery action.
- [ ] **Step 3: Confirm weekly delivery changes.** Before enabling, name the selected channel and schedule; before disabling, state that the channel configuration remains saved. Use consistent success and error replies.
- [ ] **Step 4: Improve backup status and actions.** Explain backup destination, next automatic run, last result, and manual backup cooldown. Confirm before overwriting backup settings; after an upload, state whether it was delivered and where.
- [ ] **Step 5: Make upload/backup failures recoverable.** Give owner-facing errors that distinguish missing destination, missing permissions, database validation failure, and upload failure without exposing raw exception details. Preserve temporary artifact cleanup behavior.
- [ ] **Step 6: Remove decorative icons from weekly and backup embeds.** Keep only semantic state marks and domain imagery that adds information.

### Task 7: Apply one reduced icon system and response pattern across the bot

**Files:**
- Modify: `cogs/admin_config.py`
- Modify: `cogs/help.py`
- Modify: `cogs/leveling.py`
- Modify: `cogs/monitor.py`
- Modify: `cogs/owner_backup.py`
- Modify: `cogs/owner_recovery.py`
- Modify: `cogs/owner_tools.py`
- Modify: `cogs/profile.py`
- Modify: `cogs/server_events.py`
- Modify: `cogs/setup_wizard.py`
- Modify: `cogs/weekly_stats.py`
- Modify: `utils/views.py`
- Modify: `utils/logger.py` only where user-facing console wording is shared with command UX; do not alter log event identifiers solely for visual cleanup.

- [ ] **Step 1: Inventory visible icon use.** Search command descriptions, embeds, messages, buttons, selects, timeout messages, and progress displays. Classify each icon as decorative, status, rank, or earned badge/title identity.
- [ ] **Step 2: Remove decorative icons.** Remove icons that repeat the same meaning as nearby text, prefix every bullet/field, or serve only as decoration. Remove decorative emoji from slash descriptions, button labels, and routine success messages.
- [ ] **Step 3: Preserve a small semantic set.** Keep text-first statuses (`Aktif`, `Nonaktif`, `Perlu diperiksa`, `Gagal`); where an icon remains, use one stable mapping for success, warning, failure, and in-progress. Keep rank medals and earned gamification art.
- [ ] **Step 4: Standardize embeds and buttons.** Use one field order and heading style per command category. Keep button labels verb-led and short, such as `Simpan`, `Kembali`, `Batal`, `Reset`, and `Lihat pratinjau`.
- [ ] **Step 5: Review mobile readability.** Check that long status and leaderboard content wraps cleanly, essential actions are visible without scanning emoji-heavy rows, and no embed field exceeds Discord limits.
- [ ] **Step 6: Compare the finished UI against the icon guide.** Search again for remaining decorative emoji and document each intentional exception in the guideline file.

### Task 8: Standardize command error recovery and interaction responses

**Files:**
- Modify: `cogs/admin_config.py`
- Modify: `cogs/owner_backup.py`
- Modify: `cogs/owner_recovery.py`
- Modify: `cogs/profile.py`
- Modify: `cogs/server_events.py`
- Modify: `cogs/setup_wizard.py`
- Modify: `cogs/weekly_stats.py`
- Modify: `utils/interaction_responses.py`

- [ ] **Step 1: Map interaction acknowledgement state.** For each command, identify whether it sends an initial response, defers, or edits a component message. Route errors through the shared helper so the code never attempts a second initial response.
- [ ] **Step 2: Map expected failures to plain-language guidance.** Handle permission denial, bot permission denial, invalid options, stale/deleted channels or roles, database failures, Discord API failures, and expired interactions. Keep raw exceptions only in structured logs.
- [ ] **Step 3: Distinguish failure from empty data.** For profile, leaderboard, event, weekly status, reward list, and filter views, explain when there is genuinely no data versus when the data could not be read.
- [ ] **Step 4: Report partial operation results.** For mass grants, multi-field setup, and event operations, state what succeeded, what failed, and whether a retry is safe. Avoid a green success response when a secondary action such as role assignment failed.
- [ ] **Step 5: Review every command error handler.** Replace bare `print`-only user command failures with structured bot logging plus a safe user message. Keep access-control responses ephemeral.
- [ ] **Step 6: Review logs and user text separately.** Ensure logs retain actionable event/context while ordinary users never see exception text, SQL, internal event codes, or stack traces.

### Task 9: Final command catalog, heuristic review, and manual QA

**Files:**
- Review all modified command cogs and `utils/interaction_responses.py`.
- Update: `docs/superpowers/specs/2026-09-21-jiromi-command-ux-guidelines.md`
- Update: `cogs/help.py` or `utils/help_content.py` for any discovered mismatch.

- [ ] **Step 1: Compare registered commands with help.** Verify every user, administrator, event, weekly, and owner command has an accurate name, option list, permission note, and purpose in the appropriate help topic.
- [ ] **Step 2: Walk through normal user flows manually.** Review `/help`, `/profile`, `/rank`, `/level`, `/leaderboard`, `/title select`, and `/weekly_leaderboard` for self/other/empty/timeout states.
- [ ] **Step 3: Walk through administrator flows manually.** Review setup apply/cancel/failure, status healthy/unhealthy, filter add/remove/reset, reward add/list, both reset commands, and event setup/edit/preview/test/clear.
- [ ] **Step 4: Walk through owner flows manually.** Review backup destination/status/manual upload and grant single/mass confirmation, cancellation, progress, and partial failure.
- [ ] **Step 5: Review all ten heuristics.** Record remaining concerns against visibility, real-world language, control, consistency, prevention, recognition, efficiency, minimalism, error recovery, and help. Do not claim a target score without checking the actual Discord rendering and user flows.
- [ ] **Step 6: Verify scope.** Confirm `utils/math_utils.py`, XP earning behavior, database runtime artifacts, and JSONL logs are unchanged. No automated tests are added or run unless the user separately requests them.

## Acceptance Criteria

- All slash commands have clear Indonesian descriptions and correct parameter names; help agrees with registered command behavior.
- `/profile`, `/rank`, and `/level` have distinct and accurate purposes in both command descriptions and help.
- Invalid event input never leaves a partial configuration update.
- Event configuration can be previewed privately and its content can be cleared or restored without accidentally removing unrelated settings.
- `/xp reset_user` and other destructive actions show target, scope, retained data, and an explicit cancel option before execution.
- XP and recap status distinguish configured, running, recently successful, stale, failed, and empty states where those apply.
- Error replies work after both initial responses and deferred interactions, explain a recovery action, and do not reveal internal exception details.
- Command descriptions, button labels, embed field names, and routine body rows contain no decorative emoji. Use at most one semantic status icon per response; keep rank medals and earned badge/title artwork intact.
- Help accurately covers member, admin, event, weekly, and owner command groups without stale examples or misleading claims.
- Manual QA covers normal, empty, denied, invalid-input, timeout, and API/database-failure states for each command category.
