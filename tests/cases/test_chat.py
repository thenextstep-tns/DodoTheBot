"""Dodo's chat mind: the parts that decide without asking a model.

Everything here runs on every message in every server, so the properties worth
protecting are the cheap ones — that state decays without a scheduler, that a
trigger can be felt without being answered, that a repeated bit wears out, and
that the prompt no longer asks the model to hand back the whole memory.
"""
import pathlib
import sys
from random import Random

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from helpers.chat import dial as dial_model
from helpers.chat import prompt as prompt_model
from helpers.chat import router as router_model
from helpers.chat import state as state_model
from helpers.chat import triggers as trigger_model

HOUR = 3600.0
DAY = 86400.0
NOW = 1_700_000_000.0
tuning = state_model.Tuning()


# --------------------------------------------------------------------------- #
#  State: decay happens on read, never on a timer
# --------------------------------------------------------------------------- #
old = {"relationship": 900, "relationship_at": NOW - 10 * DAY, "last_seen": NOW - 10 * DAY}
cooled = state_model.from_document(old, "1", tuning, now=NOW)
assert cooled.affinity == 900 - int(tuning.affinity_drift_per_day * 10), \
    f"affinity did not drift: {cooled.affinity}"
assert cooled.affinity > tuning.affinity_default, "drift overshot past neutral"
print("state           affinity drifts toward neutral over days")

frozen = state_model.from_document(old, "1", state_model.Tuning(affinity_drift_per_day=0), now=NOW)
assert frozen.affinity == 900, "drift 0 should freeze the relationship exactly"
print("state           drift 0 freezes relationships")

sour = {"relationship": 100, "relationship_at": NOW - 400 * DAY}
recovered = state_model.from_document(sour, "1", tuning, now=NOW)
assert recovered.affinity == tuning.affinity_default, "drift should stop at neutral, not cross it"
print("state           drift stops at neutral from below too")

# The legacy blob becomes fact zero, so nothing stored today is lost.
migrated = state_model.from_document({"memory": "plays healer; hates mushrooms"}, "2", tuning, now=NOW)
assert [f["text"] for f in migrated.facts] == ["plays healer; hates mushrooms"], migrated.facts
blank = state_model.from_document({"memory": "No memories yet."}, "3", tuning, now=NOW)
assert blank.facts == [], "the old placeholder should not become a memory"
print("state           legacy memory blob migrates, placeholder does not")

# Grudges fade; kindness ends them immediately.
angry = state_model.ChatState(user_id="4")
angry.add_grudge(tuning, "called you a pigeon", 0.8, now=NOW)
assert angry.top_grudge()["text"] == "called you a pigeon"
faded = state_model.from_document(
    {"grudges": angry.grudges}, "4", tuning, now=NOW + 40 * HOUR)
assert faded.grudges == [], "a grudge should not outlive five half-lives"
angry.forgive()
assert angry.top_grudge() is None, "kindness must clear grudges"
print("state           grudges fade on a half-life and kindness clears them")

# Facts are reinforced rather than duplicated, and the cap drops the weakest.
keen = state_model.ChatState(user_id="5")
keen.add_fact(tuning, "plays healer", now=NOW)
keen.add_fact(tuning, "Plays Healer", now=NOW)
assert len(keen.facts) == 1 and keen.facts[0]["hits"] == 2, keen.facts
small = state_model.Tuning(facts_max=2, facts_recall=2)
for index in range(5):
    keen.add_fact(small, f"fact {index}", now=NOW)
assert len(keen.facts) == 2, f"fact cap not enforced: {len(keen.facts)}"
assert "plays healer" in keen.recall_facts(small), "the reinforced fact should survive the cull"
print("state           facts reinforce instead of duplicating, cap keeps the strongest")

# Fatigue is stored decayed, so it never needs a sweep.
worn = state_model.ChatState(user_id="6")
for _ in range(3):
    worn.bump_fatigue(tuning, "banter", now=NOW)
assert abs(worn.fatigue_of("banter", tuning, now=NOW) - 3.0) < 1e-6
later = worn.fatigue_of("banter", tuning, now=NOW + 45 * 60)
assert abs(later - 1.5) < 1e-6, f"one half-life should halve fatigue, got {later}"
print("state           trigger fatigue decays on its own half-life")


# --------------------------------------------------------------------------- #
#  Triggers: literal text, whole words, first match wins
# --------------------------------------------------------------------------- #
banter = trigger_model.Trigger({
    trigger_model.K_NAME: "banter",
    trigger_model.K_PATTERNS: ["no u", "cope"],
    trigger_model.K_CHANCE: 1.0,
})
assert banter.matches("no u") and banter.matches("NO U, bird")
assert not banter.matches("copenhagen"), "whole-word matching should not fire inside a word"
print("triggers        literal phrases match on whole words, case-insensitively")

punct = trigger_model.Trigger({trigger_model.K_PATTERNS: [":)", "c++"]})
assert punct.matches("well :) then"), "punctuation-only patterns must still match"
print("triggers        punctuation patterns survive the word-boundary wrapper")

