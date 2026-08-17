# Tests

```bash
py -3 tests/run_tests.py             # everything
py -3 tests/run_tests.py wr tokens   # only cases matching these names
py -3 tests/run_tests.py -v          # show what each case checked
pytest tests/                        # if you have pytest; same cases
```

Nothing needs installing. The runner is stdlib-only because a suite you can't
run on the box is a suite nobody runs.

## Shape

Each file in `cases/` is a plain script that builds fake Discord objects,
asserts its way down the page, prints what it checked, and ends with `PASS`.
They run in separate processes from the repo root, so one crash can't take the
rest with it and the few cases that read source files find them.

That shape is deliberate but not sacred. It grew out of debugging sessions where
the fastest way to settle "does this actually do what I think" was a script that
printed the answer, and it kept that property: run one with `-v` and it tells you
what it verified, in order, in English.

## What they cover

| Case | What it protects |
|---|---|
| `ranks`, `wr`, `stale` | Scoring: ladders, world-record bonus, interest that expires as it's earned |
| `divider` | That moving a role divider changes **nothing** that scores |
| `apply`, `listener`, `auto`, `consent_paths` | Role application, hierarchy refusals, what gets logged, who gets asked |
| `presets`, `presetapi`, `tokens` | Write paths that have broken before, and capability-link security |
| `board`, `trials_page`, `dashboard`, `langpage`, `preview` | Rendering, and what must never leak into a page |
| `lang` | The string resolver's fallback chain and validation |
| `png`, `health`, `interest`, `detail`, `ttl`, `logchannel`, `rolelog` | The rest |
| `load` | That the cog actually loads into a real `commands.Bot` |

## If one fails

The runner prints the tail of the output, which is where the assertion is. Run
that case alone for the full story:

```bash
py -3 tests/cases/test_wr.py
```

## Adding one

Copy the shape of an existing case. Two rules learned the hard way:

- **Make the fake behave like the real thing.** Several bugs survived because a
  fake collection merged `$set` and `$setOnInsert` without complaint where Mongo
  refuses, or a fake `Guild` had no `.me`. A stub more forgiving than production
  is a test that agrees with broken code.
- **Assert the behaviour, not the wording.** Checking that a warning *exists* is
  durable; checking its exact sentence means every copy edit is a failing test.
