"""
Who brought whom in.

Discord will not tell you which invite a member used. The only way to know is to
hold the guild's invite table, compare it after somebody joins, and see whose
use count went up. That is what this module does, and it is all it does: the
comparison is pure and testable, and the fetching lives in the cog.

Three ways it can legitimately fail to name anybody, all of which must be
silent rather than wrong:

* **No permission.** Reading invites needs Manage Guild. Without it the cache is
  empty and every join is simply unattributed.
* **A tie.** Two invites can gain a use between two fetches under load. Naming
  one of them at random would credit the wrong person for the most heavily
  weighted act in the system, so a tie credits nobody.
* **The vanity URL, or an invite created and used between fetches.** Nothing to
  compare against, so nothing is claimed.

Guessing here is worse than shrugging. ``member_recruited`` is weighted at sixty
because it is meant to be the hardest thing on the list to get by accident.
"""

from __future__ import annotations

from typing import Optional


def snapshot(invites) -> dict[str, int]:
    """``{invite code: uses}`` from whatever Discord handed back."""
    out: dict[str, int] = {}
    for invite in invites or ():
        code = getattr(invite, "code", None)
        if not code:
            continue
        out[str(code)] = int(getattr(invite, "uses", 0) or 0)
    return out


def inviter_ids(invites) -> dict[str, int]:
    """``{invite code: inviter user id}``, skipping invites with no known author."""
    out: dict[str, int] = {}
    for invite in invites or ():
        code = getattr(invite, "code", None)
        inviter = getattr(invite, "inviter", None)
        user_id = getattr(inviter, "id", None)
        if code and user_id:
            out[str(code)] = int(user_id)
    return out


def used_code(before: dict[str, int], after: dict[str, int]) -> Optional[str]:
    """Which invite gained a use, or ``None`` when that cannot be said.

    ``None`` covers all three ambiguous cases at once: nothing moved, more than
    one thing moved, or the code did not exist before. An unattributed join is
    correct; a misattributed one is not.
    """
    grew = [code for code, uses in (after or {}).items()
            if uses > (before or {}).get(code, 0) and code in (before or {})]
    if len(grew) != 1:
        return None
    return grew[0]


def recruiter_for(before: dict[str, int], after: dict[str, int],
                  inviters: dict[str, int], joiner_id: int) -> Optional[int]:
    """Who to credit for a join, or ``None`` if it cannot be established.

    Refuses to credit somebody for inviting themselves, which is what an alt
    account rejoining on its own link looks like.
    """
    code = used_code(before, after)
    if code is None:
        return None
    recruiter = (inviters or {}).get(code)
    if recruiter is None or int(recruiter) == int(joiner_id):
        return None
    return int(recruiter)