cleaned = trigger_model._clean({
    trigger_model.K_SPICE: 99, trigger_model.K_CHANCE: "2.5",
    trigger_model.K_AFFINITY: "-8", trigger_model.K_PATTERNS: "a\n\nb\n",
})
assert cleaned[trigger_model.K_SPICE] == trigger_model.SPICE_MAX, "spice should clamp, not reject"
assert cleaned[trigger_model.K_CHANCE] == 1.0, "chance should clamp to 1"
assert cleaned[trigger_model.K_AFFINITY] == -8
assert cleaned[trigger_model.K_PATTERNS] == ["a", "b"], "blank lines should be dropped"
partial = trigger_model._clean({trigger_model.K_ENABLED: False}, partial=True)
assert partial == {trigger_model.K_ENABLED: False}, \
    f"a partial edit must not blank other fields: {partial}"
print("triggers        panel values clamp, and a partial edit touches only its own field")

assert all(spec.get(trigger_model.K_NAME) for spec in trigger_model.DEFAULT_TRIGGERS)
assert any(spec.get(trigger_model.K_FORGIVES) for spec in trigger_model.DEFAULT_TRIGGERS), \
    "some default trigger has to be the one that clears grudges"
print("triggers        the shipped defaults are complete")


# --------------------------------------------------------------------------- #
#  Router: noticing without speaking, and speaking without being asked
# --------------------------------------------------------------------------- #
router = router_model.Router()
rt = router_model.RouterTuning(user_cooldown_seconds=0, spontaneous_chance=0)

seen = router.decide(addressed=True, trigger=None, guild_id=1, channel_id=2, user_id=3,
                     tuning=rt, rng=Random(0), now=NOW)
assert seen.route == router_model.ENGAGE, "a direct address is always answered"

quiet = trigger_model.Trigger({trigger_model.K_PATTERNS: ["x"], trigger_model.K_CHANCE: 0.0})
noticed = router.decide(addressed=False, trigger=quiet, guild_id=1, channel_id=2, user_id=3,
                        tuning=rt, rng=Random(0), now=NOW)
assert noticed.route == router_model.IGNORE and noticed.trigger is quiet, \
    "chance 0 must still hand the trigger back so its feelings land"
print("router          addressed always answers; chance 0 notices in silence")

canned = trigger_model.Trigger({
    trigger_model.K_PATTERNS: ["x"], trigger_model.K_CHANCE: 1.0,
    trigger_model.K_REFLEX: ["no u"], trigger_model.K_REFLEX_CHANCE: 1.0,
})
reflex = router.decide(addressed=False, trigger=canned, guild_id=1, channel_id=9, user_id=3,
                       tuning=rt, rng=Random(0), now=NOW)
assert reflex.route == router_model.REFLEX and not reflex.costs_tokens, \
    "a canned line must not reach the model"
print("router          canned trigger lines cost no tokens")

capped = router_model.RouterTuning(user_cooldown_seconds=0, daily_cap=1)
router.note_call(1, now=NOW)
blocked = router.decide(addressed=True, trigger=None, guild_id=1, channel_id=2, user_id=3,
                        tuning=capped, rng=Random(0), now=NOW)
assert blocked.route == router_model.IGNORE and blocked.reason == router_model.R_CAPPED
still = router.decide(addressed=False, trigger=canned, guild_id=1, channel_id=11, user_id=3,
                      tuning=capped, rng=Random(0), now=NOW)
assert still.route == router_model.REFLEX, "canned lines should survive the daily cap"
print("router          the daily cap stops model calls but not free ones")

# Butting in needs an actual conversation: several messages, more than one voice.
loud = router_model.Router()
chatty = router_model.RouterTuning(spontaneous_chance=1.0, spontaneous_min_messages=3,
                                   spontaneous_min_speakers=2, ambient_cooldown_seconds=0)
for index in range(4):
    loud.observe(7, "Ada", f"line {index}")
alone = loud.decide(addressed=False, trigger=None, guild_id=1, channel_id=7, user_id=3,
                    tuning=chatty, rng=Random(0), now=NOW)
assert alone.route == router_model.IGNORE and alone.reason == router_model.R_QUIET, \
    "she should not interrupt one person thinking out loud"
loud.observe(7, "Bo", "and another")
joined = loud.decide(addressed=False, trigger=None, guild_id=1, channel_id=7, user_id=3,
                     tuning=chatty, rng=Random(0), now=NOW)
assert joined.route == router_model.SPONTANEOUS, f"expected a butt-in, got {joined.reason}"
loud.note_unprompted(7, now=NOW)
again = loud.decide(addressed=False, trigger=None, guild_id=1, channel_id=7, user_id=3,
                    tuning=chatty, rng=Random(0), now=NOW + 60)
assert again.route == router_model.IGNORE and again.reason == router_model.R_COOLDOWN, \
    "two uninvited contributions in a row is the failure mode"
print("router          butting in needs a real conversation and then goes quiet")

assert router_model.RouterTuning().spontaneous_chance <= 0.01, \
    "the shipped butt-in chance has to stay miniscule"
print("router          the default butt-in chance is tiny")


