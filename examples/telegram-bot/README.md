# Example: a Telegram bot that sends events to Turnup through the API

> **Most people want the built-in bot instead**: Turnup can run your Telegram bot itself
> (Admin → Bot Connections → Telegram bot), with nothing extra to host. This script is for
> developers who run their own bot elsewhere and connect it through Turnup's agent API.

People send the bot a poster, a link or the event details. It forwards them to Turnup's agent
API (`docs/agent-connections.md`), whose AI reads the event and puts it in the admin approval
queue, then the bot tells them when it's approved or rejected.

This version uses **long polling**: it's one long-running script that keeps asking Telegram for
new messages, so it needs no public URL. Run it on a laptop, a VPS or any always-on machine.
(It can't run on serverless hosts like Vercel, which only run short functions per request.)

## Setup

1. **Create the bot.** In Telegram, message [@BotFather](https://t.me/BotFather), send
   `/newbot`, pick a name and a username ending in `bot`. Copy the token it gives you.
2. **Create a Turnup connection.** Admin → Bot Connections → *Connect a bot*. Copy the API key
   (shown once). Leave the callback URL empty: this bot checks review outcomes itself.
3. **Run it** (Python 3.10+):

   ```bash
   pip install httpx
   export TELEGRAM_BOT_TOKEN="123456:ABC..."
   export TURNUP_API_KEY="tuk_..."
   export TURNUP_API_URL="https://<your turnup host>/api/integrations/v1"
   python bot.py
   ```

   It prints `Running as @yourbot, connected to Turnup as '...'` when both keys work.
4. Message your bot `/start`, then send it a poster.

Optional settings: `REVIEW_CHECK_SECONDS` (how often it asks Turnup about pending events,
default 60) and `STATE_FILE` (where it remembers them across restarts, default `pending.json`).

Only one copy may run per bot token: Telegram refuses a second poller (the bot logs a 409).
In group chats, BotFather's privacy mode (`/setprivacy`) decides whether the bot sees every
message or only commands and replies to it.
