# Per-Server Command Parameters — Master Plan (DRAFT for revision)

Goal: for every command/feature, expose the values worth tuning **per server** so the bot works
for any guild (the final step before multiserver). You'll revise this, then we implement cog by cog.

## How to read this
Each parameter row: **`key`** — description · *type* · **default** (current source).

**Legend (source):**
- `[GUILD]` — a per-guild key already exists in `GuildConfigManager.MANAGED_KEYS`, **but** the cog
  currently reads the **global** `config_py.X` instead → needs migrating to
  `bot.guild_config.get(guild_id, "X")`. (Big theme — most channel IDs are like this.)
- `[GLOBAL]` — currently a global constant in `config/constants.py`; make per-guild.
- `[HARD]` — hardcoded literal in the cog; lift into a per-guild parameter.
- `[LANG]` — text already editable via the Strings editor; listed only for context.

**Types:** `int` `float` `bool` `str` `channel` `role` `emoji` `list[role]` `list[channel]`
`list[str]` `choice`.

## Proposed mechanism (for discussion, not yet built)
A per-guild **`command_params`** store (mirroring `VisibilityManager`/`cog_guild_state`):
`{guild_id, key, value}`, typed, with the values below as built-in defaults. Cogs read via a
helper like `bot.params.get(guild_id, "key")`. The control panel gets a **Parameters** section per
cog (under each category card) with typed inputs. Channel/role params reuse the existing
`GuildConfigManager` where a key already exists; new gameplay params go in `command_params`.
**Migration note:** wherever a cog reads `config_py.<CHANNEL>` directly, switch it to the per-guild
lookup as part of the same cog's pass.

---

# 🎮 Minigames

## cheese — `cheese` cog (listener: cheese drops)
No commands; all parameters tune the drop/stretch game (currently `config/constants.py`).
- **`cheese_drop_threshold`** — 0–1000 roll; drop if roll > this · *int* · **985** `[GLOBAL]`
- **`cheese_event_timeout`** — seconds of inactivity before fizzle · *int* · **25** `[GLOBAL]`
- **`cheese_pull_strengths`** — stretch added per pull · *list[str]→int* · **2,3,5,6,8** `[GLOBAL]`
- **`cheese_steal_divisor`** — thief takes ceil(stretch/this) · *int* · **5** `[GLOBAL]`
- **`cheese_mouse_chance`** — per-pull mouse-peek chance · *float* · **0.02** `[GLOBAL]`
- **`cheese_mouse_sweetrolls`** — sweetrolls if mouse eats it · *int* · **5** `[GLOBAL]`
- **`mouse_adoption_rank`** — relationship pts to offer adoption · *int* · **250** `[GLOBAL]` (shared with racing)
- *(Cheese types table `CHEESE_TYPES` — likely keep global; flag if you want per-guild.)*

## pumpkin — `pumpkin` cog (`pumpkinstats`, `reputation`, `fight`)
- **`pumpkin_role_id`** — role at 50 pumpkins · *role* · **1430471888412475413** `[HARD]`
- **`pumpkin_role_threshold`** — pumpkins needed for the role · *int* · **50** `[HARD]`
- **`pumpkin_weight_range`** — giant-pumpkin weight min/max · *int,int* · **5–800** `[HARD]`
- **`pumpkin_strength_start`** / **`pumpkin_strength_gain`** — base pull & +per pull · *int* · **50 / 5** `[HARD]`
- **`fight`** (team deathmatch): round timing, team size, damage ranges, rewards · *review* `[HARD]`
- *(sweetroll/pumpkin **spawns** live in `bot.py`, not this cog — see Cross-cutting.)*

## deathroll — `deathroll` cog (`roll`)
- **`deathroll_start`** — starting roll ceiling · *int* · **50000000** (`roll_limit`) `[GLOBAL]`
- **`deathroll_min_bet`** / **`deathroll_max_bet`** — bet bounds · *int* · **review** `[HARD]`
- **`deathroll_channel`** — restrict to a channel · *channel* · **ROLL_CHANNEL?** `[GUILD]`
- **`deathroll_timeout`** — accept/turn timeout · *int* · **review** `[HARD]`
- **`deathroll_cooldown`** — per-user cooldown · *int* · **review**

## gilane — `gilane` cog (`gilane`)
- **`gilane_signup_seconds`** — reaction window · *int* · **20** `[HARD]`
- **`gilane_min_participants`** — min to start · *int* · **review** `[HARD]`
- **`gilane_reward`** — reward per event · *int* · **review** `[HARD]`
- **`gilane_spreadsheet_files`/`_links`** — event assets · *list[str]* · `[LANG]`-ish `[GLOBAL]`

