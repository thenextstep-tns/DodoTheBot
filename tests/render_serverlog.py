"""
Render the server log page to ``.preview/`` so the pickers can be **clicked**.

No test in this repo executes a page's JavaScript, and the multi-choice picker
is entirely JavaScript: chips, the type-ahead, backspace-to-remove, and the
hidden field that is the only thing the form actually submits. The assertions in
``tests/cases/test_serverlog.py`` prove the markup; they cannot prove the
control works. So after touching the picker, run this, open the page and use it.

    py tests/render_serverlog.py
    py -m http.server 8899 --directory .preview

The fixture is a guild with enough people and channels that filtering is a real
filter rather than a list of three.
"""

from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import panel_access  # noqa: E402
from web import routes  # noqa: E402

OUT = ".preview"


class Role:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class Member:
    bot = False
    def __init__(self, uid, name):
        self.id, self.display_name, self.name = uid, name, name.lower()


class Category:
    def __init__(self, name):
        self.name = name


class Channel:
    position = 0
    def __init__(self, cid, name, category=None):
        self.id, self.name, self.category = cid, name, category


class Thread:
    def __init__(self, tid, name):
        self.id, self.name = tid, name


NAMES = ["Mido", "Fox", "Rosa", "Tomtem", "Mr. Tea", "Gelthor", "croat", "Bram",
         "Ace", "Nixie", "Pelle", "Quill", "Roka", "Sable", "Tuck", "Vex"]
MEMBERS = [Member(100000000000000000 + i, n) for i, n in enumerate(NAMES)]
RAIDS = Category("Raids")
CHANNELS = [Channel(200000000000000000 + i, n, RAIDS if i % 2 else None)
            for i, n in enumerate(["general", "raids", "logs", "off-topic", "voice-chat"])]
THREADS = [Thread(300000000000000000, "vOC prog talk")]


class Guild:
    id, name = 783594413632520203, "ESO for Dodos"
    members, channels, threads = MEMBERS, CHANNELS, THREADS
    def get_member(self, i): return next((m for m in MEMBERS if m.id == int(i)), None)
    def get_role(self, i): return Role(int(i), "Legend")
    def get_channel_or_thread(self, i):
        return next((c for c in CHANNELS + THREADS if c.id == int(i)), None)


guild = Guild()
mido, fox = MEMBERS[0], MEMBERS[1]
general = CHANNELS[0]

DOCS = [
    {"_id": 3, "guild_id": guild.id, "event_type": "MESSAGE_DELETE",
     "timestamp": "2026-08-27T10:15:00+00:00",
     "description": f"\U0001f5d1 **<@{mido.id}>** (`{mido.id}`) message deleted "
                    f"in <#{general.id}> - <t:1756290000:f>",
     "fields": {"Content": "was this <@" + str(fox.id) + "> ok? <b>not markup</b>"},
     "user_ids": [mido.id, fox.id], "channel_ids": [general.id]},
    {"_id": 2, "guild_id": guild.id, "event_type": "MEMBER_ROLE_UPDATE",
     "timestamp": "2026-08-27T09:02:00+00:00",
     "description": f"\U0001f464 **<@{fox.id}>** (`{fox.id}`) roles updated "
                    f"by <@{mido.id}> - <t:1756290000:f>",
     "fields": {"Roles added": "<@&987654321098765432>"},
     "user_ids": [fox.id, mido.id], "channel_ids": []},
    {"_id": 1, "guild_id": guild.id, "event_type": "THREAD_CREATE",
     "timestamp": "2026-08-26T18:40:00+00:00",
     "description": f"\U0001f9f5 **Thread Created:** <#{THREADS[0].id}> (`vOC prog talk`)"
                    f"\n**Parent:** <#{general.id}>",
     "fields": {}, "user_ids": [], "channel_ids": [THREADS[0].id, general.id]},
]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    # The real stylesheet and script, so the preview is the page and not a
    # drawing of it. Copied rather than linked: Windows needs a privilege for
    # symlinks that a test script has no business asking for.
    shutil.copytree("web/static", os.path.join(OUT, "static"), dirs_exist_ok=True)

    data = {"rows": DOCS, "total": 412, "page": 2, "pages": 9}
    options = {"types": {"MESSAGE_DELETE": 210, "MESSAGE_EDIT": 88,
                         "MEMBER_ROLE_UPDATE": 74, "THREAD_CREATE": 12,
                         "MEMBER_JOIN": 28},
               "people": [999999999999999999], "channels": [888888888888888888]}
    chosen = {"type": "", "group": "", "user": [mido.id, fox.id],
              "channel": [general.id], "from": "2026-08-01", "to": ""}

    body = routes._server_log_html(None, guild, data, options, chosen)
    response = routes._page(f"{guild.name} · server log", body,
                            scope=panel_access.SCOPE_OWNER, guild=guild,
                            current="serverlog")
    path = os.path.join(OUT, "serverlog.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(response.text.replace('/static/', 'static/'))
    print(f"wrote {path}")
    print("py -m http.server 8899 --directory .preview  ->  /serverlog.html")


if __name__ == "__main__":
    main()
