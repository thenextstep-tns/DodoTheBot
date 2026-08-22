"""
Show what Dodo is actually being told, scenario by scenario — and optionally
what she says back.

The unit tests prove the machinery is correct. They cannot tell you whether the
character is any *good*, because that is a judgement call and it lives in prose:
the persona, the trigger notes, the dial line. This prints the real assembled
prompt for a set of representative situations so you can read them, edit
`chat_personality` or a trigger note, and run it again.

    py -3.13 tests/preview_chat.py              # the prompts, no API calls
    py -3.13 tests/preview_chat.py --live       # also ask the model and print replies
    py -3.13 tests/preview_chat.py --live xynode comfort   # only these scenarios

``--live`` reads the key from ``config.json`` (``PROXY_API``) and **spends real
money** — one call per scenario shown. Everything without it is free and offline.
"""

from __future__ import annotations

import json
import os
import sys
import time
from random import Random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import parameters                                    # noqa: E402
from helpers.chat import dial as dial_model                       # noqa: E402
from helpers.chat import prompt as prompt_model                   # noqa: E402
from helpers.chat import state as state_model                     # noqa: E402
from helpers.chat import triggers as trigger_model                # noqa: E402

GUILD = 424242424242424242
NOW = time.time()
RULE = "─" * 78


def param(key):
    """The shipped default for a parameter (this harness has no database)."""
    return next(spec for spec in parameters.PARAMETERS if spec["key"] == key)["default"]


def tuning() -> state_model.Tuning:
    return state_model.Tuning(
        affinity_default=param("chat_relationship_default"),
        first_impression_spread=param("chat_first_impression_spread"),
        facts_recall=param("chat_facts_recall"),
        rumours_recall=param("chat_rumours_recall"),
    )


def person(name, *, uid, affinity=None, seen=1, facts=(), grudge=None, rumours=()):
    """A user in whatever state the scenario needs."""
    tune = tuning()
    state = state_model.from_document(None, uid, tune, now=NOW)
    if affinity is not None:
        state.affinity = affinity
    state.seen = seen
    state.familiarity = min(1.0, seen * param("chat_familiarity_per_message"))
    for fact in facts:
        state.add_fact(tune, fact, now=NOW)
    if grudge:
        state.add_grudge(tune, grudge, 0.7, now=NOW)
    for text, source in rumours:
        state.add_rumour(tune, text, "0", source)
    return name, state


def find_trigger(name):
    spec = next((t for t in trigger_model.DEFAULT_TRIGGERS
                 if t[trigger_model.K_NAME] == name), None)
    return trigger_model.Trigger(spec) if spec else None


# --------------------------------------------------------------------------- #
#  The scenarios
# --------------------------------------------------------------------------- #
# Each: (label, who, what they said, trigger name or None, extra kwargs)
SCENARIOS = [
    ("stranger",
     person("Zip", uid="10", seen=0),
     "hey dodo what do you do", None, {}),

    ("praise",
     person("Ada", uid="11", affinity=760, seen=140,
            facts=["plays healer", "sister named Mo"], grudge="the insult thing"),
     "good bot, thank you dodo", "praise", {}),

    ("banter",
     person("Ada", uid="11", affinity=700, seen=140),
     "no u", "banter", {}),

    ("banter-worn",
     person("Ada", uid="11", affinity=700, seen=140),
     "no u", "banter", {"fatigue": 4}),

    ("xynode",
     person("Bo", uid="12", affinity=520, seen=30),
     "did you see xynode's new video", "nemesis", {}),

    ("insult",
     person("Cy", uid="13", affinity=430, seen=12),
     "bad bot", "insult", {}),

    ("comfort",
     person("Ada", uid="11", affinity=780, seen=140,
            facts=["plays healer", "works nights"]),
     "i feel like a total failure today, everything went wrong", "comfort", {}),

    ("extinction",
     person("Bo", uid="12", affinity=560, seen=30),
     "wait were dodos actually real or", "extinction", {}),

    ("existential",
     person("Cy", uid="13", affinity=500, seen=12),
     "you're just a bot though", "existential", {}),

    ("utility",
     person("Ada", uid="11", affinity=760, seen=140),
     "how do i get to the healer build page", None, {}),

    ("grudge-showing",
     person("Cy", uid="13", affinity=380, seen=12, grudge="the insult thing"),
     "anyway what's up", None, {}),

    ("rumour-target",
     person("Ada", uid="11", affinity=700, seen=140,
            rumours=[("once ate an entire cake alone", "Bo")]),
     "@Bo is lying about me", None, {"others": [
         {"name": "Bo", "closeness": 0.52, "facts": ["tanks", "always late"]}]}),

    ("uninvited",
     person("Ada", uid="11", affinity=700, seen=140),
     "", None, {"unprompted": True, "recent": [
         "Ada: honestly the patch made healing so much worse",
         "Bo: skill issue",
         "Ada: i will end you",
         "Bo: try it"]}),
]