## quote — `quote` cog (`quote`, `quotetop`)
- **`quote_channel`** — where the game runs / message source scope · *channel* · **review**
- **`quote_timeout`** — answer window · *int* · **review** `[HARD]`
- **`quote_points_win`** / **`quote_points_steal`** — scoring · *int* · **review** `[HARD]`
- **`quotetop_size`** — leaderboard length · *int* · **review**

## throw — `throw` cog (`throw`)
- **`throw_cooldown`** — per-user cooldown · *int* · **review**
- **`throw_distance_range`** — min/max distance · *int,int* · **review** `[HARD]`
- **`throw_funny_chance`** — chance of a funny flavor line · *float* · **review** `[HARD]`

## pp — `pp` cog (`pp`, `checkpp`, `priorities`, `hotties`)
- **`pp_max_size`** — max pp length rolled · *int* · **review** `[HARD]`
- **`pp_daily_lock`** — whether a user's pp is fixed per day · *bool* · **review**
- **`hotties_size`** — leaderboard length · *int* · **review**

## fun — `fun` cog (`cringe`, `d20`, `d20m`, `roast`, `gay`, `wisdom`, `future`, `fact`, `imagine`)
- **`cringe_pool`** (`CRINGE`) — user IDs eligible for the cringe team · *list* · `[GLOBAL/HARD]`
- **`d20m_join_seconds`** — gather window for group roll · *int* · **review** `[HARD]`
- **`imagine`** — owner-only; model/size · *str/choice* · **review** (visibility already gates it)
- *(roast/gay/future/wisdom/fact are text/RNG pools → mostly `[LANG]`; no per-server params.)*

## economy — `economy` cog (`wallet`, `sweetrolls`)
- **`starting_balance`** — new wallet balance · *int* · **0** `[HARD]`
- *(sweetrolls: read-only stats; no tunables.)*

---

# 🐾 Dodo Universe

## pet — `pet` cog (`cat`, `dog`, `summon`, `petfight`, `showcats`, `showdogs`, `snake`)
- **`pet_channel`** — where claims/summons post · *channel* · **PET_CHANNEL** `[GUILD]`
- **`cat_classes`** / **`dog_classes`** — stat tables · *table* · `[GLOBAL]` (likely keep global; flag)
- **`pet_claim_cost`** — cost to claim (if any) · *int* · **review** `[HARD]`
- **`petfight_cost`** — cost per fight · *int* · **100** (`fighting_cost`) `[GLOBAL]`
- **`pet_name_retry`** — allow re-roll on claim · *bool* · **review**

## fishing — `fishing` cog (`fish`)
- **`fishing_cost`** — cost per attempt · *int* · **10** `[GLOBAL]`
- **`fishing_pond`** / **`fishing_log`** — channels · *channel* · **FISHING_POND / FISHING_LOG** `[GUILD]`
- **`fishing_drop_rates`** — rarity weights · *review* `[HARD]`
- **`fishing_cooldown`** — per-user/per-cat cooldown · *int* · **review**

## gym / fighting — `gym` cog (`gym`)
- **`gym_cost`** — cost per session · *int* · **50** `[GLOBAL]`
- **`gym_muscle_groups`** — options · *list[str]* · `[LANG]`
- **`gym_stat_gain_range`** — stat gain min/max · *int,int* · **review** `[HARD]`

## racing — `racing` cog (`newmouse`, `race`, `gigarace`, `relationships`)
- **`race_countdown_default`** — default signup countdown · *int* · **20** `[HARD default arg]`
- **`race_track_length`** / **`gigarace_track_length`** — track lengths · *int* · **review** `[HARD]`
- **`announcement_channel`** — gigarace announce · *channel* · **ANNOUNCEMENT_CHANNEL** `[GUILD]`
- **`star_inspiration_boost`** / **`_duration`** — starry event · *int* · **5 / 5** `[GLOBAL]`
- **`relationship_base_points`** — race relationship gain · *int* · **20** `[GLOBAL]`
- **`mouse_adoption_rank`** — adoption threshold · *int* · **250** `[GLOBAL]` (shared with cheese)

## racestats — `racestats` cog (`mice`, `mousestats`)
- **`mousestats_size`** — leaderboard length · *int* · **review** (read-only otherwise)

---

# ⚔️ ESO Raiding & Info

## raid_setups — `raid_setups` cog (`create_raid`, `setups`, `markers`, `delete_raid`)
- **`raid_manager_roles`** — who may create/delete raids · *list[role]* · **review** `[HARD]`
- **`setups_page_size`** — fights per page · *int* · **1** `[HARD]`
- **`roster_link_enabled`** — show roster link · *bool* · **review**
- *(Google Sheet parsing config — likely global.)*

