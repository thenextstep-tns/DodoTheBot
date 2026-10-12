# Control Panel — Setup Guide

Step-by-step to turn on the owner web control panel (guild list, cog load/reload/unload,
per-guild command visibility). The panel is **dormant until you configure it**, so nothing here
changes how the bot runs today.

There are two tracks — do **Track A** first to confirm it works on your own machine, then move to
**Track B** when you want to reach it from anywhere.

---

## What you'll end up with in `config.json`

A new `web` block (added alongside your existing keys like `token`, `owners`, `application_id`):

```json
"web": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 8080,
  "public_url": "http://localhost:8080",
  "client_id": "YOUR_APPLICATION_ID",
  "client_secret": "FROM_DISCORD_PORTAL",
  "session_secret": "A_LONG_RANDOM_STRING"
}
```

Keep `config.json` private — it already holds your bot token, and now the OAuth client secret too.

---

## Track A — Run it locally (do this first)

### 1. Confirm you're an owner
The panel only lets **bot owners** in. Your `config.json` `owners` list must contain your Discord
user ID (yours, `309719542115074049`, is already there). No action needed unless you want to add
more owners.

### 2. Open your Discord application
1. Go to **https://discord.com/developers/applications**
2. Click the application your bot already uses (the one whose ID is `application_id` in
   `config.json`). You do **not** need to create a new app — the bot *is* the app.

### 3. Copy the Client ID
- On the app's **General Information** page, copy the **Application ID**.
- This is the same value already in `config.json` as `application_id`, so you can reuse it — but
  it's fine to paste it into `client_id` explicitly.

### 4. Get the Client Secret
> **If you already have this secret saved** (env file, password manager, etc.), just reuse that
> value — **skip the reset**. Discord shows the secret only once and "Reset Secret" generates a
> *new* one that invalidates the old, breaking anything already using it. The client secret is a
> separate credential from the bot **token** — having the token doesn't mean you have the secret.

Only if the secret was never saved / is unrecoverable:
1. Left sidebar → **OAuth2**.
2. Under **Client Secret**, click **Reset Secret** and copy the new value.
3. Update every place that used the old secret.

Either way, paste the value into `client_secret`. Treat it like a password.

### 5. Add the OAuth2 redirect URL
Still on the **OAuth2** page:
1. Find **Redirects** → **Add Redirect**.
2. Enter exactly:
   ```
   http://localhost:8080/oauth/callback
   ```
3. Click **Save Changes** at the bottom.

> ⚠️ This must match `public_url` + `/oauth/callback` **character for character**. Discord permits
> plain `http` only for `localhost` — for any real domain you'll use `https` (Track B).

### 6. Generate a session secret
Run this once and copy the output — it signs the login cookie so sessions can't be forged:

```bash
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 7. Fill in `config.json`
Add the `web` block (see the top of this guide). For local use:

```json
"web": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 8080,
  "public_url": "http://localhost:8080",
  "client_id": "PASTE_APPLICATION_ID",
  "client_secret": "PASTE_CLIENT_SECRET",
  "session_secret": "PASTE_GENERATED_SECRET"
}
```

### 8. Start the bot
Start the bot the way you normally do. In the logs you should see:

```
Control panel listening on 127.0.0.1:8080 (public: http://localhost:8080).
```

If instead you see "Control panel disabled…" or a "session_secret / client_secret are missing"
warning, re-check step 7.

### 9. Log in
1. Open **http://localhost:8080/** in your browser.
2. You'll be redirected to Discord to **Authorize** (scope: *identify* only — it just reads who you
   are; it does not gain access to your account).
3. After authorizing you land on the dashboard.

### 10. Use it
- **Dashboard** — your guilds, and every cog with **Load / Reload / Unload** (process-wide:
  affects all guilds at once).
- **Click a guild** — toggle each cog on/off for that guild, and set each command to
  **visible / admin / owner**. Changes apply to that guild's slash picker within a few seconds.

You're done with local testing. 🎉

---

## Track B — Make it reachable from anywhere (public)

Only do this once Track A works. The extra requirement is **HTTPS**, because you'll be sending a
login session over the internet.

### 1. Point a domain at the machine
Have a domain/subdomain (e.g. `panel.dodos.fun`) resolve to the server the bot runs on.

### 2. Put HTTPS in front of the bot
The bot serves plain HTTP on its port; a **reverse proxy** (Nginx, Caddy, Cloudflare Tunnel, etc.)
terminates HTTPS and forwards to it. Example with **Caddy** (simplest — auto HTTPS):

```
panel.dodos.fun {
    reverse_proxy 127.0.0.1:8080
}
```

Keep the bot bound to `127.0.0.1` and let only the proxy be public. (If you can't use a proxy, set
`host` to `0.0.0.0` — but then you must have HTTPS some other way; never expose it as plain http.)

### 3. Update the Discord redirect
On the app's **OAuth2 → Redirects**, add:
```
https://panel.dodos.fun/oauth/callback
```
(You can keep the localhost one too.)

### 4. Update `config.json`
```json
"web": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 8080,
  "public_url": "https://panel.dodos.fun",
  "client_id": "…",
  "client_secret": "…",
  "session_secret": "…"
}
```
`public_url` being `https://…` makes the login cookie `Secure` automatically.

### 5. Restart and log in at `https://panel.dodos.fun/`.

---

## Good to know

- **Owner-only commands** (`kill`, `sync`, `reload`, the control tooling, …) never show in any
  guild's slash picker — Discord can't hide a command from just one user ID. Run them by prefix
  (e.g. `!kill`) or from the panel. This is expected.
- **Admin-only** commands map to Discord's **Manage Server** permission in the picker; the exact
  per-guild admin allowlist is enforced when the command actually runs.
- **Reloading `control_panel`** (from the panel or `!reload control_panel`) cleanly restarts the
  web server, so you can iterate without restarting the whole bot.
- **Guild admins** logging in themselves (managing only their own server) is **phase 2** — not
  wired yet. For now the panel is owner-only.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Log says "Control panel disabled" | `web.enabled` isn't `true` in `config.json`. |
| Log warns secrets missing | Fill `client_secret` and `session_secret`. |
| "Invalid OAuth state" | The redirect URL in the portal doesn't exactly match `public_url` + `/oauth/callback`, or cookies are blocked. |
| "This panel is for bot owners only" | Your Discord user ID isn't in `owners` in `config.json`. |
| Browser can't connect | Wrong port, firewall, or (Track B) the reverse proxy isn't forwarding to the bot's port. |
| Redirected to Discord in a loop | Session cookie not sticking — on Track B make sure you're on `https` and `public_url` matches. |
