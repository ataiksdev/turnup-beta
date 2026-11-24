"""A learned ranker for /for-you, once there is enough real activity to learn from.

    python -m app.cli recs-train [--weeks 8] [--out data/models/ranker.txt] [--force]

1. Training examples: at weekly cut-offs, every person who went on to save, RSVP "going" to
   or buy something in the next LABEL_DAYS gets their whole candidate list scored as the
   ranker saw it then (recommender.score_all, features rebuilt as of the cut-off). Each
   candidate's features are the ranker's named parts (WEIGHTS keys). Its label is what they
   did: 3 bought, 2 going, 1 saved, 0 nothing.
2. A LightGBM lambdarank model is trained on all but the latest cut-off and compared with
   the hand-set weights on the latest one (NDCG@10).
3. It's saved only if there's enough data (MIN_GROUPS people-weeks, MIN_POSITIVES actions)
   and it beats the hand-set weights by MIN_GAIN. --force skips both checks, for
   experiments on synthetic data. Saving doesn't switch it on: set RANKER_MODEL_PATH to
   the file. recs_served then records the model's version, so its click-through can be
   compared with the hand-set ranker's.

LightGBM is optional (requirements-ml.txt): without it the API runs as before and training
says so.
"""
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.event import EventAttendee, EventSave
from app.models.organizer import TicketOrder
from app.models.user import User

logger = logging.getLogger("turnup.rec_training")

LABEL_DAYS = 7
MIN_GROUPS = 300
MIN_POSITIVES = 1000
MIN_GAIN = 0.005
GRADES = {"save": 1, "going": 2, "order": 3}


def feature_names() -> list[str]:
    from app.services.recommender import WEIGHTS
    return sorted(WEIGHTS)


def _vector(parts: dict, names: list[str]) -> list[float]:
    return [float(parts.get(n, 0.0)) for n in names]


# ── Using a trained model ───────────────────────────────────────────────────────


@dataclass
class LoadedModel:
    booster: object
    features: list[str]
    version: str

    def score(self, scored: list) -> list[float]:
        import numpy as np
        rows = np.asarray([_vector(s.parts, self.features) for s in scored], dtype=float)
        return [float(x) for x in self.booster.predict(rows)]


_cache: dict = {}


def load_model() -> LoadedModel | None:
    path = settings.ranker_model_path
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        if _cache.get("warned") != path:
            logger.warning("RANKER_MODEL_PATH %s not found: using the hand-set weights", path)
            _cache["warned"] = path
        return None
    if _cache.get("key") == (path, mtime):
        return _cache["model"]
    try:
        import lightgbm
        with open(path + ".json") as f:
            meta = json.load(f)
        model = LoadedModel(lightgbm.Booster(model_file=path), meta["features"], meta["version"])
    except Exception:
        logger.exception("Couldn't load the ranker model at %s: using the hand-set weights", path)
        model = None
    _cache.update(key=(path, mtime), model=model)
    return model


# ── Building examples ───────────────────────────────────────────────────────────


async def _actions(db: AsyncSession, start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """{user_id: {event_id: grade}} for what people did in (start, end]."""
    out: dict[str, dict[str, int]] = {}
    sources = (
        ("save", select(EventSave.user_id, EventSave.event_id).where(
            EventSave.created_at > start, EventSave.created_at <= end)),
        ("going", select(EventAttendee.user_id, EventAttendee.event_id).where(
            EventAttendee.status == "going", EventAttendee.created_at > start, EventAttendee.created_at <= end)),
        ("order", select(TicketOrder.user_id, TicketOrder.event_id).where(
            TicketOrder.status == "confirmed", TicketOrder.created_at > start, TicketOrder.created_at <= end)),
    )
    for kind, q in sources:
        for uid, eid in (await db.execute(q)).all():
            out.setdefault(uid, {})
            out[uid][eid] = max(out[uid].get(eid, 0), GRADES[kind])
    return out


async def build_examples(db: AsyncSession, cutoff: datetime, max_people: int = 2000) -> list[dict]:
    """One group per person: the hand-set score, the parts and the label of every candidate.
    Rebuilds features as of `cutoff` inside the caller's transaction (roll back afterwards)."""
    from app.services.rec_features import compute_event_features, compute_user_features
    from app.services.recommender import score_all
    await compute_event_features(db, as_of=cutoff, commit=False)
    await compute_user_features(db, as_of=cutoff, commit=False)
    actions = await _actions(db, cutoff, cutoff + timedelta(days=LABEL_DAYS))
    users = (await db.execute(select(User).where(
        User.id.in_(sorted(actions)[:max_people]), User.created_at <= cutoff,
        User.is_deleted == False))).scalars().all()  # noqa: E712
    groups = []
    for user in users:
        _, scored, _ = await score_all(db, user=user, now=cutoff, persist=False, use_model=False)
        labels = actions[user.id]
        if not scored or not any(s.event.id in labels for s in scored):
            continue  # nothing they acted on was a candidate: no ranking signal
        groups.append({"cutoff": cutoff, "user_id": user.id,
                       "rows": [(s.parts, s.score, labels.get(s.event.id, 0)) for s in scored]})
    return groups


def _ndcg(labels_in_order: list[int], k: int = 10) -> float:
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(labels_in_order[:k]))
    ideal = sorted(labels_in_order, reverse=True)
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal[:k]))
    return dcg / idcg if idcg else 0.0