## scheduler — `scheduler` cog (`schedule_raid`)
- **`open_raid_channel`** — forum for raid threads · *channel* · **OPEN_RAID_CHANNEL** `[GUILD]`
- **`raid_trials`** — selectable trials · *list[str]* · **review** `[HARD/LANG]`
- **`raid_run_types`** — run-type options · *list[str]* · `SCHED_RUN_TYPES` `[LANG]`
- **`raid_leader_roles`** — who may schedule · *list[role]* · **review**
- **`default_group_size`** — group composition default · *int* · **review** `[HARD]`

## parsing — `parsing` cog (`topparses`, `bottomparses`, `parseold`)
- **`parseold_cooldown`** — per-user cooldown · *int* · **5** `[HARD @cooldown]`
- **`max_parse`** — max dummy parse number · *int* · **210000** `[GLOBAL]`
- **`dummy_health`** — dummy HP · *int* · **21000000** `[GLOBAL]`
- **`parses_leaderboard_size`** — top/bottom N · *int* · **10** `[HARD]`

## parse_tournament — `parse_tournament` cog (`parse`, `stopfest`; listener: reactions)
- **`parse_max_attempts_cap`** — cap on the 1–3 attempts arg · *int* · **3** `[HARD]`
- **`parse_signup_seconds`** — signup window · *int* · **review** `[HARD]`
- **`max_parse_championship`** — max number · *int* · **210000** `[GLOBAL]`
- **`parse_channel`** — restrict where it runs · *channel* · **review**

## pat — `pat` cog (listener: PAT decode)
- **`pat_decode_channel`** — channel it watches · *channel* · **PAT_DECODE_CHANNEL** `[GUILD]`
- **`pat_role_map`** — clear-line → role mapping · *table* · **review** `[HARD]`

---

# 🛡️ Moderation & Server Mgmt

## moderation — `moderation` cog (`kick`, `ban`, `go`, `nick`, `purge`, `pin`, `unpin`)
- **`log_channel`** — mod-action log · *channel* · **LOG_CHANNEL** `[GUILD]`
- **`purge_max`** — max messages per purge · *int* · **review** `[HARD]`
- **`zoomies_role`** / **`zoomies_seconds`** — the `go` timeout role & duration · *role/int* · **review** `[HARD]`
- **`pin_allowed_roles`** — who may pin via reply · *list[role]* · **review** `[HARD]`

## log — `log` cog (`setlogchannel`, `setdeletechannel`; feature: audit_log)
- **`log_channel`** / **`delete_channel`** — already set via commands + `guilds.json` · *channel* · `[GUILD-ish]`
- **`log_events`** — which of the 28 event types to log · *list[str]* · **all** `[HARD]` (nice-to-have granularity)
- **`log_batch_seconds`** — batch flush interval · *int* · **review** `[HARD]`

## spam — `spam` cog (feature: spam_autoban)
- **`spam_threshold`** — msgs in window before action · *int* · **3** (`SPAM_THRESHOLD`) `[GLOBAL]`
- **`spam_time_window`** — seconds · *float* · **2.0** `[GLOBAL]`
- **`multi_channel_threshold`** / **`multi_channel_window`** — cross-channel · *int/float* · **3 / 1.0** `[GLOBAL]`
- **`spam_action`** — ban vs kick vs delete-only · *choice* · **ban** `[HARD]`
- **`spam_exempt_roles`** — roles exempt · *list[role]* · **admins only** `[HARD]`

## event_tracker — `event_tracker` cog (feature: event_tracking)
- **`tracked_channels`** — channel→category+behaviors config · *table* · **review** (already per-channel JSON)
- *(behaviors: images/messages/reactions — keep as the existing config.)*

## seasonal — `seasonal` cog (`love`, `vote`, `resetvote`)
- **`valentine_channel`** — love threads · *channel* · **VALENTINE_CHANNEL** `[GUILD]`
- **`doty_channel`** — vote threads · *channel* · **DOTY_CHANNEL** `[GUILD]`
- **`log_channel`** — love log · *channel* · **LOG_CHANNEL** `[GUILD]`
- **`love_cooldown`** — per-user cooldown · *int* · **review**
- **`doty_enabled`** — seasonal on/off window · *bool* · **review**

## server_config — `server_config` cog (`serverconfig` group)
Admin UI over `GuildConfigManager`; no game params of its own. **Should grow** to surface the new
`command_params` too (or the panel supersedes it).

---

# 🤖 AI & Conversation

## chat — `chat` cog (`chat`) — **DONE**

All 44 parameters are live and editable in the panel under the chat cog; the
string listeners themselves live on the **Events page**, not here, because they
are per-server rows rather than single values. See `docs/CHAT_PERSONA.md` for
what each group is for and how the pieces fit together.

Groups, in the order the panel shows them:

- **The model** — `chat_api_key`, `chat_base_url`, `chat_model`,
  `chat_temperature`, `chat_personality`.
