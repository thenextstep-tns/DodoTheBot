# Monetization

"Completely tweakable and monetizeable" was a stated requirement. The enforcement
machinery mostly exists already — `helpers/visibility.py` notes that features are
individually toggleable "for monetization flexibility."

Note that inference is **local-only** (`08-LLM-LAYER.md` §2), so there is no
per-token cost to pass on. What is scarce here is *host capacity*, not money.

---

## 1. What is actually scarce

Price the things that cost money or that a serious GM feels the lack of:

| Scarce | Why | Cheap to meter |
| --- | --- | --- |
| **Model calls** | One inference host, serialized (`08-LLM-LAYER.md` §8) | Yes — `llm/budget.py` |
| **Simulation depth** | CPU on one core | Yes — tier caps |
| **Memory depth** | Storage + tick cost | Yes — budget multiplier |
| **Campaign count** | Storage (~7 MB each) | Yes |
| **Autonomous GM** | The premium capability | Yes — feature flag |
| **World continuity** | The headline feature | Yes — `dnd_world_tick` |

Deliberately **not** priced: number of players, dice rolls, character sheets,
sessions. Charging for those punishes the group for being popular, which kills the
word of mouth this product depends on.

## 2. Tiers

| | **Free** | **Table** | **Chronicle** |
| --- | --- | --- | --- |
| Campaigns | 1 | 3 | 12 |
| Ruleset | freeform | both | both + custom |
| Narration | Templates (`null`) | Model-rendered, 200 calls/day | Model-rendered, 1000/day |
| Queue priority | lowest | normal | high |
| Own Ollama host | ✅ (unmetered) | ✅ | ✅ |
| World tick | Off | On | On |
| Focus NPCs | 3 | 8 | 16 |
| Active NPCs | 20 | 200 | 1000 |
| Memory multiplier | 0.4× | 1.0× | 2.0× |
| Autonomous GM | — | — | ✅ |
| Canon auto-accept | — | ✅ | ✅ |
| Entity inspector | Basic | Full | Full + decision traces |
| Export | — | ✅ | ✅ |

Free must be **genuinely playable**, not a demo: freeform ruleset, real sheets,
real dice, memory, relationships, NPC decisions. What is missing is the world
*continuing* — which is exactly the thing worth paying for and the thing you can
only appreciate after you have played without it.

**Bring-your-own-Ollama is unmetered at every tier**, free included. It costs the
operator literally nothing — the inference happens on their machine — and it is
how the technically-inclined GMs who become evangelists get in. It is also a real
privacy claim no hosted competitor can make: with your own host, no player text
ever leaves your hardware.

## 3. Enforcement

Never scattered through the code. One module, `helpers/dnd/entitlements.py`:

```python
class Entitlements:
    def tier(self, guild_id: int) -> str: ...
    def limit(self, guild_id: int, key: str) -> int | float: ...
    def allows(self, guild_id: int, feature: str) -> bool: ...
    def check(self, guild_id: int, key: str, current: int) -> None:
        """Raise EntitlementError with an upgrade message, or return."""
```

Enforcement points:

- **Creation** — `check("campaigns", count)` before a new campaign.
- **Tick** — focus/active caps applied when promoting entity tiers.
- **Budget** — `08-LLM-LAYER.md` §7, degrading to `null` rather than blocking.
- **Features** — via the existing `bot.visibility.feature_active`, so tier changes
  and manual admin toggles use one code path.
- **Panel** — locked pages render as an upsell, not a 403.

**Rule: exceeding a limit degrades, never destroys.** Over the campaign cap →
existing campaigns become read-only, never deleted. Over budget → prose falls back
to templates, the game continues. Downgrade must be survivable, or churn becomes
data loss and support becomes a nightmare.

## 4. Billing

Deliberately out of scope for the first phases. When it lands:

- Stripe subscriptions keyed on `guild_id`; a `dnd_subscriptions` collection maps
  guild → tier → period.
- Grace period on payment failure: 7 days at tier, then degrade to free.
- Entitlements read from that collection, with the bot owner able to grant tiers
  manually (early adopters, friends, refunds).

Until then, `Entitlements` reads a manually-set tier from the owner panel. That is
enough to build and test every enforcement path without touching payments.

## 5. Import / export

A campaign is a JSON bundle: campaign doc, entities, knowledge, relations,
beliefs, imprinted memories, clocks, plus retained events and snapshots.

Why it matters commercially:

- **Kills the lock-in objection**, which is the first thing a serious GM asks.
- **Enables sharing** — a GM publishes a starting world; someone else imports it.
- **A marketplace** is the obvious next business: paid campaign settings, NPC
  packs, rulesets. The bundle format is the foundation, so it should be clean and
  versioned from the start even though the marketplace is far off.

Export is a paid feature; **import is free**, because import is acquisition.

## 6. What not to do

- **Don't meter dice rolls or messages.** Metering the core loop makes people play
  less, which makes them churn.
- **Don't cripple free into uselessness.** A free tier that cannot host a real
  campaign generates no evangelists.
- **Don't hide the entity inspector entirely** on free. It is the "oh, *that* is
  what this is" moment; show a basic version and gate the depth.
- **Don't charge per player.** Groups are the unit of virality.
