"""
Dodo Tabletop — the Discord surface.

Design in ``docs/dnd/``; read ``README.md`` before changing anything here.

P0 is the spine: campaigns, characters with sheets that come from a **ruleset**,
scenes bound to channels, and dice that actually feed resolution. No language
model is involved anywhere in this file, and none is needed — that is the point
of the architecture, not a limitation of the phase.

Three things worth knowing before editing:

* **Nothing here touches a collection.** Every read and write goes through a
  scoped repository (``helpers/dnd/store/``), which is what makes it impossible
  to serve one server another server's campaign.
* **Every resolution is seeded from the event log.** The RNG comes from
  ``event_seed(campaign.seed, seq)``, so a campaign replays exactly. Reaching for
  the ``random`` module in a resolution path would quietly break that.
* **The command groups are class attributes**, not instances built in
  ``__init__``. That is what binds them to the cog, and the binding is what
  ``bot._app_visibility_check`` reads to decide whether this cog is enabled for a
  guild — groups added to the tree by hand would report no cog and slip the
  per-guild switch.

The cog is named ``dnd`` so the existing visibility and category machinery keeps
working; the legacy session manager now loads as ``dnd_legacy``.
"""

from __future__ import annotations

from random import Random

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

import lang_dnd
from cogs.dnd import context, embeds, knowledge as kb, minds_ui
from helpers import checks
from helpers.dnd import migrate, minds, rules
from helpers.dnd import tuning as tuning_registry
from helpers.dnd import parameters as dnd_params
from helpers.dnd.rules import dice
from helpers.dnd.rules.ruleset import Action
from helpers.dnd.store import campaign_store, campaigns_for, ensure_indices
from helpers.dnd.world import event as events
from helpers.dnd.world.campaign import Campaign
from helpers.dnd.world.entity import KIND_PC, TIER_FOCUS, Entity, Identity, Position
from helpers.dnd.world.belief import SOURCE_ASSUMED, adopt
from helpers.dnd.world.event import event_seed
from helpers.dnd.mind.relationships import kinds as relationship_kinds
from helpers.dnd.world.knowledge import Fact
from helpers.dnd.world.scene import Scene

MAX_NAME = 60
# One jump forward is capped so a slip of the keyboard cannot age a whole
# campaign into dust. Repeat the command to go further.
MAX_ADVANCE_DAYS = 3650


def _seeded(campaign: Campaign, seq: int) -> Random:
    """The RNG for resolving one event — derived, never ad hoc."""
    return Random(event_seed(campaign.seed, seq))


