# Bot connections: sending events to Turnup from outside bots

Outside bots and agents (your own WhatsApp or Telegram bot, an AI agent, n8n or Zapier, a
partner's system) can submit events to Turnup with an API key. **Nothing they send goes live on
its own**: every event lands in the admin Events queue as *pending*, the same as a scouted or
moderator-submitted event, and is published only when an admin approves it.

```
 person ──poster/text──▶ your bot ──API──▶ Turnup ──▶ admin approval queue
                            ▲                              │ approve / reject
                            └──── signed callback ◀────────┘
```

## Setting up a connection (admins)

Admin → **Bot Connections** (`/admin/integrations`) → *Connect a bot*:

| Field | What it does |
|---|---|
| Name | Shown on its events in the queue ("via Lagos Events bot") |
| Host account | Optional username whose profile hosts the events (e.g. a partner organizer's bot posting their own events). Empty: the scout bot account hosts them |
| Daily limit | Submissions accepted per rolling 24 hours (default 50). A poster or text submission costs one AI call |
| Callback URL | Optional `https://` URL Turnup POSTs review outcomes to |

You get an **API key** (`tuk_…`) and a **callback signing secret** (`whsec_…`) once. Give
them to whoever runs the bot. *Rotate key* issues new ones and the old key stops working at
once; *Pause* refuses the key without deleting anything; *Delete* removes the connection and its
log but keeps the events it created.

## The API (bot developers)

Base URL: `https://<turnup host>/api/integrations/v1`. Authenticate with
`Authorization: Bearer tuk_…` (or `X-API-Key: tuk_…`). Interactive reference: `/api/docs`,
under "agent API". 30 requests a minute per IP.

### Forward what the person sent: `POST /drafts` (multipart)

The simplest bot: pass along the poster, link or text and let Turnup's AI extract the event.

| Field | |
|---|---|
| `image` | Poster/flyer, JPEG, PNG, WebP or GIF, max 8MB |
| `text` | What the person typed (a caption, the details, "this Saturday!") |
| `url` | A link to the event's page |
| `submitted_by` | Who gave you the event (phone number, chat id, name). Echoed back in callbacks so you know whom to tell |
| `external_id` | Your id for this message. Sending it again returns the first result and does nothing |

At least one of `image`, `text`, `url` is required.

```bash
curl -X POST https://turnup.ng/api/integrations/v1/drafts \
  -H "Authorization: Bearer $TURNUP_KEY" \
  -F "image=@poster.jpg" -F "text=Free entry before 10pm" \
  -F "submitted_by=+2348030000000" -F "external_id=wamid.HBgL..."
```

### Send fields you extracted yourself: `POST /events` (JSON)

If your bot already does its own extraction. No AI call on Turnup's side.

```json
{
  "title": "Rooftop Jazz Night",
  "description": "An evening of live jazz on the rooftop.",
  "start_date": "2026-12-05T19:00:00+01:00",
  "end_date": "2026-12-05T23:00:00+01:00",
  "venue_name": "Sky Bar", "address": "1 Marina Rd", "city": "Lagos", "country": "Nigeria",
  "event_type": "physical",
  "is_free": false, "price_min": 5000, "price_max": 15000, "currency": "NGN",
  "category": "Music", "tags": ["jazz", "live music"],
  "cover_image": "https://your-bot.example.com/posters/123.jpg",
  "ticket_url": "https://tix.example.com/jazz",
  "submitted_by": "+2348030000000", "external_id": "msg-123"
}
```

Required: `title`, `description`, `start_date`. Dates must include a timezone offset. `category`
is one of `GET /categories` (anything else is ignored). `cover_image` must be a public http(s) URL.

### The response (both endpoints)

```json
{
  "submission_id": "…", "status": "created", "repeated": false,
  "external_id": "msg-123", "submitted_by": "+2348030000000",
  "event_id": "…", "event_title": "Rooftop Jazz Night",
  "start_date": "2026-12-05T18:00:00Z", "venue_name": "Sky Bar",
  "review_status": "pending", "review_note": null, "event_url": null,
  "message": "Thanks! It's with the Turnup team for review and goes live once approved.",
  "created_at": "…"
}
```

`message` is written for the person, so a bot can simply reply with it.

| HTTP | `status` | Meaning |
|---|---|---|
| 201 | `created` | Waiting for admin review |
| 200 | (any) | `repeated: true`: this `external_id` was sent before; the earlier result is returned |
| 409 | `skipped_duplicate` | Already on Turnup (same title, or same venue on the same day) |
| 422 | `skipped_no_event` | No event found: needs a name, a date and time, and a description |
| 422 | `failed` | Couldn't be read (e.g. the AI or the link failed). Retry later |
| 429 | `over_limit` | The connection's daily limit is reached |
| 401 / 403 | | Bad key / connection paused |

### Other endpoints

- `GET /submissions/{submission_id}`: current state; once approved, `event_url` is set.
- `GET /submissions?limit=20`: your recent submissions.
- `GET /categories`: category names.
- `GET /me`: the connection's name, `daily_limit` and `used_today`.

## Review callbacks

If the connection has a callback URL, Turnup POSTs once when an admin approves or rejects
one of its events:

```json
{
  "type": "event.approved",
  "submission_id": "…", "external_id": "msg-123", "submitted_by": "+2348030000000",
  "event_id": "…", "event_title": "Rooftop Jazz Night", "start_date": "2026-12-05T18:00:00+00:00",
  "review_status": "approved", "review_note": null,
  "event_url": "https://turnup.ng/events/rooftop-jazz-night-1a2b3c4d"
}
```

`type` is `event.approved` or `event.rejected` (with the admin's `review_note`). Headers:
`X-Turnup-Event`, `X-Turnup-Timestamp` (Unix seconds) and
`X-Turnup-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>" with the callback secret>`.
Verify it before trusting the body, and reject old timestamps:

```python
import hmac, hashlib, time

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Answer with any 2xx. Delivery is best effort (one attempt, 10 seconds, redirects not followed,
and only to public addresses), so poll `GET /submissions/{id}` if you must not miss an outcome.

WhatsApp only lets a business send a free-form message within 24 hours of the person's last
message. An approval that comes later needs a WhatsApp message template on your side.

## Notes for operators

- The API key is stored only as a SHA-256 hash. The callback secret is encrypted with a key
  derived from `SECRET_KEY`: changing `SECRET_KEY` stops callbacks until the key is rotated.
- Submitted events have `created_via = "agent_api"`. The connection that sent each is in
  `agent_submissions` (Admin → Bot Connections → Recent submissions).
- Settings: `AGENT_DEFAULT_DAILY_LIMIT` (50), `RATE_LIMIT_AGENT_API` ("30/minute").
- Code: `app/routers/integrations.py` (the API), `app/routers/admin_integrations.py`,
  `app/services/agent_intake.py`; drafting reuses `app/services/ai_agent.py`.
