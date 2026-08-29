"""
Run the Scrap lab on its own, without the bot.

The lab is almost entirely JavaScript talking to one endpoint, and no test in
this repo executes a page's JS — so a control wired to nothing would pass every
assertion in ``tests/cases/test_scrap.py`` and still be dead on the panel. This
serves the real page, the real stylesheet and the real engine on localhost so
you can click it.

    py tests/scrap_lab.py            # http://127.0.0.1:8898/scrap
                                     # http://127.0.0.1:8898/reactions

Auth is bypassed because there is nothing here to protect: no bot, no guild, and
the reaction grid is pointed at an in-memory store rather than the real
collection, so clicking around in here cannot write to anybody's server. It binds
to loopback only.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web  # noqa: E402

from helpers import reactions, scrap  # noqa: E402
from web import reactions_page, routes  # noqa: E402

HOST, PORT = "127.0.0.1", 8898


class FakeCollection:
    """Just enough pymongo for the reaction grid, held in memory."""

    def __init__(self):
        self.docs: list[dict] = []

    def _match(self, query, doc):
        for key, value in query.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def find(self, query):
        return [d for d in self.docs if self._match(query, d)]

    def delete_one(self, query):
        for doc in self.docs:
            if self._match(query, doc):
                self.docs.remove(doc)
                return

    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._match(query, doc):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(query)
            doc.update(update.get("$set", {}))
            self.docs.append(doc)


class FakeGuild:
    """A guild-shaped object with no Discord behind it."""
    id = 1
    name = "Scrap lab"
    emojis = ()


MEMORY = FakeCollection()
reactions._collection = lambda: MEMORY


async def page(request: web.Request) -> web.Response:
    return routes._page("Scrap lab", routes._scrap_html())


async def reactions_grid(request: web.Request) -> web.Response:
    """The reaction grid against the in-memory store."""
    guild = FakeGuild()
    params = {"group": (request.query.get("group") or "").strip(),
              "q": (request.query.get("q") or "").strip()}
    try:
        page_no = max(1, int(request.query.get("page", 1)))
    except (TypeError, ValueError):
        page_no = 1

    rows = reactions.catalogue(guild)
    groups = list(dict.fromkeys(r["group"] for r in rows))
    if params["group"]:
        rows = [r for r in rows if r["group"] == params["group"]]
    if params["q"]:
        needle = params["q"].casefold()
        rows = [r for r in rows if needle in r["name"].casefold() or needle == r["char"]]

    total = len(rows)
    pages = max(1, -(-total // reactions_page.PER_PAGE))
    page_no = min(page_no, pages)
    start = (page_no - 1) * reactions_page.PER_PAGE
    visible = rows[start:start + reactions_page.PER_PAGE]

    classes = routes._scrap_classes()
    grid = reactions.grid(guild.id, [r["char"] for r in visible], [c["key"] for c in classes])
    coverage = reactions.coverage(guild.id, len(reactions.catalogue(guild)), len(classes))
    body = reactions_page.render(guild, classes, visible, grid, groups,
                                 params, page_no, pages, total, coverage)
    return routes._page("Reaction grid", body)


async def save_reaction(request: web.Request) -> web.Response:
    data = await request.json()
    result = reactions.save(1, data.get("emoji"), data.get("cls"),
                            data.get("text"), data.get("stats") or {}, None)
    return web.json_response({"ok": True, **result})


async def simulate(request: web.Request) -> web.Response:
    """The same contract as the panel endpoint, minus the owner check."""
    data = await request.json()
    side_a, side_b = data.get("a") or [], data.get("b") or []
    if not side_a or not side_b:
        return web.json_response({"ok": False, "error": "Both sides need at least one cat."})

    tuning = {k: float(v) for k, v in (data.get("tuning") or {}).items() if v not in ("", None)}
    props = data.get("props") or {}
    batch = int(data.get("batch") or 0)

    if batch:
        tally, rounds_used = {"A": 0, "B": 0, "draw": 0}, 0
        for seed in range(batch):
            result = scrap.simulate(side_a, side_b, props=props, seed=seed, tuning=tuning)
            tally[result["winner"] or "draw"] += 1
            rounds_used += len(result["rounds"])
        return web.json_response({"ok": True, "batch": batch, "tally": tally,
                                  "avg_rounds": round(rounds_used / batch, 2)})

    seed = data.get("seed")
    result = scrap.simulate(side_a, side_b, props=props,
                            seed=int(seed) if seed not in ("", None) else None, tuning=tuning)
    result["ok"] = True
    result["prefight"] = {
        cat.get("name") or "cat": {"taunt": scrap.taunt_odds(cat, tuning), "psps": scrap.psps_odds(cat, tuning)}
        for cat in side_a + side_b
    }
    return web.json_response(result)


def main() -> None:
    app = web.Application()
    app.add_routes([
        web.get("/", page),
        web.get("/scrap", page),
        web.post("/api/scrap/simulate", simulate),
        web.get("/reactions", reactions_grid),
        web.post("/api/guild/1/reaction", save_reaction),
        web.static("/static", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")),
    ])
    print(f"Scrap lab:     http://{HOST}:{PORT}/scrap")
    print(f"Reaction grid: http://{HOST}:{PORT}/reactions")
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
