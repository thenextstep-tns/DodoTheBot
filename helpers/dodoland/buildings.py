"""
Buildings — what a town is made of, and how a tier is earned.

A building is **per-guild data, not a constant**. Name, icon, the channels that
feed it and what each is worth there, its per-metric multipliers, and its tiers.
Free-form the way trial ranks are free-form: rename it, repoint it, delete it,
add a fourth. Nothing in the engine knows what a "library" is.

Thresholds are derived, not authored
------------------------------------

This is the decision that separates these tiers from the document they came
from, which asked one person for 125,000 acts when the server's entire history
is 306,927 messages. Authored numbers are wrong twice: wrong on day one when
nobody has any, and wrong again in a year when everybody does.

So a tier carries a **percentile** of the server's own live distribution. Tier 6
at percentile 95 means "the top 5% of people who have any score in this
building", and it means that on day one, in three years, on a 60-person server
and on a 600-person one. Nothing has to be re-tuned, and no tier is ever dead.

A tier also carries a small **floor** in absolute points, and the effective
threshold is whichever is higher. That exists for the young-server case: with
four scoring people a percentile is arithmetic rather than an achievement, and
"top 5%" should not be reachable with three messages. The floor stops that
without anybody having to maintain it.

Both numbers are visible in the panel next to what they currently resolve to,
because a threshold you cannot see resolve is exactly the black box the whole
design is trying to avoid.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from helpers.dodoland import metrics as metric_registry

MAX_BUILDINGS = 24
MAX_TIERS = 12
MAX_NAME = 60
MAX_TITLE = 60
MAX_ICON = 8
# A channel's weight is a multiplier, so this is "worth ten times a normal room".
MAX_WEIGHT = 10.0


class DodoLandError(ValueError):
    """A rejected DodoLand setting, with a message meant for the panel."""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return cleaned or "building"


def _clean_text(value: Any, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DodoLandError(f"{field} cannot be empty.")
    if len(text) > limit:
        raise DodoLandError(f"{field} is too long (max {limit} characters).")
    return text


def _weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DodoLandError("A channel weight must be a number.") from None
    if number < 0 or number > MAX_WEIGHT:
        raise DodoLandError(f"A channel weight must be between 0 and {MAX_WEIGHT}.")
    return round(number, 3)


def _percentile(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DodoLandError("A tier percentile must be a number.") from None
    if number < 0 or number > 100:
        raise DodoLandError("A tier percentile must be between 0 and 100.")
    return round(number, 2)


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
def validate_tiers(value: Any) -> list[dict]:
    """``[{title, percentile, floor}]``, kept sorted from easiest to hardest."""
    if not isinstance(value, list):
        raise DodoLandError("Tiers must be a list.")
    if len(value) > MAX_TIERS:
        raise DodoLandError(f"A building can have at most {MAX_TIERS} tiers.")
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise DodoLandError("Each tier must be an object.")
        floor = item.get("floor", 0)
        try:
            floor = max(0, int(floor))
        except (TypeError, ValueError):
            raise DodoLandError("A tier floor must be a whole number of points.") from None
        out.append({
            "title": _clean_text(item.get("title"), MAX_TITLE, "A tier title"),
            "percentile": _percentile(item.get("percentile", 0)),
            "floor": floor,
        })
    out.sort(key=lambda tier: (tier["percentile"], tier["floor"]))
    titles = [tier["title"].lower() for tier in out]
    if len(set(titles)) != len(titles):
        raise DodoLandError("Two tiers in the same building have the same title.")
    return out


def validate_channels(value: Any, *, guild=None) -> dict[str, float]:
    """``{channel id: weight}`` — which rooms feed this building, and how much.

    **Keys come back as strings.** BSON documents may only have string keys, so
    an int-keyed mapping is rejected by the driver and surfaces as a 500 on
    save. Every reader coerces with ``int()`` already, so strings are the safe
    representation and ints are the one that cannot be stored.

    A room may be a channel **or a forum post**: a forum is a container of
    separate rooms rather than a room, so its posts are attachable in their own
    right and are not in ``guild.channels``. Both are accepted, and anything
    belonging to another server is refused, because the panel is per-guild and
    pointing one server at another's rooms would leak activity between them.
    """
    if isinstance(value, list):
        # The panel posts a list of rows; both shapes are accepted so the API
        # does not dictate the widget.
        value = {row.get("channel_id"): row.get("weight", 1) for row in value
                 if isinstance(row, dict)}
    if not isinstance(value, dict):
        raise DodoLandError("A building's channels must be a mapping.")

    known: Optional[set] = None
    if guild is not None:
        known = {int(c.id) for c in getattr(guild, "channels", [])}
        # Active forum posts. An archived one already attached stays attached:
        # it is checked below only when the guild can still see it.
        known |= {int(t.id) for t in (getattr(guild, "threads", []) or [])}

    out: dict[str, float] = {}
    for raw_id, weight in value.items():
        try:
            channel_id = int(raw_id)
        except (TypeError, ValueError):
            raise DodoLandError("A channel id must be a number.") from None
        if known is not None and channel_id not in known:
            # An archived forum post is not in the guild's active lists but is
            # still a real room with real history behind it, so it is kept.
            still_there = None
            if hasattr(guild, "get_thread"):
                still_there = guild.get_thread(channel_id)
            if still_there is None and hasattr(guild, "get_channel"):
                still_there = guild.get_channel(channel_id)
            if still_there is None:
                raise DodoLandError(
                    "A room in this building is not in this server.")
        out[str(channel_id)] = _weight(weight)
    return out


def validate_metric_weights(value: Any) -> dict[str, float]:
    """``{metric_key: multiplier}`` — this building's own emphasis.

    Absent means 1.0. A building that wants pictures to matter more sets
    ``image`` here rather than changing the server-wide weight, which would
    change every other building at the same time.
    """
    if not isinstance(value, dict):
        if value in (None, "", []):
            return {}
        raise DodoLandError("A building's metric weights must be a mapping.")
    out: dict[str, float] = {}
    for key, weight in value.items():
        metric_registry.get(str(key))  # raises KeyError on an unknown metric
        out[str(key)] = _weight(weight)
    return out


def _default_shape_for(key: str) -> str:
    """The shape this key was designed with, or the generic one.

    Read from the built-in set rather than hardcoded, so adding a default
    building adds its shape here with nothing to remember.
    """
    from helpers.dodoland import townart

    for spec in _DEFAULT_SET:
        if spec[0] == key:
            return spec[4]
    return townart.DEFAULT_SHAPE


def validate_building(value: Any, *, guild=None) -> dict:
    """One building, fully checked, ready to store."""
    if not isinstance(value, dict):
        raise DodoLandError("A building must be an object.")
    name = _clean_text(value.get("name"), MAX_NAME, "A building name")
    icon = str(value.get("icon") or "").strip()[:MAX_ICON]
    hints = value.get("hints")
    # The Font Awesome class this building is drawn with on the map. Restricted
    # to the shape of a class name so a building definition cannot inject markup
    # into every page that renders a town.
    fa = str(value.get("fa") or "").strip()[:40]
    if fa and not re.fullmatch(r"[a-z0-9 -]+", fa):
        raise DodoLandError("An icon class may only contain letters, digits, spaces and hyphens.")
    # Which silhouette this building is drawn with on the map. A building's kind
    # has to be legible in outline alone, so this is a choice from a known set
    # rather than free text.
    from helpers.dodoland import townart
    shape = str(value.get("shape") or "").strip()
    if shape and shape not in townart.SHAPES:
        raise DodoLandError(f"There is no {shape!r} building shape.")
    # The emblem hung on it: what the place is *for*, where the shape only says
    # what kind of place it is. A keep with a shield and a keep with a map are
    # the barracks and the war room, and no amount of masonry says which.
    symbol = str(value.get("symbol") or "").strip()
    if symbol and symbol not in townart.GLYPHS:
        raise DodoLandError(f"There is no {symbol!r} emblem.")
    key = _slug(value.get("key") or name)
    # A save that says nothing about the shape must not *decide* one. It used to
    # fall back to the global default, so every save from the panel — and the
    # editor has never had a shape control, and "Suggest rooms" saves too —
    # wrote "inn" over all fifteen buildings on the server. Symbols survived the
    # same treatment only because a blank one is filled in on read, and "inn" is
    # not blank. Falling back to *this key's own* default keeps a library a hall.
    if not shape:
        shape = _default_shape_for(key)
    return {
        "key": key,
        "name": name,
        "icon": icon,
        "fa": fa or "fa-house",
        "shape": shape,
        "symbol": symbol,
        "channels": validate_channels(value.get("channels") or {}, guild=guild),
        "metric_weights": validate_metric_weights(value.get("metric_weights") or {}),
        # Kept through a save so "Suggest from channel names" still has its
        # matching words after the building has been edited once.
        "hints": [str(h)[:40] for h in hints][:40] if isinstance(hints, list) else [],
        "tiers": validate_tiers(value.get("tiers") or []),
    }


def validate_buildings(value: Any, *, guild=None) -> list[dict]:
    """The whole set, with unique keys."""
    if not isinstance(value, list):
        raise DodoLandError("Buildings must be a list.")
    if len(value) > MAX_BUILDINGS:
        raise DodoLandError(f"A server can have at most {MAX_BUILDINGS} buildings.")
    out = [validate_building(item, guild=guild) for item in value]
    keys = [building["key"] for building in out]
    if len(set(keys)) != len(keys):
        raise DodoLandError("Two buildings have the same key. Rename one of them.")
    return out


# --------------------------------------------------------------------------- #
#  Defaults
# --------------------------------------------------------------------------- #
# Six tiers, not thirty. Every one of these will be reached by somebody, which
# is the entire argument: the document this replaces spent sixty of its ninety
# art states on tiers nobody could ever see.
_DEFAULT_TIERS = (
    ("Foundations", 20.0, 25),
    ("Established", 40.0, 100),
    ("Notable", 60.0, 300),
    ("Renowned", 80.0, 800),
    ("Storied", 92.0, 2000),
    ("Legendary", 98.0, 5000),
)


def _tier_set(titles: Iterable[str]) -> list[dict]:
    return [{"title": title, "percentile": pct, "floor": floor}
            for title, (_default, pct, floor) in zip(titles, _DEFAULT_TIERS)]


# A town, as a town is normally imagined: somewhere to drink, somewhere to
# learn, somewhere to trade, somewhere to train, somewhere to worship, somewhere
# to make things. Each entry carries ``hints`` — keywords matched against real
# channel names by :func:`suggest_channels`, so a server attaches its own rooms
# rather than a guess made by somebody who has never seen it.
_DEFAULT_SET: tuple[tuple, ...] = (
    ("tavern", "The Tavern", "🍺",
     "fa-beer-mug-empty",
     "inn",
     "mug",
     ("general", "chat", "lounge", "chill", "hangout", "talk", "offtopic",
      "off-topic", "banter", "social", "main"),
     {}, ("Roadside Bench", "Ale Stall", "The Tap Room", "The Inn",
          "The Great Hall", "Heart of the Town")),
    ("library", "The Grand Library", "📚",
     "fa-book-open",
     "hall",
     "book",
     ("help", "guide", "question", "advice", "info", "resource", "lore", "wiki",
      "faq", "support", "build", "theorycraft", "newbie", "beginner"),
     {}, ("Scholar's Desk", "Reading Nook", "Modest Archive", "The Athenaeum",
          "Grand Library", "Citadel of Wisdom")),
    ("warroom", "The War Room", "🗺",
     "fa-map-location-dot",
     "keep",
     "map",
     ("lead", "officer", "organiser", "organizer", "sherpa", "planning",
      "schedule", "signup", "sign-up", "mentor"),
     {}, ("Chalk Table", "Map Table", "The Planning Room", "The Strategium",
          "The War Room", "Seat of Command")),
    ("barracks", "The Vanguard Barracks", "🛡",
     "fa-shield-halved",
     "keep",
     "shield",
     ("trial", "raid", "lfg", "prog", "dps", "parse", "vet", "roster", "static",
      "score", "hardmode", "trifecta"),
     {}, ("Training Dummy", "Militia Camp", "The Armory", "Guardhouse",
          "Vanguard Keep", "Paragon's Redoubt")),
    ("playhouse", "The Playhouse", "🎮",
     "fa-gamepad",
     "stage",
     "gamepad",
     ("game", "gaming", "other games", "minecraft", "steam", "console",
      "playing", "co-op", "coop", "lobby"),
     {}, ("Street Corner", "Card Table", "The Games Room", "The Playhouse",
          "The Grand Arcade", "The Pleasure Gardens")),
    ("moot", "The Moot Hall", "⚖",
     "fa-scale-balanced",
     "hall",
     "scales",
     ("debate", "trivia", "quiz", "discussion", "argument", "philosoph",
      "politics", "serious", "topic"),
     {}, ("Soapbox", "Speaking Stone", "The Debating Room", "The Moot Hall",
          "The Forum", "The Great Assembly")),
    ("menagerie", "The Menagerie", "🦜",
     "fa-paw",
     "pen",
     "paw",
     ("pet", "cat", "dog", "animal", "creature", "critter", "mount", "paw"),
     {"image": 2.0}, ("Mud Paddock", "Animal Pens", "The Stables",
                      "Exotic Menagerie", "The Aviary", "Gilded Sanctuary")),
    ("gallery", "The Gallery", "🖼",
     "fa-image",
     "hall",
     "image",
     ("photo", "picture", "screenshot", "art", "gallery", "media", "showcase",
      "landscape", "shot"),
     {"image": 2.5}, ("Chalk Wall", "Pinned Sketches", "The Long Corridor",
                      "The Salon", "The Exhibition", "Hall of Wonders")),
    ("portraits", "The Portrait Hall", "🪞",
     "fa-camera-retro",
     "hall",
     "camera",
     ("selfie", "face", "irl", "us", "yourself", "mirror", "fit", "fashion",
      "outfit"),
     {"image": 2.5}, ("Small Mirror", "Sketch Corner", "The Sitting Room",
                      "The Portrait Hall", "The Gallery of Faces",
                      "Hall of a Thousand Faces")),
    ("bakery", "The Bakery", "🍞",
     "fa-bread-slice",
     "inn",
     "bread",
     ("food", "cook", "recipe", "bake", "kitchen", "meal", "eat", "coffee",
      "tea", "snack"),
     {"image": 2.0}, ("Cold Hearth", "Bread Oven", "The Bakehouse",
                      "The Kitchens", "The Banquet Hall", "The Endless Feast")),
    ("workshop", "The Clockwork Workshop", "⚙",
     "fa-gear",
     "works",
     "gear",
     ("cod", "dev", "program", "tech", "software", "script", "addon", "bot",
      "engineer", "hardware", "linux"),
     {}, ("Workbench", "Tinker's Shed", "The Workshop", "The Manufactory",
          "The Clockwork Hall", "The Engine of Making")),
    ("sanctuary", "The Sanctuary", "🕯",
     "fa-dove",
     "chapel",
     "dove",
     ("safe", "vent", "support", "mental", "health", "quiet", "comfort",
      "kind", "care"),
     {}, ("Wayside Stone", "Small Shrine", "The Chapel", "The Sanctuary",
          "The Temple", "The Still Heart")),
    ("undercroft", "The Undercroft", "🕶",
     "fa-wine-bottle",
     "keep",
     "bottle",
     ("degen", "lair", "unmoderated", "nsfw", "cursed", "gremlin", "chaos",
      "basement", "dungeon", "unhinged"),
     {}, ("Cellar Door", "Back Room", "The Speakeasy", "The Undercroft",
          "The Deep Cellars", "The Unlit Halls")),
    # The statue is fed by bot commands, which are counted wherever they happen
    # rather than by room. Its hints still match a bot channel so that ordinary
    # chatter in there builds something, but the statue grows either way.
    ("statue", "The Dodo Statue", "🗿",
     "fa-monument",
     "monument",
     "monument",
     ("bot", "command", "dodo", "casino", "gamble", "playground", "minigame"),
     {"command_used": 2.0},
     ("Odd Boulder", "Carved Stone", "The Little Dodo", "The Dodo Statue",
      "The Gilded Dodo", "The Colossus of Dodo")),
    ("wayshrine", "The Wayshrine", "🚪",
     "fa-door-open",
     "gate",
     "door",
     ("welcome", "introduction", "intro", "arrival", "rules", "gate", "hello",
      "newcomer", "start", "lobby"),
     {}, ("Boundary Post", "Traveller's Marker", "The Gatehouse",
          "The Wayshrine", "The Great Gate", "Threshold of the World")),
)


def default_buildings() -> list[dict]:
    """A town's worth of buildings, with no channels attached.

    Deliberately unattached: a building that silently counts every room is a
    building nobody configured. "Suggest from channel names" fills them in from
    the server's actual rooms, which is better than a guess made by somebody who
    has never seen the server. Every name here is meant to be rewritten.
    """
    return [
        {"key": key, "name": name, "icon": icon, "fa": fa, "shape": shape,
         "symbol": symbol, "channels": {}, "metric_weights": dict(weights),
         "hints": list(hints), "tiers": _tier_set(titles)}
        for key, name, icon, fa, shape, symbol, hints, weights, titles in _DEFAULT_SET
    ]


def suggest_channels(guild, buildings: list[dict]) -> list[dict]:
    """Attach each building to the channels whose names look like it.

    Only ever fills in buildings that have **no** channels yet, so pressing it
    again after hand-tuning cannot undo the tuning.

    A room *may* feed more than one building — that is a deliberate allowance,
    because a busy general channel really is both the tavern and somewhere else.
    The suggester still hands each room to a single building, because a guess
    that quietly double-counted would be a bad guess; sharing a room is a choice
    somebody makes on purpose, in the editor.

    Matching is on the channel name alone. It is a starting guess and is meant
    to be corrected, which is the same bargain "Suggest from role names" makes
    on the trials page.
    """
    hints_for = {key: hints
                 for key, _n, _i, _f, _s, _y, hints, _w, _t in _DEFAULT_SET}
    claimed: set[int] = {int(cid) for building in buildings
                         for cid in (building.get("channels") or {})}
    out = []
    for building in buildings:
        building = dict(building)
        if building.get("channels"):
            out.append(building)
            continue
        hints = building.get("hints") or hints_for.get(building.get("key")) or []
        found: dict[str, float] = {}
        for channel in getattr(guild, "channels", []):
            channel_id = int(getattr(channel, "id", 0) or 0)
            name = str(getattr(channel, "name", "") or "").lower()
            if not channel_id or channel_id in claimed or not name:
                continue
            # The category counts as part of the name, so a hint can match a
            # whole section of the server rather than one room at a time. That
            # is how servers are actually organised, and it is far more reliable
            # than guessing at individual channel names.
            category = getattr(channel, "category", None)
            haystack = name
            if category is not None and getattr(category, "name", None):
                haystack = f"{str(category.name).lower()}/{name}"
            if any(hint in haystack for hint in hints):
                found[str(channel_id)] = 1.0
                claimed.add(channel_id)
        building["channels"] = found
        out.append(building)
    return out


# --------------------------------------------------------------------------- #
#  Store
# --------------------------------------------------------------------------- #
class BuildingStore:
    """The per-guild DodoLand configuration document.

    One row per guild, holding the buildings and (later) the map. Reads are
    cached per guild and dropped on write, the same approach the rest of the
    bot's per-guild config uses.
    """

    def __init__(self, collection) -> None:
        self._col = collection
        self._cache: dict[int, dict] = {}

    def config(self, guild_id: int) -> dict:
        guild_id = int(guild_id)
        if guild_id not in self._cache:
            doc = self._col.find_one({"_id": guild_id}) or {}
            self._cache[guild_id] = doc
        return self._cache[guild_id]

    def buildings(self, guild_id: int) -> list[dict]:
        """This guild's buildings, or the unattached defaults if none are set.

        Rows saved before a field existed are filled in from the defaults by
        key, on read. Every building on this server was stored before there was
        an icon class, so without this they all drew as the same generic house
        and a town was a row of identical huts. Migrating on read rather than
        with a script means a server that has not been opened since is fixed the
        moment somebody looks at it.
        """
        stored = self.config(guild_id).get("buildings")
        if not stored:
            return default_buildings()
        fallback = {b["key"]: b for b in default_buildings()}
        out = []
        for building in stored:
            building = dict(building)
            base = fallback.get(building.get("key"), {})
            if not building.get("fa"):
                building["fa"] = base.get("fa") or "fa-house"
            if not building.get("shape"):
                from helpers.dodoland import townart
                building["shape"] = base.get("shape") or townart.DEFAULT_SHAPE
            if not building.get("symbol"):
                building["symbol"] = base.get("symbol") or ""
            if not building.get("hints"):
                building["hints"] = list(base.get("hints") or [])
            out.append(building)
        return out

    def is_configured(self, guild_id: int) -> bool:
        """Whether anybody has saved buildings, as opposed to seeing defaults."""
        return bool(self.config(guild_id).get("buildings"))

    def invalidate(self, guild_id: Optional[int] = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(int(guild_id), None)

    def map_image(self, guild_id: int) -> Optional[dict]:
        """The uploaded base map, or ``None`` if this server has not set one."""
        return self.config(guild_id).get("map") or None

    def save_map(self, guild_id: int, image: Optional[dict]) -> None:
        """Store or clear the base map. ``None`` removes it."""
        guild_id = int(guild_id)
        if image is None:
            self._col.update_one({"_id": guild_id}, {"$unset": {"map": ""}}, upsert=True)
        else:
            self._col.update_one({"_id": guild_id}, {"$set": {"map": image}}, upsert=True)
        self.invalidate(guild_id)

    def plots(self, guild_id: int) -> dict[int, dict]:
        """``{user_id: {x, y}}`` — where people have settled, in map percentages.

        Percentages rather than pixels so replacing the base image with a
        redrawn one of a different size does not move everybody's town.
        """
        return {int(k): v for k, v in (self.config(guild_id).get("plots") or {}).items()}

    def settle(self, guild_id: int, user_id: int, x: float, y: float) -> dict:
        """Claim a plot. Re-settling moves the town rather than making a second."""
        spot = {"x": round(max(0.0, min(100.0, float(x))), 3),
                "y": round(max(0.0, min(100.0, float(y))), 3)}
        self._col.update_one({"_id": int(guild_id)},
                             {"$set": {f"plots.{int(user_id)}": spot}}, upsert=True)
        self.invalidate(guild_id)
        return spot

    def unsettle(self, guild_id: int, user_id: int) -> None:
        """Take a town off the map. Nothing it earned is touched.

        A town's position and a town's standing have never had anything to do
        with each other, so this is only ever a change of scenery.
        """
        self._col.update_one({"_id": int(guild_id)},
                             {"$unset": {f"plots.{int(user_id)}": ""}})
        self.invalidate(guild_id)

    def clear_plots(self, guild_id: int) -> int:
        """Empty the map. Returns how many towns were on it."""
        count = len(self.plots(guild_id))
        self._col.update_one({"_id": int(guild_id)}, {"$set": {"plots": {}}},
                             upsert=True)
        self.invalidate(guild_id)
        return count

    def reset_shapes(self, guild_id: int, *, symbols: bool = False) -> list[dict]:
        """Put every building back to the shape its key was designed with.

        Only touches ``shape`` (and ``symbol`` when asked): rooms, tiers,
        weights, names and everything else are left exactly as they are, because
        this is repairing a drawing mistake and not resetting a server.

        A key that is not one of the built-in defaults is left alone — there is
        nothing to put it back *to*, and guessing would be worse than the thing
        being wrong.

        Returns ``[{key, from, to}]`` for what actually changed, so the panel
        can say what it did rather than claiming success.
        """
        stored = (self.config(guild_id).get("buildings") or [])
        if not stored:
            return []
        known = {spec[0]: spec for spec in _DEFAULT_SET}
        changed = []
        out = []
        for building in stored:
            building = dict(building)
            key = str(building.get("key") or "")
            spec = known.get(key)
            if spec is not None:
                if building.get("shape") != spec[4]:
                    changed.append({"key": key, "from": building.get("shape") or "",
                                    "to": spec[4]})
                    building["shape"] = spec[4]
                if symbols and not building.get("symbol"):
                    building["symbol"] = spec[5]
            out.append(building)
        if changed:
            self._col.update_one({"_id": int(guild_id)},
                                 {"$set": {"buildings": out}}, upsert=True)
            self.invalidate(guild_id)
        return changed

    def save_buildings(self, guild_id: int, value: Any, *, guild=None) -> list[dict]:
        buildings = validate_buildings(value, guild=guild)
        self._col.update_one({"_id": int(guild_id)},
                             {"$set": {"buildings": buildings}}, upsert=True)
        self.invalidate(guild_id)
        return buildings