def _mean_ndcg(groups: list[dict], scores: list[list[float]]) -> float:
    vals = []
    for g, sc in zip(groups, scores):
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        vals.append(_ndcg([g["rows"][i][2] for i in order]))
    return round(sum(vals) / len(vals), 4) if vals else 0.0


# ── Training ────────────────────────────────────────────────────────────────────


async def train(db: AsyncSession, weeks: int = 8, out: str = "data/models/ranker.txt", force: bool = False,
                now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoffs = sorted(now - timedelta(days=LABEL_DAYS + 7 * i) for i in range(weeks))
    try:
        by_cutoff = [await build_examples(db, c) for c in cutoffs]
    finally:
        await db.rollback()  # the as-of feature rebuilds never touch the live tables
    valid, train_groups = by_cutoff[-1], [g for gs in by_cutoff[:-1] for g in gs]
    positives = sum(1 for gs in by_cutoff for g in gs for r in g["rows"] if r[2] > 0)
    report = {"cutoffs": [c.date().isoformat() for c in cutoffs], "train_groups": len(train_groups),
              "valid_groups": len(valid), "positives": positives}
    if not force and (len(train_groups) + len(valid) < MIN_GROUPS or positives < MIN_POSITIVES):
        return {**report, "status": "not_enough_data",
                "needs": {"groups": MIN_GROUPS, "positives": MIN_POSITIVES}}
    if not train_groups or not valid:
        return {**report, "status": "not_enough_data"}
    try:
        import lightgbm
    except ImportError:
        return {**report, "status": "lightgbm_not_installed", "install": "pip install -r requirements-ml.txt"}

    import numpy as np
    names = feature_names()
    X = np.asarray([_vector(p, names) for g in train_groups for p, _, _ in g["rows"]], dtype=float)
    y = np.asarray([label for g in train_groups for _, _, label in g["rows"]], dtype=float)
    group_sizes = [len(g["rows"]) for g in train_groups]
    booster = lightgbm.train(
        {"objective": "lambdarank", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 20,
         "label_gain": [0, 1, 3, 7], "eval_at": [10], "verbosity": -1, "seed": 1, "deterministic": True},
        lightgbm.Dataset(X, label=y, group=group_sizes, feature_name=names), num_boost_round=300)

    learned = [[float(x) for x in booster.predict(np.asarray([_vector(p, names) for p, _, _ in g["rows"]], dtype=float))]
               for g in valid]
    hand = [[score for _, score, _ in g["rows"]] for g in valid]
    report.update(ndcg_model=_mean_ndcg(valid, learned), ndcg_hand=_mean_ndcg(valid, hand))
    report["importance"] = dict(sorted(zip(names, (int(x) for x in booster.feature_importance("gain"))),
                                       key=lambda kv: -kv[1])[:10])
    if not force and report["ndcg_model"] < report["ndcg_hand"] + MIN_GAIN:
        return {**report, "status": "not_better", "saved": None}

    version = f"lgbm-{now:%Y%m%d}"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    booster.save_model(out)
    with open(out + ".json", "w") as f:
        json.dump({"version": version, "features": names, "trained_at": now.isoformat(), **report}, f, indent=1,
                  default=str)
    return {**report, "status": "saved", "saved": out, "version": version,
            "next": f"Set RANKER_MODEL_PATH={out} to use it"}
