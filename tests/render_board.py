"""
Render the public leaderboard to ``.preview/`` so it can be opened on a phone.

The board is entirely client-side: the rows, the requirement lines, the expanded
breakdown and the compare panel are all built by ``board.js`` from a blob in the
page. Nothing in the test suite runs it, so this is how the layout gets looked
at — particularly on a narrow screen, where the fixed number columns once left
about twenty pixels for the player's name.

    py tests/render_board.py
    py -m http.server 8899 --directory .preview   ->  /board.html

The names are deliberately long: a fixture of three-letter nicknames cannot show
a truncation bug.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers.share_tokens import ShareTokenStore, KIND_PUBLIC  # noqa: E402
from web import routes  # noqa: E402

OUT = ".preview"


class Colour:
    def __init__(self, value):
        self.value = value


class Role:
    managed = False
    def __init__(self, rid, name, colour=0):
        self.id, self.name, self.position, self.colour = rid, name, 1, Colour(colour)
    def is_default(self):
        return False


class Member:
    bot = False
    def __init__(self, uid, name, roles):
        self.id, self.display_name, self.name, self.roles = uid, name, name.lower(), roles


class Guild:
    id, name = 783594413632520203, "ESO For Dodos"
    def __init__(self, roles, members):
        self.roles, self.members = roles, members
    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)


RANKS = [("Casual", 0, 0x95A5A6), ("Trialgoer", 40, 0x3498DB),
         ("Veteran", 120, 0x2ECC71), ("Master", 240, 0x9B59B6),
         ("Myth", 360, 0xE91E63)]
CLEARS = [("vAA", 1), ("vHRC HM", 4), ("vSS HM", 15), ("vRG HM", 25),
          ("vOC HM", 30), ("Godslayer", 30), ("Immortal Redeemer", 20),
          ("Tick-Tock Tormentor", 15), ("Master Angler", 20), ("vDSR HM", 27)]

ROLES = {}
for i, (name, _points, colour) in enumerate(RANKS):
    ROLES[name] = Role(900 + i, name, colour)
for i, (name, _points) in enumerate(CLEARS):
    ROLES[name] = Role(1000 + i, name)

# Long, real-shaped names. "Whippersnapper in Space" is the one that showed the
# bug: at 375px the name column had about twenty pixels to render it in.
NAMES = ["Whippersnapper in Space", "NornCat, the Queen of Nornia", "Dinogopher",
         "Mr. Tea and the Biscuits", "steppeswolf", "Gelthor the Unbroken",
         "damage_", "croat", "Yffilandaria Moonwhisper", "Sable", "Ace",
         "Pelle of the Northern Reach", "Quill", "Roka", "Tuck", "Vex",
         "Bram Stoker-Smythe", "Nixie", "Rosa", "Tomtem"]

MEMBERS = []
for i, name in enumerate(NAMES):
    # A descending spread of clears, so the board crosses every threshold.
    held = [ROLES[c] for c, _ in CLEARS[: max(1, len(CLEARS) - (i // 2))]]
    MEMBERS.append(Member(100000000000000000 + i, name, held))

guild = Guild(list(ROLES.values()), MEMBERS)
CONFIG = {
    "points": {str(ROLES[name].id): points for name, points in CLEARS},
    "trials": [],
    "ranks": [{"role_id": ROLES[name].id, "min_points": points, "name": name}
              for name, points, _c in RANKS],
}


class Col:
    def __init__(self):
        self.docs = []
    def create_index(self, *a, **k): pass
    def insert_one(self, d): self.docs.append(dict(d))
    def find_one(self, q):
        return next((d for d in self.docs
                     if all(d.get(k) == v for k, v in q.items())), None)
    def delete_many(self, q):
        keep = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
        removed = len(self.docs) - len(keep)
        self.docs = keep
        return type("R", (), {"deleted_count": removed})()


tokens = ShareTokenStore(Col())
token = tokens.issue(guild.id, kind=KIND_PUBLIC)


class Mgr:
    def get(self, gid): return CONFIG
    # A couple of record holders, so the medals and the bonus chip are on screen.
    def wr_all(self, gid):
        return {MEMBERS[0].id: {"current": 2, "former": 1},
                MEMBERS[3].id: {"current": 0, "former": 2}}
    def enrolled_ids(self, gid): return {m.id for m in MEMBERS}


class Bot:
    trial_ranks = Mgr()
    share_tokens = tokens
    def get_guild(self, gid): return guild if gid == guild.id else None


class Req:
    def __init__(self):
        self.match_info = {"gid": str(guild.id), "token": token}
        self.app = {"bot": Bot()}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    shutil.copytree("web/static", os.path.join(OUT, "static"), dirs_exist_ok=True)
    response = asyncio.run(routes.public_leaderboard(Req()))
    body = re.sub(r'(?<=")/static/', "static/", response.text)
    path = os.path.join(OUT, "board.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    print(f"wrote {path} with {len(MEMBERS)} players")
    print("py -m http.server 8899 --directory .preview  ->  /board.html")


if __name__ == "__main__":
    main()
