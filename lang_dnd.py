"""
User-facing strings for Dodo Tabletop — **separate from ``lang.py`` on purpose.**

The tabletop engine is kept apart from the rest of the bot at every shared
surface: its own strings (here), its own parameters
(``helpers/dnd/parameters.py``), its own dashboard section, its own storage. The
one registry that says what belongs to it is ``helpers/dnd/registry.py``.

Why separate rather than another section of ``lang.py``: this is a product with
its own vocabulary and its own release cycle, and mixing 200 tabletop strings
into the bot's general file would make both harder to translate, review and
eventually extract.

--------------------------------------------------------------------------- #
MERGE NOTE — how this rejoins the rest of the bot later
--------------------------------------------------------------------------- #
``lang.py`` is wrapped by ``helpers/lang_manager.LangManager``, which makes every
string overridable per guild and per locale from the panel's ``/lang`` page, and
mutates the module in place so existing ``lang.KEY`` reads pick edits up live.

This file is a plain module today, so tabletop strings are **not** panel-editable.
To merge: construct a second ``LangManager(lang_dnd, config_py.dnd_lang_overrides)``
and hang it on the bot (e.g. ``bot.dnd_lang``), then teach the ``/lang`` page to
render more than one module. That is a small change and deliberately deferred —
it needs the panel work, not this file.

Convention: keys are prefixed ``TT_`` (tabletop) for the engine and ``DND_`` for
the legacy cog. The ``DND_`` block goes when ``cogs/dnd_legacy.py`` is deleted
(``docs/dnd/13-MIGRATION.md`` §6).
"""

# --------------------------------------------------------------------------- #
#  Campaigns
# --------------------------------------------------------------------------- #
TT_NO_CAMPAIGN = "No campaign here yet. A GM can start one with `/campaign create`."
TT_CAMPAIGN_CREATED = "Campaign **{name}** created on the **{ruleset}** ruleset. You're its GM — players join with `/campaign join {name}`."
TT_CAMPAIGN_EXISTS = "This server already has a campaign called **{name}**."
TT_CAMPAIGN_NOT_FOUND = "No campaign called **{name}** on this server."
TT_CAMPAIGN_NEEDS_NAME = "Give the campaign a name."
TT_CAMPAIGN_LIST_TITLE = "Campaigns on this server"
TT_CAMPAIGN_LIST_LINE = "**{name}** — {ruleset}, {players} player(s), {status}"
TT_CAMPAIGN_LIST_EMPTY = "No campaigns yet. A GM can start one with `/campaign create`."
TT_CAMPAIGN_JOINED = "You've joined **{name}**. Make a character with `/character create`."
TT_CAMPAIGN_ALREADY_IN = "You're already in **{name}**."
TT_CAMPAIGN_LEFT = "You've left **{name}**. Your character is kept."
TT_CAMPAIGN_NOT_IN = "You're not in **{name}**."
TT_NOT_GM = "Only a GM of **{name}** can do that."
TT_GM_CANNOT_LEAVE = "You're the last GM of **{name}** — hand it over before leaving."

# --------------------------------------------------------------------------- #
#  Characters & sheets
# --------------------------------------------------------------------------- #
TT_CHARACTER_CREATED = "**{name}** joins **{campaign}**. `/character sheet` to see them."
TT_CHARACTER_EXISTS = "You already play **{name}** in **{campaign}**."
TT_NO_CHARACTER = "You have no character in **{campaign}** yet — `/character create`."
TT_CHARACTER_RETIRED = "**{name}** has been retired."
TT_SHEET_FOOTER = "{ruleset} · {campaign}"

# --------------------------------------------------------------------------- #
#  Dice & resolution
# --------------------------------------------------------------------------- #
TT_ROLL_INVALID = "I can't read `{expr}`. Try `1d20`, `2d6+3`, `4d6kh3`, or `1d20adv`."
TT_ROLL_TOO_BIG = "That's more dice than this server allows ({max_dice}d{max_sides} at most)."
TT_ROLL_RESULT = "🎲 `{expr}` → **{total}**"
TT_ROLL_BREAKDOWN = "{rolls}{modifier}"
TT_CHECK_RESULT = "🎲 **{name}** rolls {approach}: `{expr}` → **{total}** vs DC {dc} — **{outcome}**"

# --------------------------------------------------------------------------- #
#  Scenes
# --------------------------------------------------------------------------- #
TT_SCENE_OPENED = "Scene **{title}** is open."
TT_SCENE_CLOSED = "Scene **{title}** is closed."
TT_SCENE_NONE = "No open scene here."
TT_SCENE_EXISTS = "There's already an open scene in this channel."
TT_NEEDS_GUILD = "Tabletop commands only work in a server, not in DMs."

