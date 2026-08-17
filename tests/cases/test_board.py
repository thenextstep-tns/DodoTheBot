"""The public board: enrolled only, token-gated, and unindexable."""
import asyncio, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers.share_tokens import ShareTokenStore, KIND_PUBLIC


class Colour:
    def __init__(s, v): s.value = v


class Role:
    managed = False
    def __init__(s, i, n, c=0): s.id, s.name, s.position, s.colour = i, n, 1, Colour(c)
    def is_default(s): return False


class Member:
    bot = False
    def __init__(s, i, n, roles): s.id, s.display_name, s.name, s.roles = i, n, n, roles


class Guild:
    id, name = 42, "ESO for Dodos"
    def __init__(s, r, m): s.roles, s.members = r, m
    def get_role(s, i): return next((x for x in s.roles if x.id == int(i)), None)


R = {"Legend": Role(100, "Legend", 0xE67E22), "vRG HM": Role(101, "vRG HM")}
rid = lambda n: R[n].id
people = [Member(1, "Mobi", [R["vRG HM"]]), Member(2, "Ghost", [R["vRG HM"]]),
          Member(3, "Bot", [])]
guild = Guild(list(R.values()), people)
CFG = {"points": {str(rid("vRG HM")): 25}, "trials": [],
       "ranks": [{"role_id": rid("Legend"), "min_points": 20, "name": "Legend"}]}


class Col:
    def __init__(s): s.docs = []
    def create_index(s, *a, **k): pass
    def insert_one(s, d): s.docs.append(dict(d))
    def find_one(s, q): return next((d for d in s.docs
                                     if all(d.get(k) == v for k, v in q.items())), None)
    def delete_many(s, q):
        keep = [d for d in s.docs if not all(d.get(k) == v for k, v in q.items())]
        n = len(s.docs) - len(keep); s.docs = keep
        return type("R", (), {"deleted_count": n})()


tokens = ShareTokenStore(Col())
token = tokens.issue(42, kind=KIND_PUBLIC)


class Mgr:
    def get(s, g): return CFG
    def wr_all(s, g): return {1: {"current": 1, "former": 0}}
    def enrolled_ids(s, g): return {1}          # only Mobi opted in


class Bot:
    trial_ranks = Mgr()
    share_tokens = tokens
    def get_guild(s, gid): return guild if gid == 42 else None


class Req:
    def __init__(s, gid, tok): s.match_info = {"gid": str(gid), "token": tok}; s.app = {"bot": Bot()}


ok = asyncio.run(routes.public_leaderboard(Req(42, token)))
print("status:", ok.status)
assert ok.status == 200
body = ok.text
# Rows are now drawn client-side from embedded data, so check that instead.
import json, re
payload = json.loads(re.search(r'id="board-data">(.*?)</script>', body, re.S).group(1))
names = [p["name"] for p in payload["players"]]
print("players:", names)
assert names == ["Mobi"], "only enrolled players are listed"
assert "1 player(s)" in body
mobi = payload["players"][0]
# 25 from the clear + 15 for the current record.
assert mobi["score"] == 40, mobi
assert mobi["rank"] == "Legend" and mobi["bonus"] == 15
assert mobi["colour"] == "#e67e22", "the rank badge borrows the role colour"
assert "vRG HM" in mobi["held"] and "vRG HM" in mobi["has"]
# Every earnable clear travels too, so a comparison can show what is missing.
assert [r["name"] for r in payload["roles"]] == ["vRG HM"], payload["roles"]
# Every role carries the trial it belongs to, so compare can group by raid.
assert payload["roles"][0]["group"] == "Achievements", payload["roles"][0]
assert mobi["wr"] is True, "the record-holder filter needs this flag"
for control in ('id="brank"', 'id="bach"', 'id="bwr"', 'id="bcompare"'):
    assert control in body, control
assert "board.js" in body and 'id="bsearch"' in body and 'id="bcompare"' in body
# The username travels for the second line under the display name.
assert mobi["tag"] == "Mobi", mobi
# Rank requirements, so the board can draw where each threshold falls. The
# bottom rung is excluded: nobody crosses a line at zero.
assert [(r["name"], r["points"]) for r in payload["ranks"]] == [("Legend", 20)], payload["ranks"]
# Columns are fixed so expanding a row cannot re-measure the table.
assert "<colgroup>" in body and "c-rank" in body
# Not indexable, and no referrer to leak the token out of the URL.
assert 'content="noindex, nofollow, noarchive"' in body
assert ok.headers["Referrer-Policy"] == "no-referrer"
assert ok.headers["X-Robots-Tag"].startswith("noindex")
assert ok.headers["Cache-Control"] == "no-store"
print("enrolled-only, bonus counted, noindex + no-referrer + no-store")

# Every wrong way in gives the same 404, revealing nothing.
for label, req in (("bad token", Req(42, token + "x")),
                   ("empty token", Req(42, "")),
                   ("wrong guild", Req(99, token))):
    resp = asyncio.run(routes.public_leaderboard(req))
    print(f"   {label:12} -> {resp.status} {resp.text!r}")
    assert resp.status == 404 and resp.text == "Not found."

# Revoking kills the live link.
tokens.revoke_all(42, kind=KIND_PUBLIC)
assert asyncio.run(routes.public_leaderboard(Req(42, token))).status == 404
print("revocation takes effect immediately")
print("PASS")
