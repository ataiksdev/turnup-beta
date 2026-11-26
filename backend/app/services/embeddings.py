"""Event text embeddings, and the "semantic" taste signal the ranker builds from them.

- embed_events() (worker, every 30 minutes) embeds events from the last 180 days onwards
  whose text changed.
- taste_vector() averages the vectors of events a person saved, RSVP'd "going" to or bought
  (weighted 1, 2, 3); the ranker scores each candidate by its cosine similarity to that.

Providers (EMBEDDINGS_PROVIDER): OpenAI text-embedding-3-small (512 dimensions) or Gemini
gemini-embedding-001 (768 dimensions) using the AI keys already configured, or "hashing": a local model that
hashes words and word pairs into 256 dimensions. It needs no key or network and catches
shared words ("afrobeats", "rooftop"), though not meaning the way a trained model does.
Vectors from different models are never compared: each row records its model.
"""
import hashlib
import logging
import math
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.discovery import EventEmbedding
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import TicketOrder

logger = logging.getLogger("turnup.embeddings")
HASH_DIM = 256
GEMINI_MODEL = "gemini-embedding-001"  # text-embedding-004 was retired by Google (404s)
GEMINI_DIM = 768
BATCH = 64
_WORD = re.compile(r"[a-z0-9]+")


def provider() -> str | None:
    p = settings.embeddings_provider
    if p == "off":
        return None
    if p == "auto":
        return "openai" if settings.openai_api_key else "gemini" if settings.gemini_api_key else "hashing"
    return p


def model_name(p: str | None = None) -> str | None:
    p = p or provider()
    return {"openai": "openai/text-embedding-3-small-512", "gemini": f"gemini/{GEMINI_MODEL}-{GEMINI_DIM}",
            "hashing": f"hashing-{HASH_DIM}"}.get(p or "")


def event_text(e: Event, category: str | None) -> str:
    return " | ".join(filter(None, (e.title, category, (e.tags or "").replace(",", ", "), e.venue_name,
                                    (e.description or "")[:1500])))


def _normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 6) for x in v]


def hashing_vector(text: str) -> list[float]:
    words = _WORD.findall(text.lower())
    v = [0.0] * HASH_DIM
    for tok in words + [f"{a} {b}" for a, b in zip(words, words[1:])]:
        h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        v[int.from_bytes(h[:4], "little") % HASH_DIM] += 1.0 if h[4] & 1 else -1.0
    return _normalise(v)


async def embed_texts(texts: list[str], p: str, client: httpx.AsyncClient) -> list[list[float]]:
    if p == "hashing":
        return [hashing_vector(t) for t in texts]
    if p == "openai":
        r = await client.post("https://api.openai.com/v1/embeddings",
                              headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                              json={"model": "text-embedding-3-small", "input": texts, "dimensions": 512})
        r.raise_for_status()
        return [_normalise(d["embedding"]) for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    if p == "gemini":
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:batchEmbedContents",
            # Key in a header, not the URL, so it never shows up in error messages or logs.
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={"requests": [{"model": f"models/{GEMINI_MODEL}", "content": {"parts": [{"text": t}]},
                                "taskType": "SEMANTIC_SIMILARITY", "outputDimensionality": GEMINI_DIM}
                               for t in texts]})
        r.raise_for_status()
        return [_normalise(e["values"]) for e in r.json()["embeddings"]]
    raise ValueError(f"Unknown embeddings provider {p!r}")


async def embed_events(db: AsyncSession, client: httpx.AsyncClient | None = None, limit: int = 2000) -> dict:
    p = provider()
    if p is None:
        return {"skipped": "EMBEDDINGS_PROVIDER is off"}
    model = model_name(p)
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(Event, Category.name).outerjoin(Category, Category.id == Event.category_id)
        # Recent past events too: taste vectors are built from what people went to.
        .where(Event.status.in_(("published", "completed")), Event.end_date > now - timedelta(days=180))
        .order_by(Event.end_date.desc()).limit(limit))).all()
    existing = {r.event_id: r for r in (await db.execute(select(EventEmbedding).where(
        EventEmbedding.event_id.in_([e.id for e, _ in rows])))).scalars().all()} if rows else {}
    todo = []
    for e, cat in rows:
        text = event_text(e, cat)
        digest = hashlib.sha256(text.encode()).hexdigest()
        have = existing.get(e.id)
        if not have or have.model != model or have.text_hash != digest:
            todo.append((e.id, text, digest))
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    done = 0
    try:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            try:
                vectors = await embed_texts([t for _, t, _ in chunk], p, client)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning("Embedding with %s failed: %s", p, exc)
                break
            for (eid, _, digest), vec in zip(chunk, vectors):
                row = existing.get(eid)
                if row:
                    row.model, row.vector, row.text_hash, row.computed_at = model, vec, digest, now
                else:
                    db.add(EventEmbedding(event_id=eid, model=model, vector=vec, text_hash=digest, computed_at=now))
                done += 1
        await db.commit()
    finally:
        if own:
            await client.aclose()
    return {"provider": p, "embedded": done, "waiting": len(todo) - done}


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both are unit vectors


async def vectors_for(db: AsyncSession, event_ids: list[str]) -> dict[str, list[float]]:
    model = model_name()
    if not model or not event_ids:
        return {}
    return dict((await db.execute(select(EventEmbedding.event_id, EventEmbedding.vector).where(
        EventEmbedding.event_id.in_(event_ids), EventEmbedding.model == model))).all())


async def taste_vector(db: AsyncSession, user_id: str, now: datetime, days: int = 180) -> list[float] | None:
    """The weighted mean of what they committed to before `now`, or None without history."""
    since = now - timedelta(days=days)
    weights: dict[str, float] = {}
    for eid, in (await db.execute(select(EventSave.event_id).where(
            EventSave.user_id == user_id, EventSave.created_at >= since, EventSave.created_at <= now))).all():
        weights[eid] = max(weights.get(eid, 0), 1.0)
    for eid, in (await db.execute(select(EventAttendee.event_id).where(
            EventAttendee.user_id == user_id, EventAttendee.status == "going",
            EventAttendee.created_at >= since, EventAttendee.created_at <= now))).all():
        weights[eid] = max(weights.get(eid, 0), 2.0)
    for eid, in (await db.execute(select(TicketOrder.event_id).where(
            TicketOrder.user_id == user_id, TicketOrder.status == "confirmed",
            TicketOrder.created_at >= since, TicketOrder.created_at <= now))).all():
        weights[eid] = max(weights.get(eid, 0), 3.0)
    if not weights:
        return None
    recent = sorted(weights, key=lambda e: -weights[e])[:50]
    vecs = await vectors_for(db, recent)
    if not vecs:
        return None
    dim = len(next(iter(vecs.values())))
    total = [0.0] * dim
    for eid, v in vecs.items():
        for i, x in enumerate(v):
            total[i] += weights[eid] * x
    return _normalise(total)
