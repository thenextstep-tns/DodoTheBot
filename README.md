# DodoTheBot

Dodo is the Discord bot of the **ESO for Dodos** community — a mix of moderation,
audit logging, and a big pile of games (cat/dog pets, skeevaton races, a pumpkin
deathmatch, fishing, a parse championship, DnD sessions, and plenty of silly
commands).

Built on **[discord.py](https://discordpy.readthedocs.io/) 2.x** with
**MongoDB** for persistence. All commands are hybrid — usable both as `/slash`
commands and with a text prefix.

## Requirements

- **Python 3.13** (3.9+ works; 3.13 is what the dev bot runs)
- A **MongoDB** database (Atlas or self-hosted)
- The **Tesseract OCR** binary on the host (only for the `pat` screenshot decoder)

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `config.json` in the project root (it is git-ignored — never commit it):

```json
{
  "prefix": ["Dodo ", "dodo "],
  "token": "YOUR_BOT_TOKEN",
  "application_id": "YOUR_APPLICATION_ID",
  "permissions": "YOUR_PERMISSIONS_INTEGER",
  "openai_api_key": "YOUR_OPENAI_KEY",
  "owners": [YOUR_USER_ID],
  "test_guild_id": YOUR_DEV_GUILD_ID
}
```

- `test_guild_id` (optional) syncs slash commands instantly to one guild for
  development; omit it to sync globally (can take up to an hour to propagate).
- Enable the **Message Content**, **Server Members**, and **Presence** privileged
  intents for the application in the Discord Developer Portal.
- Non-secret settings (channel/role IDs, game balance, the MongoDB URI) live in
  `config_py.py`. Add blacklisted user IDs to `blacklist.json`.

## Running

```bash
python bot.py
```

## Project layout

```
bot.py            # entry point: the DodoBot client, events, background tasks
config_py.py      # channel/role IDs, game constants, MongoDB collections
lang.py           # all user-facing strings, grouped by cog
cogs/             # one file per feature area, each a hybrid-command cog
helpers/          # shared utilities
  messages.py     #   embeds, sends, mentions, reaction/select prompts
  database.py     #   common MongoDB access patterns
  checks.py       #   command checks (owner, blacklist)
  logger.py       #   structured UTF-8 logging
exceptions.py     # custom error types
```

Cogs are loaded automatically from `cogs/` on startup; drop a new cog in with an
`async def setup(bot)` and it's picked up.
