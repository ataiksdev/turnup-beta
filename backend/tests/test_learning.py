"""Embeddings and the learned ranker (app/services/embeddings.py, rec_training.py)."""
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models.discovery import EventEmbedding
from app.models.event import EventAttendee
from app.services import embeddings as em
from app.services import rec_training
from tests.test_recommendations import NOW, make_category, make_event, make_user


def test_hashing_vectors_are_unit_length_and_share_words():
    a = em.hashing_vector("Afrobeats rooftop party in Lekki")
    b = em.hashing_vector("Rooftop afrobeats night, Lekki")
    c = em.hashing_vector("Python meetup: async databases")
    assert abs(sum(x * x for x in a) - 1) < 1e-3
    assert em.cosine(a, b) > em.cosine(a, c) + 0.2


async def test_embed_events_skips_unchanged_text_and_survives_provider_errors(db, monkeypatch):
    _, host = await make_user(db, role="organizer")
    eid = await make_event(db, host, title="Jazz on the Lagoon")
    monkeypatch.setattr(em.settings, "embeddings_provider", "hashing")
    first = await em.embed_events(db)
    assert first["provider"] == "hashing" and first["embedded"] >= 1
    row = await db.get(EventEmbedding, eid)
    assert row.model == "hashing-256" and len(row.vector) == 256
    again = await em.embed_events(db)
    assert again["embedded"] == 0                    # nothing changed

    monkeypatch.setattr(em.settings, "embeddings_provider", "openai")
    monkeypatch.setattr(em.settings, "openai_api_key", "test")
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        body = calls[-1]
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0, 0.0] if i % 2 else [0.0, 2.0]}
                                                  for i in range(len(body["input"]))]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await em.embed_events(db, client)
    assert result["provider"] == "openai" and result["embedded"] >= 1 and calls[0]["dimensions"] == 512
    await db.refresh(row)
    assert row.model == "openai/text-embedding-3-small-512" and row.vector in ([0.0, 1.0], [1.0, 0.0])

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        await db.execute(EventEmbedding.__table__.delete())
        assert (await em.embed_events(db, client))["embedded"] == 0   # logged, not raised


async def test_ranker_prefers_events_like_the_ones_they_went_to(db, monkeypatch):
    from app.models.user import User
    from app.services.recommender import score_all
    monkeypatch.setattr(em.settings, "embeddings_provider", "hashing")
    cat, _ = await make_category(db)
    _, host = await make_user(db, role="organizer")
    _, uid = await make_user(db)
    past = await make_event(db, host, title="Highlife brass band night", category_id=cat,
                            start=NOW() - timedelta(days=20))
    db.add(EventAttendee(user_id=uid, event_id=past, status="going", created_at=NOW() - timedelta(days=25)))
    await db.commit()
    like = await make_event(db, host, title="Highlife brass band evening", category_id=cat)
    unlike = await make_event(db, host, title="Crypto trading seminar", category_id=cat)
    await em.embed_events(db)
    _, scored, _ = await score_all(db, user=await db.get(User, uid), now=NOW(), persist=False)
    parts = {s.event.id: s.parts for s in scored}
    assert parts[like].get("semantic", 0) > parts[unlike].get("semantic", 0)


async def test_training_refuses_without_enough_data(db):
    report = await rec_training.train(db, weeks=2, out="/nonexistent/should-not-be-written.txt")
    assert report["status"] in ("not_enough_data", "lightgbm_not_installed")


def test_no_model_configured_means_hand_set_weights(monkeypatch):
    monkeypatch.setattr(rec_training.settings, "ranker_model_path", "")
    assert rec_training.load_model() is None
    monkeypatch.setattr(rec_training.settings, "ranker_model_path", "/nope/ranker.txt")
    assert rec_training.load_model() is None


async def test_a_trained_model_ranks_and_is_recorded(db, tmp_path, monkeypatch):
    pytest.importorskip("lightgbm")
    pytest.importorskip("numpy")
    from app.models.user import User
    from app.services.recommender import ranker_version, recommend
    from app.models.event import EventSave
    _, host = await make_user(db, role="organizer")
    _, uid = await make_user(db)
    old = NOW() - timedelta(days=60)
    events = [await make_event(db, host, title=f"Model test {i}", created_at=NOW() - timedelta(days=30),
                               start=NOW() + timedelta(days=5)) for i in range(4)]
    # People who saved something in each of the last two weeks: one training week, one to check against.
    for i in range(4):
        _, person = await make_user(db, created_at=old)
        db.add(EventSave(user_id=person, event_id=events[i % 4], created_at=NOW() - timedelta(days=10)))
        db.add(EventSave(user_id=person, event_id=events[(i + 1) % 4], created_at=NOW() - timedelta(days=3)))
    await db.commit()
    out = str(tmp_path / "ranker.txt")
    report = await rec_training.train(db, weeks=2, out=out, force=True)  # forced: too little data otherwise
    assert report["status"] == "saved", report
    meta = json.loads(open(out + ".json").read())
    assert meta["features"] == rec_training.feature_names() and meta["version"].startswith("lgbm-")
    monkeypatch.setattr(rec_training.settings, "ranker_model_path", out)
    assert ranker_version().startswith("lgbm-")
    result = await recommend(db, user=await db.get(User, uid), log=False, persist=False)
    assert result.events