# --------------------------------------------------------------------------- #
#  Legacy import (owner tooling)
# --------------------------------------------------------------------------- #
TT_MIGRATE_HEADER = "**Legacy import** — source has {sessions} session(s), {characters} character(s), {actions} action(s).\n"
TT_MIGRATE_CONFIRM = "\nNothing was written. Re-run with `confirm: True` to import for real."
TT_MIGRATE_NO_GUILD = "Run this in the server you want the campaigns imported into."

# --------------------------------------------------------------------------- #
#  Legacy DnD cog (cogs/dnd_legacy.py) — deleted with that cog
# --------------------------------------------------------------------------- #
DND_SESSION_CREATED = "Session **{title}** created and posted in {channel}."
DND_NO_SESSION_CHANNEL = "Error: Session channel not found."
DND_CHARACTER_CREATED = "Character **{name}** created and added to session {session_id}!"
DND_NO_CHARACTER = "No character found in this session. Please sign up first."
DND_ACTION_SUBMITTED = "Action submitted! Check the session channel for the outcome."
DND_GM_ERROR = "Error generating GM response. Please try again."
DND_INITIATIVE_INVALID = "Invalid input. Please enter a numeric value."
DND_SESSION_NOT_FOUND = "Session not found."
DND_INITIATIVE_RECORDED = "Your initiative ({value}) has been recorded."
DND_DICE_INVALID = "Invalid dice format. Please use NdM (e.g., 1d20)."
DND_DICE_RESULT = "Rolled {dice}: {results} (Total: {total})"
DND_ALREADY_SIGNED = "You are already signed up as **{name}**. Use Sign Off to remove yourself."
DND_SIGNED_OFF = "You have been signed off from this session. Your character data remains saved."
DND_NO_INITIATIVE = "No initiative order recorded."
DND_NEXT_TURN = "Next turn: **{name}** (Player ID: {player_id}) with initiative {initiative}."
DND_COMBAT_ENDED = "Combat ended."
DND_DM_ONLY = "Please use this command in DMs with the bot."
DND_SESSION_ENDED = "Session {session_id} has ended."
DND_NO_ACTIONS = "No actions recorded for this session."
DND_STATS_HEADER = "Session Stats:\n"
DND_STATS_LINE = "- {name}: {count} actions\n"

# --------------------------------------------------------------------------- #
#  Knowledge, lore & belief (P1)
# --------------------------------------------------------------------------- #
TT_LORE_ADDED = "Noted. **{title}** is now part of {campaign}'s world."
TT_LORE_SECRET_ADDED = "Noted privately. **{title}** is GM-only — players will never see it."
TT_LORE_REMOVED = "**{title}** is no longer canon."
TT_LORE_NOT_FOUND = "No fact called **{title}** in this campaign."
TT_LORE_EMPTY = "Nothing written down yet. A GM can add some with `/lore add`."
TT_LORE_LIST_TITLE = "{campaign} — world knowledge"
TT_LORE_SEARCH_EMPTY = "Nothing on file about that."
TT_LORE_SEARCH_TITLE = "Knowledge matching “{query}”"
TT_LORE_TOO_LONG = "That's longer than a fact should be — keep it under {limit} characters and split it up."

TT_LOOK_TITLE = "{name} looks around"
TT_LOOK_NO_SCENE = "There's no scene open here to look at."
TT_LOOK_NOTHING_KNOWN = "Nothing you know of bears on this place."
TT_LOOK_PRESENT = "Present"
TT_LOOK_BELIEFS = "What you believe"
TT_LOOK_FOOTER = "You see what {name} would see — not what is true."

TT_KNOWS_TITLE = "What {name} believes"
TT_KNOWS_EMPTY = "**{name}** believes nothing in particular yet."
TT_KNOWS_LINE = "{certainty} · {claim}"
TT_KNOWS_WRONG = " ⚠️ *(false)*"
TT_KNOWS_NOT_YOURS = "You can only look inside your own character's head."
TT_BELIEF_ADDED = "**{name}** now believes: {claim}"
TT_BELIEF_NO_TARGET = "No entity called **{name}** in this campaign."

TT_CANON_EMPTY = "Nothing waiting for review. Invented facts land here once the narrator is switched on."
TT_CANON_TITLE = "Proposed canon — {count} awaiting review"
TT_CANON_LINE = "**{title}** — {text}"
