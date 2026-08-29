"""
Render the real map page to a file, with stub data, and open it in a browser.

The map is JavaScript — zooming, panning, culling, the card, the drawer — and
none of that is exercised by anything in the suite, which renders HTML and reads
it as text. The only place it has ever been clickable is a live server behind an
admin login, which is a slow and risky place to find out that a button does
nothing.

    py tools/dodoland_map_preview.py dodoland_map.html

The page it writes is the page ``web/dodoland/mappage.py`` produces, byte for
byte, against a fake guild with a generated base map. Nothing here reimplements
any of it.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))

import discord  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland.assets import AssetStore  # noqa: E402
from helpers.dodoland.buildings import BuildingStore  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.dodoland.decor import DecorStore  # noqa: E402
from helpers.dodoland.towns import TownStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import mappage  # noqa: E402
from web.dodoland.assets_route import draw_town  # noqa: E402

GUILD_ID = 42
ROOMS = {"help": 900, "fashion": 901, "crafting": 902, "raids": 903,
         "lore": 904, "voice-chat": 905}
BUILDINGS = [
    ("library", "The Grand Library", "\U0001F4DA", "hall", "book", "lore"),
    ("tavern", "The Leaky Dodo", "\U0001F37A", "inn", "mug", "help"),
    ("menagerie", "The Menagerie", "\U0001F99C", "pen", "paw", "fashion"),
    ("forge", "The Forge", "\U0001F525", "works", "gear", "crafting"),
    ("barracks", "The Barracks", "\U0001F6E1", "keep", "shield", "raids"),
    ("chapel", "The Quiet Room", "\U0001F54A", "chapel", "dove", "voice-chat"),
    ("stage", "The Playhouse", "\U0001F3AD", "stage", "masks", "fashion"),
]


class Channel(discord.TextChannel):
    category = None

    def __init__(self, cid, name):
        self.id, self.name, self.position = cid, name, 0


class Member:
    bot = False

    def __init__(self, uid, name):
        self.id, self.display_name, self.name = uid, name, name.lower()


class Role:
    def __init__(self, rid, name, colour_value):
        self.id, self.name = rid, name
        self.colour = type("C", (), {"value": colour_value})()


NAMES = ["Nik", "Rosa", "Fox", "Mira", "Ash", "Juno", "Vex", "Pim", "Tuli",
         "Orla", "Bram", "Kestrel", "Sable", "Wren", "Dodo", "Hex", "Nell",
         "Oz", "Pike", "Quill", "Rune", "Sage", "Thorn", "Umber"]


class Guild:
    name, id = "ESO for Dodos", GUILD_ID
    icon = None

    def __init__(self):
        self.members = [Member(i + 1, n) for i, n in enumerate(NAMES)]
        self.channels = [Channel(cid, n) for n, cid in ROOMS.items()]
        self.roles = [Role(70, "Legend", 0xFF6EC7), Role(71, "Godslayer", 0x9682FF),
                      Role(72, "Raider", 0x2F6FA8), Role(73, "Casual", 0x3F8F5E)]

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)


class Visibility:
    def feature_active(self, *a, **k):
        return True

    def cog_enabled(self, *a, **k):
        return True


class TrialRanks:
    """Four rungs, so the whole flourish ladder appears on one map."""

    def get(self, gid):
        return {"ranks": [{"role_id": 73, "min_points": 0, "name": "Casual"},
                          {"role_id": 72, "min_points": 50, "name": "Raider"},
                          {"role_id": 71, "min_points": 150, "name": "Godslayer"},
                          {"role_id": 70, "min_points": 400, "name": "Legend"}]}

    def standings(self, gid, limit=100):
        rng = random.Random(7)
        return [{"user_id": i + 1, "score": rng.choice([0, 20, 70, 200, 500])}
                for i in range(len(NAMES))]


class Bot:
    def __init__(self, guild):
        self.dodoland_params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
        self.dodoland = ActivityStore(FakeCollection(), FakeCollection(), self.dodoland_params)
        self.dodoland_buildings = BuildingStore(FakeCollection())
        self.dodoland_assets = AssetStore(FakeCollection())
        self.dodoland_towns = TownStore(FakeCollection())
        self.dodoland_decor = DecorStore(FakeCollection())
        self.visibility = Visibility()
        self.trial_ranks = TrialRanks()
        self._guild = guild

    def get_guild(self, gid):
        return self._guild

    def get_user(self, uid):
        return None


def _base_map(width=1600, height=1000) -> bytes:
    """A plausible continent, as an SVG. Not art — something to place towns on."""
    rng = random.Random(3)
    blobs = ""
    for _ in range(9):
        cx, cy = rng.uniform(0.2, 0.8) * width, rng.uniform(0.2, 0.8) * height
        blobs += (f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{rng.uniform(120, 340):.0f}" '
                  f'ry="{rng.uniform(90, 240):.0f}" fill="#cdba92"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
            f'<rect width="{width}" height="{height}" fill="#a8c4d8"/>'
            f'<g opacity=".95">{blobs}</g>'
            f'<text x="40" y="{height - 40}" font-size="34" fill="#7a674c" '
            f'font-family="Georgia,serif">a stand-in continent</text>'
            f'</svg>').encode("utf-8")


def build() -> str:
    guild = Guild()
    bot = Bot(guild)
    rng = random.Random(11)

    bot.dodoland_buildings.save_buildings(GUILD_ID, [
        {"key": key, "name": name, "icon": icon, "shape": shape, "symbol": symbol,
         "channels": {ROOMS[room]: 1.0}, "metric_weights": {},
         "tiers": [{"title": t, "percentile": p, "floor": f}
                   for t, p, f in (("Shed", 10, 1), ("Yard", 30, 20),
                                   ("House", 55, 60), ("Hall", 75, 140),
                                   ("Great hall", 90, 300), ("Wonder", 97, 600))]}
        for key, name, icon, shape, symbol, room in BUILDINGS
    ], guild=guild)

    # A believable spread: a couple of giants, a middle, a long tail.
    for member in guild.members:
        weight = rng.choice([1, 1, 2, 3, 5, 9, 20, 40])
        for room_id in ROOMS.values():
            for _ in range(rng.randint(0, weight * 4)):
                bot.dodoland.record(GUILD_ID, member.id, "message", channel_id=room_id)
        for other in rng.sample(guild.members, rng.randint(1, min(12, weight + 2))):
            if other.id != member.id:
                bot.dodoland.record(GUILD_ID, member.id, "mention_given",
                                    channel_id=ROOMS["help"], partner_id=other.id)

    bot.dodoland_buildings.save_map(GUILD_ID, {
        "data": _base_map(), "content_type": "image/svg+xml",
        "width": 1600, "height": 1000})
    for member in guild.members:
        if rng.random() < 0.8:
            bot.dodoland_buildings.settle(GUILD_ID, member.id,
                                          rng.uniform(8, 92), rng.uniform(10, 88))
    # A few assets in the library, so the toolkit has something in it. Drawn
    # here rather than uploaded: the point is to exercise the placement, not the
    # upload path.
    for name, body in (
        ("Pine wood", '<circle cx="32" cy="26" r="18" fill="#2f7f52"/>'
                      '<rect x="28" y="40" width="8" height="20" fill="#7a5233"/>'),
        ("Mountain", '<polygon points="6,58 32,8 58,58" fill="#8d8577"/>'
                     '<polygon points="22,26 32,8 42,26" fill="#f2f0ea"/>'),
        ("Ruin", '<rect x="12" y="26" width="10" height="32" fill="#b9b1a2"/>'
                 '<rect x="30" y="16" width="10" height="42" fill="#b9b1a2"/>'
                 '<rect x="46" y="34" width="10" height="24" fill="#b9b1a2"/>'),
        ("Bonfire", '<polygon points="32,14 44,50 20,50" fill="#ff9a3c"/>'
                    '<ellipse cx="32" cy="52" rx="16" ry="5" fill="#6b4a30"/>'),
    ):
        bot.dodoland_assets.add(
            GUILD_ID, name=name,
            data=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                  f'{body}</svg>').encode("utf-8"),
            content_type="image/svg+xml")

    bot.dodoland_towns.save(GUILD_ID, 1, name="Beanburg",
                            blurb="Mostly soup, some regrets.")

    class Request(dict):
        def __init__(self, app):
            super().__init__()
            self.app = app

    request = Request({"bot": bot})
    request["guild"], request["scope"], request["uid"] = guild, "full", 1
    body = asyncio.run(mappage.map_page(request)).text

    # The art endpoint is not running here, so the fetch every town makes would
    # 404 and each settlement would stay an empty box. The drawings are made
    # with the same function the endpoint calls and handed to the page instead.
    art = {str(m.id): draw_town(bot, guild, m.id) for m in guild.members}
    return body, art


def main(argv: list[str]) -> int:
    target = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path("dodoland_map.html")
    body, art = build()
    body = body.replace(
        "fetch('/guild/' + D.gid + '/dodoland/town/' + person.id + '/art')",
        "Promise.resolve({ok: true, text: function () { "
        "return Promise.resolve(window.DLART[person.id] || ''); }})")
    # Before the page's own script, not after it. The stand-in resolves
    # immediately, so its `.then` runs as a microtask at the end of that script
    # — while a later `<script>` tag has not been parsed yet, and every town
    # came out empty.
    body = body.replace(
        "</script>\n<script>",
        f"</script>\n<script>window.DLART = {json.dumps(art)};</script>\n<script>",
        1)
    target.write_text(body, encoding="utf-8")
    print(f"wrote {target.resolve()}  ({len(art)} towns drawn)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
