"""Offline evaluation of the /for-you ranker (docs/recommendations-spec.md).

    python -m app.cli recs-eval [--holdout-days 10] [--k 10]

Time split, never random: pick a cut-off T (now minus the holdout), rebuild every feature
from data before T, rank each person's feed as it would have looked at T, and check it
against what they actually saved, RSVP'd "going" to or bought between T and now (only events
that were on sale at T count). Compared with two baselines on the same people and events:
most popular first (demand score), and random order.

Everything runs in one transaction that is rolled back: the live feature tables are left
as they were.
"""
import math
import random
import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.activity import EventFeatures
from app.models.event import Event, EventAttendee, EventSave
from app.models.organizer import TicketOrder
from app.models.user import User
from app.services.rec_features import compute_event_features, compute_user_features
from app.services.recommender import _base, _exclusions, recommend


def _ndcg(ranked: list[str], positives: set[str], k: int) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, e in enumerate(ranked[:k]) if e in positives)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(positives), k)))
    return dcg / ideal if ideal else 0.0


def _recall(ranked: list[str], positives: set[str], k: int) -> float:
    return len(set(ranked[:k]) & positives) / len(positives) if positives else 0.0


async def evaluate(db, holdout_days: int = 10, k: int = 10, max_users: int = 500, seed: int = 1) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=holdout_days)
    rng = random.Random(seed)
    try:
        await compute_event_features(db, as_of=cutoff, commit=False)
        await compute_user_features(db, as_of=cutoff, commit=False)

        on_sale = {e.id for e in (await db.execute(_base(cutoff))).scalars().all()}
        positives: dict[str, set[str]] = {}
        for table, extra in ((EventSave, ()), (EventAttendee, (EventAttendee.status == "going",)),
                             (TicketOrder, (TicketOrder.status == "confirmed",))):
            for uid, eid in (await db.execute(select(table.user_id, table.event_id).where(
                    table.created_at > cutoff, table.created_at <= now, *extra))).all():
                if eid in on_sale:
                    positives.setdefault(uid, set()).add(eid)
        user_ids = sorted(positives)[:max_users]
        users = {u.id: u for u in (await db.execute(select(User).where(
            User.id.in_(user_ids), User.created_at <= cutoff, User.is_deleted == False))).scalars().all()}  # noqa: E712

        demand = {f.event_id: f.demand_score for f in (await db.execute(select(EventFeatures))).scalars().all()}
        hosts = dict((await db.execute(select(Event.id, Event.host_id).where(Event.id.in_(on_sale)))).all())
        popular = sorted(on_sale, key=lambda e: -demand.get(e, 0.0))
        scores = {"ranker": ([], []), "popular": ([], []), "random": ([], [])}
        for uid, user in users.items():
            # What they'd already committed to by the cut-off is neither recommended nor a
            # "hit" (saving before T and buying after T isn't a prediction).
            before = await _exclusions(db, user, cutoff)
            pos = positives[uid] - before
            if not pos:
                continue
            result = await recommend(db, user=user, now=cutoff, limit=max(k, 20), log=False, persist=False)
            ranked = [e.id for e in result.events]
            pool = [e for e in popular if e not in before and hosts.get(e) != uid]
            shuffled = list(pool)
            rng.shuffle(shuffled)
            for name, order in (("ranker", ranked), ("popular", pool), ("random", shuffled)):
                scores[name][0].append(_ndcg(order, pos, k))
                scores[name][1].append(_recall(order, pos, k))
        people = len(scores["ranker"][0])
        return {
            "cutoff": cutoff.isoformat(timespec="minutes"), "people": people, "events_on_sale": len(on_sale), "k": k,
            **{name: {f"ndcg@{k}": round(statistics.fmean(n), 4) if n else None,
                      f"recall@{k}": round(statistics.fmean(r), 4) if r else None}
               for name, (n, r) in scores.items()},
        }
    finally:
        await db.rollback()