class Tabletop(commands.Cog, name="dnd"):
    """Campaigns, characters, scenes and dice — the P0 spine."""

    campaign = app_commands.Group(
        name="campaign", description="Create and manage tabletop campaigns."
    )
    character = app_commands.Group(
        name="character", description="Make and view your characters."
    )
    scene = app_commands.Group(name="scene", description="Open and close scenes. (GM)")
    lore = app_commands.Group(
        name="lore", description="The campaign's world knowledge."
    )
    npc = app_commands.Group(name="npc", description="The people who live in the world.")
    tune = app_commands.Group(
        name="tune", description="Simulation settings for this campaign."
    )

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        ensure_indices()

    # ------------------------------------------------------------------ #
    #  /campaign
    # ------------------------------------------------------------------ #
    @campaign.command(name="create", description="Start a new campaign on this server.")
    @app_commands.describe(
        name="What the campaign is called.",
        ruleset="Which rules to play by. Defaults to the server's setting.",
        channel="Channel scenes will be opened in. Defaults to here.",
    )
    async def campaign_create(
        self,
        interaction: discord.Interaction,
        name: str,
        ruleset: str | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(lang_dnd.TT_NEEDS_GUILD, ephemeral=True)
            return

        name = name.strip()[:MAX_NAME]
        if not name:
            await interaction.response.send_message(lang_dnd.TT_CAMPAIGN_NEEDS_NAME, ephemeral=True)
            return

        repo = campaigns_for(interaction.guild_id)
        if repo.by_name(name):
            await interaction.response.send_message(
                lang_dnd.TT_CAMPAIGN_EXISTS.format(name=name), ephemeral=True
            )
            return

        key = ruleset or dnd_params.get(interaction.guild_id, "dnd_default_ruleset")
        resolved = rules.get(key)
        target = channel or interaction.channel

        created = repo.create(
            Campaign(
                guild_id=interaction.guild_id,
                name=name,
                ruleset=resolved.key,
                gm_ids=[interaction.user.id],
                channel_id=getattr(target, "id", 0) or 0,
            )
        )
        store = campaign_store(interaction.guild_id, created.id)
        store.events.append(
            events.CAMPAIGN_CREATED,
            actor_id=interaction.user.id,
            payload={"name": name, "ruleset": resolved.key},
        )
        await interaction.response.send_message(
            lang_dnd.TT_CAMPAIGN_CREATED.format(name=name, ruleset=resolved.label)
        )

    @campaign_create.autocomplete("ruleset")
    async def _ruleset_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [
            app_commands.Choice(name=r.label, value=r.key)
            for r in rules.all_rulesets()
            if current in r.key.lower() or current in r.label.lower()
        ][:25]

    @campaign.command(name="list", description="Campaigns running on this server.")
    async def campaign_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(lang_dnd.TT_NEEDS_GUILD, ephemeral=True)
            return
        campaigns = campaigns_for(interaction.guild_id).list()
        await interaction.response.send_message(
            embed=embeds.campaign_list(campaigns, {}), ephemeral=True
        )

    @campaign.command(name="info", description="Show a campaign's details.")
    async def campaign_info(
        self, interaction: discord.Interaction, name: str | None = None
    ) -> None:
        found = context.resolve(interaction, name)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embeds.campaign_info(
                found.campaign,
                characters=found.store.entities.count({"kind": KIND_PC, "retired": False}),
                scenes=found.store.scenes.count(),
            )
        )

    @campaign.command(name="join", description="Join a campaign as a player.")
    async def campaign_join(
        self, interaction: discord.Interaction, name: str | None = None
    ) -> None:
        found = context.resolve(interaction, name)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        if found.campaign.is_member(interaction.user.id):
            await interaction.response.send_message(
                lang_dnd.TT_CAMPAIGN_ALREADY_IN.format(name=found.campaign.name), ephemeral=True
            )
            return
        found.store.campaigns.add_player(found.campaign.id, interaction.user.id)
        found.store.events.append(
            events.PLAYER_JOINED,
            actor_id=interaction.user.id,
            payload={"user_id": interaction.user.id},
        )
        await interaction.response.send_message(
            lang_dnd.TT_CAMPAIGN_JOINED.format(name=found.campaign.name), ephemeral=True
        )

    @campaign.command(name="leave", description="Leave a campaign. Your character is kept.")
    async def campaign_leave(
        self, interaction: discord.Interaction, name: str | None = None
    ) -> None:
        found = context.resolve(interaction, name)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        campaign = found.campaign
        if not campaign.is_member(interaction.user.id):
            await interaction.response.send_message(
                lang_dnd.TT_CAMPAIGN_NOT_IN.format(name=campaign.name), ephemeral=True
            )
            return
        # A campaign with no GM has nobody who can open a scene, so the last one
        # out has to hand it over first.
        if campaign.is_gm(interaction.user.id) and len(campaign.gm_ids) == 1:
            await interaction.response.send_message(
                lang_dnd.TT_GM_CANNOT_LEAVE.format(name=campaign.name), ephemeral=True
            )
            return
        found.store.campaigns.remove_player(campaign.id, interaction.user.id)
        found.store.campaigns.remove_gm(campaign.id, interaction.user.id)
        found.store.events.append(
            events.PLAYER_LEFT,
            actor_id=interaction.user.id,
            payload={"user_id": interaction.user.id},
        )
        await interaction.response.send_message(
            lang_dnd.TT_CAMPAIGN_LEFT.format(name=campaign.name), ephemeral=True
        )

    # ------------------------------------------------------------------ #
    #  /character
    # ------------------------------------------------------------------ #
    @character.command(name="create", description="Make a character in a campaign.")
    @app_commands.describe(
        name="Your character's name.",
        role="Their calling — wizard, harbourmaster, thief. Shapes their stats.",
        species="Optional. Human, elf, whatever the setting has.",
        pronouns="Optional. Defaults to they/them.",
        campaign="Which campaign, if you're in more than one.",
    )
    async def character_create(
        self,
        interaction: discord.Interaction,
        name: str,
        role: str,
        species: str | None = None,
        pronouns: str | None = None,
        campaign: str | None = None,
    ) -> None:
        found = context.resolve(interaction, campaign)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return

        existing = found.store.entities.character_of(interaction.user.id)
        if existing is not None:
            await interaction.response.send_message(
                lang_dnd.TT_CHARACTER_EXISTS.format(name=existing.name, campaign=found.campaign.name),
                ephemeral=True,
            )
            return

        # Making a character is how most people join, so don't make them run
        # /campaign join first.
        if not found.campaign.is_member(interaction.user.id):
            found.store.campaigns.add_player(found.campaign.id, interaction.user.id)

        ruleset = rules.get(found.campaign.ruleset)
        seq = found.store.campaigns.next_seq(found.campaign.id)
        stats = ruleset.blank_sheet(
            {"name": name, "role": role, "species": species or ""},
            _seeded(found.campaign, seq),
        )

        entity = found.store.entities.create(
            Entity(
                guild_id=found.campaign.guild_id,
                campaign_id=found.campaign.id,
                kind=KIND_PC,
                tier=TIER_FOCUS,
                owner_id=interaction.user.id,
                identity=Identity(
                    name=name.strip()[:MAX_NAME],
                    pronouns=(pronouns or "they/them").strip(),
                    species=(species or "").strip(),
                    role=role.strip(),
                ),
                stats=stats,
                importance=1.0,          # PCs are always fully simulated
                position=Position(),
            )
        )
        found.store.events.append(
            events.CHARACTER_CREATED,
            actor_id=entity.id,
            seq=seq,                 # the number the sheet's RNG was derived from
            seed=event_seed(found.campaign.seed, seq),
            payload={
                "name": entity.name,
                "role": role,
                "ruleset": ruleset.key,
                "user_id": interaction.user.id,
            },
        )
        await interaction.response.send_message(
            lang_dnd.TT_CHARACTER_CREATED.format(name=entity.name, campaign=found.campaign.name),
            embed=embeds.character_sheet(entity, found.campaign),
        )

    @character.command(name="sheet", description="Show a character sheet.")
    @app_commands.describe(
        who="Whose character to show. Defaults to yours.",
        campaign="Which campaign, if you're in more than one.",
    )
    async def character_sheet(
        self,
        interaction: discord.Interaction,
        who: discord.User | None = None,
        campaign: str | None = None,
    ) -> None:
        found = context.resolve(interaction, campaign)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return

        target = who or interaction.user
        entity = found.store.entities.character_of(target.id)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NO_CHARACTER.format(campaign=found.campaign.name), ephemeral=True
            )
            return
        # Your own sheet is ephemeral; looking at someone else's is a
        # table-facing act, so it gets posted.
        await interaction.response.send_message(
            embed=embeds.character_sheet(entity, found.campaign),
            ephemeral=who is None,
        )

    @character.command(name="retire", description="Retire your character in a campaign.")
    async def character_retire(
        self, interaction: discord.Interaction, campaign: str | None = None
    ) -> None:
        found = context.resolve(interaction, campaign)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        entity = found.store.entities.character_of(interaction.user.id)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NO_CHARACTER.format(campaign=found.campaign.name), ephemeral=True
            )
            return
        found.store.entities.retire(entity.id)
        found.store.events.append(
            events.CHARACTER_RETIRED,
            actor_id=entity.id,
            payload={"name": entity.name, "user_id": interaction.user.id},
        )
        await interaction.response.send_message(
            lang_dnd.TT_CHARACTER_RETIRED.format(name=entity.name)
        )

    # ------------------------------------------------------------------ #
    #  /scene
    # ------------------------------------------------------------------ #
    @scene.command(name="open", description="Open a scene in this channel. (GM)")
    async def scene_open(
        self, interaction: discord.Interaction, title: str, campaign: str | None = None
    ) -> None:
        found = context.resolve(interaction, campaign)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        if found.store.scenes.open_in_channel(interaction.channel_id) is not None:
            await interaction.response.send_message(lang_dnd.TT_SCENE_EXISTS, ephemeral=True)
            return

        # Everyone with a character starts present, and present means focus tier
        # — the simulation only pays for who is on screen.
        present = found.store.entities.characters()
        opened = found.store.scenes.create(
            Scene(
                guild_id=found.campaign.guild_id,
                campaign_id=found.campaign.id,
                title=title.strip()[:MAX_NAME],
                channel_id=interaction.channel_id or 0,
                present=[e.id for e in present],
            )
        )
        for entity in present:
            found.store.entities.set_tier(entity.id, TIER_FOCUS)
        found.store.events.append(
            events.SCENE_OPENED,
            actor_id=interaction.user.id,
            payload={"title": opened.title, "scene_id": str(opened.id)},
        )

        await interaction.response.send_message(
            lang_dnd.TT_SCENE_OPENED.format(title=opened.title),
            embed=embeds.scene_card(opened, found.campaign, present),
        )
        try:
            message = await interaction.original_response()
            found.store.scenes.attach_message(opened.id, message.id)
        except discord.HTTPException:
            pass    # the card is a convenience; a scene without one still works

    @scene.command(name="close", description="Close the scene in this channel. (GM)")
    async def scene_close(self, interaction: discord.Interaction) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        open_scene = found.store.scenes.open_in_channel(interaction.channel_id)
        if open_scene is None:
            await interaction.response.send_message(lang_dnd.TT_SCENE_NONE, ephemeral=True)
            return
        found.store.scenes.close(open_scene.id)
        found.store.events.append(
            events.SCENE_CLOSED,
            actor_id=interaction.user.id,
            payload={"title": open_scene.title, "scene_id": str(open_scene.id)},
        )
        await interaction.response.send_message(
            lang_dnd.TT_SCENE_CLOSED.format(title=open_scene.title)
        )

    # ------------------------------------------------------------------ #
    #  Dice
    # ------------------------------------------------------------------ #
    # Named "dice", not "roll": the deathroll minigame has owned /roll since long
    # before this existed, and breaking a command people already use to give a new
    # subsystem the prettier name is not a trade worth making.
    @app_commands.command(name="dice", description="Roll dice: 2d6+3, 4d6kh3, 1d20adv.")
    @app_commands.describe(expression="What to roll.", private="Only you see the result.")
    async def dice_roll(
        self, interaction: discord.Interaction, expression: str, private: bool = False
    ) -> None:
        max_dice = dnd_params.get(interaction.guild_id, "dnd_max_dice")
        max_sides = dnd_params.get(interaction.guild_id, "dnd_max_sides")
        try:
            spec = dice.parse(expression, max_dice=max_dice, max_sides=max_sides)
        except dice.DiceLimitError as limit:
            await interaction.response.send_message(
                lang_dnd.TT_ROLL_TOO_BIG.format(max_dice=limit.max_dice, max_sides=limit.max_sides),
                ephemeral=True,
            )
            return
        if spec is None:
            await interaction.response.send_message(
                lang_dnd.TT_ROLL_INVALID.format(expr=expression), ephemeral=True
            )
            return

        # A bare roll is not a world event, so it takes a fresh RNG rather than
        # consuming a sequence number. Only resolutions go in the log.
        result = dice.roll(spec, Random())
        await interaction.response.send_message(
            embed=embeds.roll_result(str(spec), result, author=interaction.user.display_name),
            ephemeral=private,
        )

    @app_commands.command(name="check", description="Make a check with your character.")
    @app_commands.describe(
        approach="Which ability, skill or approach you're using.",
        dc="Target number. Defaults to the ruleset's.",
        description="What you're actually trying to do.",
    )
    async def check(
        self,
        interaction: discord.Interaction,
        approach: str,
        dc: int | None = None,
        description: str | None = None,
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        entity = found.store.entities.character_of(interaction.user.id)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NO_CHARACTER.format(campaign=found.campaign.name), ephemeral=True
            )
            return

        ruleset = rules.get(found.campaign.ruleset)
        seq = found.store.campaigns.next_seq(found.campaign.id)
        seed = event_seed(found.campaign.seed, seq)
        action = Action(
            kind="check", approach=approach, text=(description or "").strip(), difficulty=dc
        )
        outcome = ruleset.resolve(action, entity.stats, None, Random(seed))

        # The resolution *is* the event. Storing the trace means a GM can later
        # ask why a roll went the way it did, and a replay reproduces it exactly.
        found.store.events.append(
            events.CHECK,
            actor_id=entity.id,
            seq=seq,                 # the number this roll's seed came from
            seed=seed,
            payload={
                "approach": approach,
                "dc": outcome.dc,
                "degree": outcome.degree,
                "total": outcome.roll.total if outcome.roll else None,
                "faces": list(outcome.roll.faces) if outcome.roll else [],
                "detail": outcome.detail,
                "text": action.text,
                "user_id": interaction.user.id,
            },
        )
        await interaction.response.send_message(
            embed=embeds.check_result(entity, outcome, found.campaign)
        )

    # ------------------------------------------------------------------ #
    #  /lore — the campaign knowledge base (P1)
    # ------------------------------------------------------------------ #
    @lore.command(name="add", description="Write something into the campaign's world. (GM)")
    @app_commands.describe(
        title="Short name for the fact.",
        text="What is true.",
        kind="What sort of thing this is.",
        secret="GM-only: players never see it, but the engine does.",
        weight="0-1. How central this is; higher means it surfaces more often.",
    )
    async def lore_add(
        self,
        interaction: discord.Interaction,
        title: str,
        text: str,
        kind: str = "lore",
        secret: bool = False,
        weight: float = 0.5,
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        if len(text) > kb.MAX_FACT_CHARS:
            await interaction.response.send_message(
                lang_dnd.TT_LORE_TOO_LONG.format(limit=kb.MAX_FACT_CHARS), ephemeral=True
            )
            return

        fact = found.store.knowledge.add(
            Fact(
                kind=kind,
                title=title.strip()[: kb.MAX_TITLE_CHARS],
                text=text.strip(),
                secret=secret,
                weight=max(0.0, min(1.0, weight)),
            )
        )
        # A secret confirmation is ephemeral, or announcing it defeats the point.
        message = (
            lang_dnd.TT_LORE_SECRET_ADDED if secret else lang_dnd.TT_LORE_ADDED
        ).format(title=fact.title, campaign=found.campaign.name)
        await interaction.response.send_message(message, ephemeral=secret)

    @lore_add.autocomplete("kind")
    async def _kind_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [c for c in kb.kind_choices() if current in c.value][:25]

    @lore.command(name="list", description="Everything written down about this campaign.")
    async def lore_list(self, interaction: discord.Interaction, kind: str | None = None) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        is_gm = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        ) == ""
        facts = found.store.knowledge.campaign_facts(kind=kind)
        if not is_gm:
            facts = [f for f in facts if not f.secret]
        await interaction.response.send_message(
            embed=kb.lore_list(facts, found.campaign.name, show_secret=is_gm), ephemeral=True
        )

    @lore.command(name="search", description="Look something up in the campaign's world.")
    async def lore_search(self, interaction: discord.Interaction, query: str) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        is_gm = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        ) == ""
        facts = found.store.knowledge.search(query, include_secret=is_gm)
        await interaction.response.send_message(
            embed=kb.lore_search(facts, query, show_secret=is_gm), ephemeral=True
        )

    @lore.command(name="remove", description="Remove a fact from the campaign. (GM)")
    async def lore_remove(self, interaction: discord.Interaction, title: str) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        match = next(
            (f for f in found.store.knowledge.campaign_facts()
             if f.title.lower() == title.strip().lower()),
            None,
        )
        if match is None:
            await interaction.response.send_message(
                lang_dnd.TT_LORE_NOT_FOUND.format(title=title), ephemeral=True
            )
            return
        found.store.knowledge.remove(match.id)
        await interaction.response.send_message(
            lang_dnd.TT_LORE_REMOVED.format(title=match.title), ephemeral=True
        )

    # ------------------------------------------------------------------ #
    #  Fog of war (P1)
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="look", description="See the scene as your character understands it."
    )
    async def look(self, interaction: discord.Interaction) -> None:
        """A player's view is built from their character's beliefs, never from
        world truth. Retrieval runs with ``for_player=True``, so a secret cannot
        reach this embed even if the rendering below is wrong."""
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        entity = found.store.entities.character_of(interaction.user.id)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NO_CHARACTER.format(campaign=found.campaign.name), ephemeral=True
            )
            return

        scene = found.store.scenes.open_in_channel(interaction.channel_id)
        present = []
        if scene is not None:
            present = [e for e in found.store.entities.list() if e.id in scene.present]

        beliefs = found.store.beliefs.held_by(entity.id, limit=10)
        facts = found.store.knowledge.retrieve(
            query=scene.title if scene else "",
            budget=dnd_params.get(interaction.guild_id, "dnd_kb_budget"),
            max_facts=dnd_params.get(interaction.guild_id, "dnd_kb_max_facts"),
            scene_id=scene.id if scene else None,
            present_entities=[e.id for e in present],
            for_player=True,
        )
        await interaction.response.send_message(
            embed=kb.player_view(entity, scene, present, beliefs, facts), ephemeral=True
        )

    @app_commands.command(name="knows", description="What someone believes to be true.")
    @app_commands.describe(who="Whose head to look inside. GMs may name any entity.")
    async def knows(self, interaction: discord.Interaction, who: str | None = None) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        is_gm = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        ) == ""

        if who and not is_gm:
            await interaction.response.send_message(
                lang_dnd.TT_KNOWS_NOT_YOURS, ephemeral=True
            )
            return

        entity = (
            found.store.entities.by_name(who) if who
            else found.store.entities.character_of(interaction.user.id)
        )
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_BELIEF_NO_TARGET.format(name=who) if who
                else lang_dnd.TT_NO_CHARACTER.format(campaign=found.campaign.name),
                ephemeral=True,
            )
            return

        beliefs = found.store.beliefs.held_by(entity.id)
        await interaction.response.send_message(
            embed=kb.gm_view(entity, beliefs, is_gm=is_gm), ephemeral=True
        )

    @app_commands.command(name="believe", description="Give someone a belief. (GM)")
    @app_commands.describe(
        who="Who holds the belief.",
        claim="What they think is true.",
        about="Who or what it concerns. Defaults to the holder.",
        true="Whether it is actually true. Leave unset for undecided.",
    )
    async def believe(
        self,
        interaction: discord.Interaction,
        who: str,
        claim: str,
        about: str | None = None,
        true: bool | None = None,
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return

        holder = found.store.entities.by_name(who)
        if holder is None:
            await interaction.response.send_message(
                lang_dnd.TT_BELIEF_NO_TARGET.format(name=who), ephemeral=True
            )
            return
        subject = found.store.entities.by_name(about) if about else holder
        if subject is None:
            await interaction.response.send_message(
                lang_dnd.TT_BELIEF_NO_TARGET.format(name=about), ephemeral=True
            )
            return

        # Re-asserting something they already hold strengthens it rather than
        # storing a duplicate — otherwise a GM nudging an NPC twice would leave
        # them with two half-held copies of one conviction.
        existing = found.store.beliefs.knows_that(holder.id, claim)
        if existing is not None:
            found.store.beliefs.reinforce(existing.id)
        else:
            belief = adopt(
                claim,
                holder_id=holder.id,
                subject_id=subject.id,
                source_kind=SOURCE_ASSUMED,
                at=found.campaign.world_time,
            )
            belief.truth = true
            found.store.beliefs.add(belief)

        await interaction.response.send_message(
            lang_dnd.TT_BELIEF_ADDED.format(name=holder.identity.name, claim=claim),
            ephemeral=True,
        )

    @app_commands.command(
        name="canon", description="Facts the narrator invented, awaiting review. (GM)"
    )
    async def canon(self, interaction: discord.Interaction) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        await interaction.response.send_message(
            embed=kb.canon_queue(found.store.canon.pending()), ephemeral=True
        )

    # ------------------------------------------------------------------ #
    #  /npc — people with minds (P2)
    # ------------------------------------------------------------------ #
    @npc.command(name="create", description="Bring an NPC into the world. (GM)")
    @app_commands.describe(
        name="What they're called.",
        role="Their calling — harbourmaster, guard, smuggler. Shapes disposition and stats.",
        culture="Where they're from. Nudges disposition and naming.",
        species="Optional.",
        pronouns="Optional. Defaults to they/them.",
        importance="0-1. How much they matter: drives memory capacity and simulation depth.",
    )
    async def npc_create(
        self,
        interaction: discord.Interaction,
        name: str,
        role: str = "",
        culture: str = "",
        species: str = "",
        pronouns: str = "they/them",
        importance: float | None = None,
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        if found.store.entities.by_name(name):
            await interaction.response.send_message(
                lang_dnd.TT_NPC_EXISTS.format(name=name), ephemeral=True
            )
            return

        seq = found.store.campaigns.next_seq(found.campaign.id)
        rng = _seeded(found.campaign, seq)
        entity = minds.spawn_npc(
            found.store,
            name=name.strip()[:MAX_NAME],
            role=role.strip(),
            species=species.strip(),
            culture=culture.strip(),
            pronouns=(pronouns or "they/them").strip(),
            importance=importance,
            world_time=found.campaign.world_time,
            rng=rng,
            ruleset=rules.get(found.campaign.ruleset),
        )
        found.store.events.append(
            events.NPC_SPAWNED,
            actor_id=entity.id,
            seq=seq,
            seed=event_seed(found.campaign.seed, seq),
            payload={"name": entity.name, "role": role, "culture": culture},
        )
        traits = minds.traits_of(entity)
        await interaction.response.send_message(
            lang_dnd.TT_NPC_CREATED.format(
                name=entity.name,
                traits=traits.describe(),
                memories=found.store.memories.count_for(entity.id),
            )
        )

    @npc.command(name="list", description="Everyone who lives in this campaign.")
    async def npc_list(self, interaction: discord.Interaction) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        await interaction.response.send_message(
            embed=minds_ui.npc_list(found.store.entities.npcs(), found.campaign.name),
            ephemeral=True,
        )

    @npc.command(name="mind", description="Look inside someone's head. (GM)")
    @app_commands.describe(who="Whose mind to inspect.")
    async def npc_mind(self, interaction: discord.Interaction, who: str) -> None:
        """The inspector: disposition, body, memory with per-field clarity, and
        why each memory is sticking. Read-only — looking must not change what is
        being looked at, so recall runs without reconsolidation."""
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        entity = found.store.entities.by_name(who)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NPC_NOT_FOUND.format(name=who), ephemeral=True
            )
            return

        tuning = minds.tuning_for(found.store, found.campaign)
        world_time = found.campaign.world_time
        relations = []
        for rel in found.store.relations.outgoing(entity.id)[:8]:
            other = found.store.entities.get(rel.to_id)
            relations.append((other.identity.name if other else "someone", rel))

        await interaction.response.send_message(
            embed=minds_ui.mind_view(
                entity,
                minds.traits_of(entity),
                minds.needs_of(entity, world_time, tuning),
                found.store.memories.for_entity(entity.id),
                minds.impulses_of(entity, world_time, tuning),
                relations,
                tuning=tuning,
                explain=lambda m: minds.explain_retention(entity, m),
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------------ #
    #  Memory (P2)
    # ------------------------------------------------------------------ #
    @app_commands.command(name="remember", description="Give someone a memory. (GM)")
    @app_commands.describe(
        who="Who remembers it.",
        what="What happened, in their words.",
        feeling="-1 (awful) to 1 (wonderful), as it felt to them.",
        detail="A concrete detail — the thing that later becomes a recall cue.",
        clarity="0-1. How well they perceived it. Low means a hazy memory from the start.",
    )
    async def remember(
        self,
        interaction: discord.Interaction,
        who: str,
        what: str,
        feeling: float = 0.0,
        detail: str = "",
        clarity: float = 1.0,
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        entity = found.store.entities.by_name(who)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NPC_NOT_FOUND.format(name=who), ephemeral=True
            )
            return

        seq = found.store.campaigns.next_seq(found.campaign.id)
        memory = minds.remember(
            found.store,
            entity,
            what.strip(),
            world_time=found.campaign.world_time,
            rng=_seeded(found.campaign, seq),
            valence=max(-1.0, min(1.0, feeling)),
            details=[detail.strip()] if detail.strip() else None,
            perception=max(0.0, min(1.0, clarity)),
        )
        if memory is None:
            await interaction.response.send_message(
                lang_dnd.TT_REMEMBER_NOTHING.format(name=entity.identity.name), ephemeral=True
            )
            return

        note = f"salience {memory.salience:.2f}"
        if memory.is_imprint:
            note += " — **that will mark them permanently**"
        note += f"; {minds.explain_retention(entity, memory)}"
        await interaction.response.send_message(
            lang_dnd.TT_REMEMBER_ADDED.format(name=entity.identity.name, detail=note),
            ephemeral=True,
        )

    @app_commands.command(name="recall", description="See what a cue brings to someone's mind. (GM)")
    @app_commands.describe(
        who="Whose memory to stir.",
        cue="What they see, hear or smell — 'lantern', 'rain', a name.",
    )
    async def recall(self, interaction: discord.Interaction, who: str, cue: str) -> None:
        """Recall *rewrites*: the gist firms up and the present can leak in as a
        false detail. That is deliberate, so this command changes state."""
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        entity = found.store.entities.by_name(who)
        if entity is None:
            await interaction.response.send_message(
                lang_dnd.TT_NPC_NOT_FOUND.format(name=who), ephemeral=True
            )
            return

        cues = [c for c in cue.lower().split() if c]
        seq = found.store.campaigns.next_seq(found.campaign.id)
        imprint = minds.imprint_triggered(
            found.store, entity, cues, found.campaign.world_time
        )
        hits = minds.recall_for(
            found.store,
            entity,
            cues,
            world_time=found.campaign.world_time,
            rng=_seeded(found.campaign, seq),
            present_details=cues,
        )
        await interaction.response.send_message(
            embed=minds_ui.recall_view(entity, hits, imprint), ephemeral=True
        )

    # ------------------------------------------------------------------ #
    #  Relationships (P2)
    # ------------------------------------------------------------------ #
    @app_commands.command(name="relate", description="Record something between two people, or look. (GM)")
    @app_commands.describe(
        who="Whose feelings change.",
        toward="About whom.",
        what="What happened. Leave blank to just look at the current state.",
    )
    async def relate(
        self, interaction: discord.Interaction, who: str, toward: str, what: str = ""
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        a = found.store.entities.by_name(who)
        b = found.store.entities.by_name(toward)
        if a is None or b is None:
            await interaction.response.send_message(
                lang_dnd.TT_NPC_NOT_FOUND.format(name=who if a is None else toward),
                ephemeral=True,
            )
            return

        if what:
            refusal = context.require_gm(
                found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
            )
            if refusal:
                await interaction.response.send_message(refusal, ephemeral=True)
                return
            if what not in relationship_kinds():
                await interaction.response.send_message(
                    lang_dnd.TT_RELATE_UNKNOWN.format(
                        kind=what, kinds=", ".join(relationship_kinds())
                    ),
                    ephemeral=True,
                )
                return
            updated = minds.relate(
                found.store, a, b, what, world_time=found.campaign.world_time
            )
            await interaction.response.send_message(
                lang_dnd.TT_RELATE_DONE.format(
                    a=a.identity.name, b=b.identity.name, summary=updated.summary()
                )
            )
            return

        await interaction.response.send_message(
            embed=minds_ui.relationship_view(
                a.identity.name,
                b.identity.name,
                found.store.relations.between(a.id, b.id),
                found.store.relations.between(b.id, a.id),
            ),
            ephemeral=True,
        )

    @relate.autocomplete("what")
    async def _relate_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [
            app_commands.Choice(name=k.replace("_", " ").title(), value=k)
            for k in relationship_kinds()
            if current in k
        ][:25]

    # ------------------------------------------------------------------ #
    #  Time (P2 — the manual stand-in for the world tick in P3)
    # ------------------------------------------------------------------ #
    @app_commands.command(name="advance", description="Let time pass, and let minds age. (GM)")
    @app_commands.describe(days="How many in-world days go by.")
    async def advance(self, interaction: discord.Interaction, days: float) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        if days <= 0 or days > MAX_ADVANCE_DAYS:
            await interaction.response.send_message(
                lang_dnd.TT_ADVANCE_TOO_FAR.format(max=MAX_ADVANCE_DAYS), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        seq = found.store.campaigns.next_seq(found.campaign.id)
        report = minds.advance(
            found.store, found.campaign, days, _seeded(found.campaign, seq)
        )
        message = (
            lang_dnd.TT_ADVANCE_FROZEN.format(days=days)
            if report["frozen"]
            else lang_dnd.TT_ADVANCE_DONE.format(
                days=days,
                entities=report["entities"],
                imprints=report["new_imprints"],
                confab=report["confabulated"],
                pruned=report["pruned"],
            )
        )
        await interaction.followup.send(message)

    # ------------------------------------------------------------------ #
    #  Tuning — nothing is baked in (P2)
    # ------------------------------------------------------------------ #
    @tune.command(name="show", description="Current simulation settings for this campaign.")
    async def tune_show(self, interaction: discord.Interaction) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        tuning = minds.tuning_for(found.store, found.campaign)
        await interaction.response.send_message(
            embed=minds_ui.tuning_view(tuning.entries(), found.campaign.name), ephemeral=True
        )

    @tune.command(name="set", description="Change a simulation setting for this campaign. (GM)")
    @app_commands.describe(
        key="Which setting.",
        value="The new value. Leave blank to clear it back to inherited.",
    )
    async def tune_set(
        self, interaction: discord.Interaction, key: str, value: float | None = None
    ) -> None:
        found = context.resolve(interaction)
        if not found:
            await interaction.response.send_message(found.error, ephemeral=True)
            return
        refusal = context.require_gm(
            found.campaign, interaction.user, is_admin=context.is_guild_admin(interaction)
        )
        if refusal:
            await interaction.response.send_message(refusal, ephemeral=True)
            return
        spec = tuning_registry.BY_KEY.get(key)
        if spec is None:
            await interaction.response.send_message(
                lang_dnd.TT_TUNING_UNKNOWN.format(key=key), ephemeral=True
            )
            return

        before = minds.tuning_for(found.store, found.campaign)
        old, source = before.get(key), before.source_of(key)

        settings = dict(found.campaign.settings or {})
        overrides = dict(settings.get("tuning") or {})
        if value is None:
            overrides.pop(key, None)
        else:
            overrides[key] = tuning_registry.coerce(key, value)
        settings["tuning"] = overrides
        found.store.campaigns.save_settings(found.campaign.id, settings)

        found.campaign.settings = settings
        after = minds.tuning_for(found.store, found.campaign)
        template = (
            lang_dnd.TT_TUNING_CLEARED if value is None else lang_dnd.TT_TUNING_SET
        )
        await interaction.response.send_message(
            template.format(
                label=spec["label"], value=after.get(key), old=old, source=source
            ),
            ephemeral=True,
        )

    @tune_set.autocomplete("key")
    async def _tune_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [
            app_commands.Choice(name=f"{s['group']}: {s['label']}", value=s["key"])
            for s in tuning_registry.TUNABLES
            if current in s["key"] or current in s["label"].lower()
        ][:25]

    # ------------------------------------------------------------------ #
    #  Legacy import (owner only)
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(
        name="dndmigrate",
        description="Import legacy DnD sessions into this server (owner only).",
        hidden=True,
    )
    @checks.is_owner()
    @app_commands.describe(
        confirm="Off by default: the command reports what it would do and writes nothing.",
        ruleset="Which ruleset the imported campaigns should use.",
    )
    async def dnd_migrate(
        self, context: Context, confirm: bool = False, ruleset: str = "srd5e"
    ) -> None:
        """Dry run unless ``confirm`` is set.

        The old ``dodo_dnd`` database is never modified either way — it stays as
        the rollback (``docs/dnd/13-MIGRATION.md`` §5).
        """
        if context.guild is None:
            await context.send(lang_dnd.TT_MIGRATE_NO_GUILD)
            return

        async with context.typing():
            counts = migrate.legacy_counts()
            report = (
                migrate.execute(context.guild.id, ruleset_key=ruleset)
                if confirm
                else migrate.plan(context.guild.id, ruleset_key=ruleset)
            )

        body = lang_dnd.TT_MIGRATE_HEADER.format(
            sessions=counts["sessions"],
            characters=counts["characters"],
            actions=counts["actions"],
        )
        body += "\n".join(f"- {line}" for line in report.lines())
        if not confirm:
            body += lang_dnd.TT_MIGRATE_CONFIRM
        for chunk in range(0, len(body), 2000):
            await context.send(body[chunk : chunk + 2000])

    @check.autocomplete("approach")
    async def _approach_autocomplete(self, interaction: discord.Interaction, current: str):
        """Offer the approaches of *this campaign's* ruleset, so a freeform table
        never sees a list of 5e skills."""
        found = context.resolve(interaction)
        if not found:
            return []
        entity = found.store.entities.character_of(interaction.user.id)
        options = rules.get(found.campaign.ruleset).approaches(entity.stats if entity else {})
        current = (current or "").lower()
        return [
            app_commands.Choice(name=option.title(), value=option)
            for option in options
            if current in option.lower()
        ][:25]


async def setup(bot):
    await bot.add_cog(Tabletop(bot))