# --------------------------------------------------------------------------- #
#  Dial: a budget, not an adjective
# --------------------------------------------------------------------------- #
dt = dial_model.DialTuning(spice_jitter=0, obsession_chance=0)
close = state_model.ChatState(user_id="7", affinity=900, seen=50, familiarity=0.9)
distant = state_model.ChatState(user_id="8", affinity=100, seen=1)

warm = dial_model.compute(close, None, dt, rng=Random(0))
cold = dial_model.compute(distant, None, dt, rng=Random(0))
assert warm.spice > cold.spice, "she should be louder with friends than strangers"
assert warm.sentences > cold.sentences, "the budget should shape length too"
print("dial            closeness moves the flourish budget and the length with it")

link = dial_model.compute(close, None, dt, text="here https://example.com/x", rng=Random(0))
assert link.utility and link.spice <= 1, "a link is a link"
ask = dial_model.compute(close, None, dt, text="how do I get there",
                         utility_patterns=["how do i"], rng=Random(0))
assert ask.utility, "the server's own phrases should mark a real question"
print("dial            links and configured phrases drop her into answering mode")

hot = trigger_model.Trigger({trigger_model.K_SPICE: 3})
fresh = dial_model.compute(distant, hot, dt, rng=Random(0), fatigue=0)
tired = dial_model.compute(distant, hot, dt, rng=Random(0), fatigue=3)
assert tired.spice < fresh.spice, "the fourth 'no u' must be quieter than the first"
assert "pulled" in tired.line(), f"a worn bit should say so: {tired.line()}"
print("dial            a repeated bit loses its budget and admits it")

muted = dial_model.compute(close, hot, dial_model.DialTuning(spice_max=0, spice_jitter=0),
                           rng=Random(0))
assert muted.spice == 0, "a server should be able to turn the character off entirely"
print("dial            spice_max 0 gives a purely functional bot")

rotating = dial_model.DialTuning(spice_jitter=0, obsession_chance=1.0)
first = dial_model.compute(close, None, rotating, obsessions=["pigs", "the sea"],
                           obsession_rotate_hours=8, guild_id=0, now=NOW, rng=Random(0))
later = dial_model.compute(close, None, rotating, obsessions=["pigs", "the sea"],
                           obsession_rotate_hours=8, guild_id=0, now=NOW + 9 * HOUR, rng=Random(0))
assert first.obsession and first.obsession != later.obsession, "the obsession should rotate"
same = dial_model.compute(close, None, rotating, obsessions=["pigs", "the sea"],
                          obsession_rotate_hours=8, guild_id=0, now=NOW + 600, rng=Random(0))
assert same.obsession == first.obsession, "it must hold steady inside one conversation"
print("dial            the obsession holds all day and has moved by tomorrow")

assert not any("drows" in text.lower() for text in
               (pathlib.Path("cogs/chat.py").read_text(encoding="utf-8"),
                pathlib.Path("helpers/chat/dial.py").read_text(encoding="utf-8").replace(
                    "drowsiness per message", ""))), "drowsiness should be gone, not renamed"
print("dial            no per-message drowsiness roll survives")


# --------------------------------------------------------------------------- #
#  Prompt: short, and it never asks for the memory back
# --------------------------------------------------------------------------- #
rich = state_model.ChatState(user_id="9", affinity=780, seen=40, familiarity=0.6)
rich.add_fact(tuning, "plays healer", now=NOW)
rich.add_fact(tuning, "sister named Mo", now=NOW)
rich.add_grudge(tuning, "called you a pigeon", 0.9, now=NOW)
rich.add_rumour(tuning, "ate a whole cake", "12", "Bo")

built = prompt_model.build(
    persona="You are Dodo.", name="Ada", state=rich, tuning=tuning,
    dial=dial_model.compute(rich, None, dt, rng=Random(0)),
    others=[{"name": "Bo", "closeness": 0.5, "facts": ["tanks"]}],
)
assert "closeness 0.78" in built, built
assert "called you a pigeon" in built and "plays healer" in built and "ate a whole cake" in built
assert "0. Bo" in built, "rumour targets must be numbered for the model to point at one"
assert prompt_model.J_LEARNED in built and "null" in built
assert "updated_memory" not in built, "the old echo-the-whole-memory contract is gone"
print("prompt          state, grudges, facts and rumour targets all reach the model")

words = len(built.split())
assert words < 220, f"the assembled prompt has drifted long again: {words} words"
print(f"prompt          the whole system prompt is {words} words")

unprompted = prompt_model.build(
    persona="You are Dodo.", name="Ada", state=rich, tuning=tuning,
    dial=dial_model.compute(rich, None, dt, rng=Random(0)),
    recent=["Ada: hello", "Bo: hi"], unprompted=True,
)
assert "Nobody addressed you" in unprompted and "empty string" in unprompted, \
    "an uninvited turn must be allowed to say nothing"
assert "Ada: hello" in unprompted, "the recent conversation should be the context"
print("prompt          an uninvited turn gets context and permission to stay quiet")

stranger = prompt_model.state_block("Zip", state_model.ChatState(user_id="0"), tuning)
assert "never spoken before" in stranger, stranger
print("prompt          a stranger is described as one")

print("PASS")