def build_prompt(label, who, text, trigger_name, extra):
    name, state = who
    trigger = find_trigger(trigger_name) if trigger_name else None

    # The cog applies the trigger's feelings before it builds the prompt, so the
    # preview has to as well — otherwise "praise clears every grudge" shows a
    # grudge that would not actually be there.
    if trigger is not None:
        if trigger.forgives:
            state.forgive()
        if trigger.affinity:
            state.apply_sentiment(tuning(), trigger.affinity)
        if trigger.grudge:
            state.add_grudge(tuning(), f"the {trigger.name} thing", trigger.grudge, now=NOW)

    dial = dial_model.compute(
        state, trigger,
        dial_model.DialTuning(
            spice_base=param("chat_spice_base"),
            spice_max=param("chat_spice_max"),
            spice_jitter=param("chat_spice_jitter"),
            close_bonus_at=param("chat_close_bonus_at"),
            distant_penalty_at=param("chat_distant_penalty_at"),
            fatigue_bite=param("chat_fatigue_bite"),
            sentences_max=param("chat_reply_max_sentences"),
            obsession_chance=param("chat_obsession_chance"),
        ),
        text=text,
        utility_patterns=param("chat_utility_patterns"),
        obsessions=param("chat_obsessions"),
        obsession_rotate_hours=param("chat_obsession_rotate_hours"),
        guild_id=GUILD, now=NOW,
        rng=Random(sum(map(ord, label))),   # stable per scenario, so diffs are real
        fatigue=extra.get("fatigue", 0),
    )
    system = prompt_model.build(
        persona=param("chat_personality"),
        name=name, state=state, tuning=tuning(), dial=dial,
        others=extra.get("others"),
        recent=extra.get("recent"),
        unprompted=extra.get("unprompted", False),
    )
    return system, dial, trigger


def show(label, who, text, trigger_name, extra, client=None):
    name, _ = who
    system, dial, trigger = build_prompt(label, who, text, trigger_name, extra)

    print(f"\n{RULE}\n  {label.upper()}   —   {name} says: {text or '(nothing, she just joins in)'}")
    if trigger is not None:
        print(f"  trigger: {trigger.name}   ·   reply chance {trigger.chance}"
              f"   ·   canned {int(trigger.reflex_chance * 100)}% of the time")
    print(f"{RULE}\n{system}")

    if trigger is not None and trigger.reflex:
        print(f"\n  ── canned lines it might answer with instead (free) ──")
        for line in trigger.reflex[:4]:
            print(f"     {line}")

    if client is None:
        return
    reply = ask(client, system, text)
    print(f"\n  ── SHE SAYS ──\n     {reply}")


def ask(client, system, text):
    """One real call, formatted the way the cog does it."""
    try:
        completion = client.chat.completions.create(
            model=param("chat_model"),
            temperature=param("chat_temperature"),
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": text or "(nobody said anything to you)"}],
        )
        data = json.loads(completion.choices[0].message.content)
    except Exception as error:  # noqa: BLE001 - a preview must not crash on one bad call
        return f"[failed: {error}]"
    said = (data.get(prompt_model.J_SAY) or "").strip() or "[said nothing]"
    tail = []
    if data.get(prompt_model.J_FELT):
        tail.append(f"felt {data[prompt_model.J_FELT]:+}")
    if data.get(prompt_model.J_LEARNED):
        tail.append(f"learned: {data[prompt_model.J_LEARNED]}")
    return said + (f"\n     ({', '.join(tail)})" if tail else "")


def live_client():
    """A real client from config.json, or None with a reason printed."""
    try:
        from openai import OpenAI
        import config_py
    except ImportError as error:
        print(f"--live needs the bot's dependencies installed: {error}")
        return None
    key = getattr(config_py, "PROXY_API", None)
    if not key:
        print("--live found no PROXY_API key in config.json")
        return None
    return OpenAI(api_key=key, base_url=param("chat_base_url"))


def main(argv):
    live = "--live" in argv
    wanted = [a for a in argv if not a.startswith("-")]
    chosen = [s for s in SCENARIOS if not wanted or any(w in s[0] for w in wanted)]
    if not chosen:
        print(f"no scenario matched {wanted}; have: "
              f"{', '.join(s[0] for s in SCENARIOS)}")
        return 1

    client = live_client() if live else None
    if live and client is None:
        return 1
    if client is not None:
        print(f"!! live mode: {len(chosen)} real API calls\n")

    for scenario in chosen:
        show(*scenario, client=client)
    print(f"\n{RULE}\nEdit the persona in helpers/parameters.py (chat_personality) or a note in "
          f"helpers/chat/triggers.py, then run this again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
