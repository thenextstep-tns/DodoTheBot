"""DodoLand: breadth — taking part across the server, rewarded in influence.

A lively room for somebody is one where enough *other* people wrote; breadth is
the share of those they wrote in themselves; it multiplies town power for reach
only, and the strongest town still reaches no further than the top setting.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from helpers.dodoland import breadth as B  # noqa: E402
from helpers.dodoland import influence as I  # noqa: E402


def day(user, **rooms):
    return {"user_id": user, "channels": {str(c): {"message": n} for c, n in rooms.items()}}


# Rooms 1-4 are lively (three people each); room 5 is one person talking alone.
rows = [day(1, **{"1": 3, "2": 2, "3": 1, "4": 1}),
        day(2, **{"1": 1, "2": 1, "3": 1, "4": 1, "5": 9}),
        day(3, **{"1": 1, "2": 1, "3": 1, "4": 1}),
        day(4, **{"1": 5}),
        {"user_id": 5, "channels": {"2": {"mention_received": 4}}}]   # being pinged is not writing
rooms = B.talkers(rows)
assert set(rooms) == {1, 2, 3, 4, 5} and 5 not in rooms[2], rooms
everywhere = B.share(1, rooms)
one_room = B.share(4, rooms)
assert everywhere == {"joined": 4, "open": 4, "share": 1.0}, everywhere
assert one_room["joined"] == 1 and one_room["open"] == 4 and one_room["share"] == 0.25, one_room
assert B.share(2, rooms)["open"] == 4, "a room only one person talks in counted as lively"
print("breadth         lively rooms need other people; writing there is taking part")

# A cap reached still means somebody wrote: a zero day count is one message.
assert B.talkers([day(7, **{"9": 0})]) == {9: {7: 1}}
# The rooms one may not write in are not held against anyone.
assert B.share(4, rooms, may_write=lambda u, r: r == 1)["open"] == 1
# Too few lively rooms is no breadth at all.
assert B.share(4, rooms, may_write=lambda u, r: r == 1)["share"] == 0.0
# One message is not taking part when the setting asks for more.
assert B.share(1, rooms, min_messages=2)["joined"] == 2
# Channels that are gone are dropped; a forum's posts fold into the forum.
folded = B.talkers([day(1, **{"10": 1, "11": 1, "12": 1})],
                   room=lambda c: None if c == 12 else 100)
assert folded == {100: {1: 2}}, folded
print("breadth         caps, rooms one cannot write in, gone channels and forums")

# The boost: 1 + bonus x share ^ curve; nothing at bonus 0 or no breadth.
assert B.boost(1.0, 1.0) == 2.0 and B.boost(0.5, 1.0) == 1.5
assert B.boost(0.25, 1.0, 0.5) == 1.5, "a curve below 1 rewards the first rooms more"
assert B.boost(0.7, 0.0) == 1.0 and B.boost(0.0, 3.0) == 1.0
print("breadth         the boost follows bonus and curve; 0 is off")

# For reach, the boosted strongest sets the scale: nobody passes the top.
powers = {"wide": 100 * B.boost(1.0, 1.0), "narrow": 150 * B.boost(0.2, 1.0)}
strongest = max([150.0] + list(powers.values()))
assert I.reach(powers["wide"], strongest, 5, 40) == 40
assert I.reach(powers["narrow"], strongest, 5, 40) < 40
print("breadth         a wide town of less power can out-reach a narrow one, never past the top")

print("PASS")