- **What a reply may be** — `chat_reply_max_sentences`, the `chat_spice_*`
  budget, `chat_close_bonus_at` / `chat_distant_penalty_at`,
  `chat_fatigue_bite` / `chat_fatigue_halflife_minutes`,
  `chat_utility_patterns`, `chat_obsession*`.
- **Who she answers** — `chat_respond_to_role_ping`, `chat_ignored_channels`
  (replaces the proposed `chat_channels`, as a deny-list),
  `chat_ambient_multiplier`, `chat_ambient_cooldown_seconds`,
  `chat_user_cooldown_seconds`, `chat_daily_call_cap`.
- **Joining uninvited** — `chat_spontaneous_*`, `chat_context_messages`.
- **Memory and feelings** — `chat_relationship_*`, `chat_sentiment_weight`,
  `chat_familiarity_per_message`, `chat_first_impression_spread`, `chat_grudge*`,
  `chat_fact*`, `chat_rumours_*`.

Two proposed keys were dropped deliberately. `chat_system_prompt` became
`chat_personality` holding *only* the persona — the rest of the prompt is
assembled from state, so exposing it as one editable blob would let a server
break the JSON contract. `chat_memory_enabled`/`chat_memory_length` became
`chat_facts_max` / `chat_facts_recall` / `chat_fact_halflife_days`: memory is a
capped, decaying list rather than a transcript window, so "how many messages
back" was never the knob that mattered.

## talkengine — `talkengine` cog (`imitate`)
- **`imitate_sample_size`** — messages sampled for the Markov chain · *int* · **review** `[HARD]`
- **`imitate_min_messages`** — min history required · *int* · **review** `[HARD]`

## dnd — `dnd` cog (`start_session`, `session_controls`, `end_session`, `save_stats`)
- **`dnd_forum_channel`** — forum for sessions · *channel* · **DND_FORUM_CHANNEL_ID** `[GUILD]`
- **`dnd_gm_roles`** — who may start/GM · *list[role]* · **review** `[HARD]`
- **`dnd_model`** — LLM model · *str* · **review** `[HARD]`
- **`dnd_max_players`** — session size · *int* · **review** `[HARD]`

---

# ⚙️ Core (params exist but not per-server-toggleable)

## general — `general` cog (`info`, `commands`, `guide`, `server`, `dodostats`, `reminder`, `schedule123`, `ping`, `invite`)
- **`weekly_channel`** / **`weekly_message`** — schedule source for `schedule123` · *channel/int* · **WEEKLY_CHANNEL/MESSAGE** `[GUILD]`
- **`reminder_max_minutes`** — cap on `reminder` · *int* · **review** `[HARD]`
- **`guide_api_url`** — WordPress tags API · *str* · **hardcoded in bot.py** `[HARD]` (global is fine)
- *(info/commands/server/ping = infra; no per-server params.)*

---

# Cross-cutting (live in `bot.py`, not a cog) — decide where these belong
These passive behaviors are guild-relevant but currently global in `bot.py`:
- **Sweetroll / rhubarb / pumpkin spawns** — `SWEETROLL_NEEDED` **98**, `SWEETROLL_COOLDOWN` **3**,
  `SWEETROLL_GIFTING` **80** `[GLOBAL]`; spawn channel = `PET_CHANNEL` `[GUILD]`. → likely a
  "Minigames" feature (`sweetroll_drop`) with its own params + guard, like cheese.
- **Guide-tag 📖 reactions** (`check_tags`) — on/off + which channels · → an ESO feature toggle.
- **Harmful-message filter** (`check_for_harmful_messages`) — restricted strings, allowed roles,
  ban-on-invite · → Moderation feature + params.
- **Reaction-roles** (`reaction_roles` map) — per-guild message→emoji→role map `[GLOBAL/HARD]`.
- **Welcome / trap-role autoban** (`on_member_join`, trap) — starter roles, wayshrine channel,
  trap role, alert channel · mostly `[GUILD]` keys already; migrate reads.

---

# Suggested order of work (cog by cog)
1. **Foundational**: build the `command_params` store + panel "Parameters" section + `bot.params`
   helper (types: int/float/bool/str/channel/role/emoji/list). 
2. Then per category, cog by cog: migrate `config_py.<CHANNEL>` reads → per-guild, and wire each
   parameter above. Start with **Moderation** (channels/spam — highest multiserver value), then
   **ESO**, **Dodo Universe**, **Minigames**, **AI**.
3. Fold `bot.py` cross-cutting behaviors into features+params last.

> Revise freely: rename keys, change defaults, drop params you want global, add ones I missed.
> Rows marked **review** are where I inferred a tunable without confirming the exact literal —
> we'll pin those down when we reach that cog.
