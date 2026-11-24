"""Event text search.

Postgres (production): full-text search over title, venue, city, tags and description, with
prefix matching ("afrob" finds "afrobeats"), plus trigram word similarity on the short fields
for typos ("afrobeets", "lekki phse 1"). Both are backed by GIN indexes created in migration
0009 (named ix_search_*; see migrations/env.py for why Alembic leaves them alone).

Anything else (SQLite in development and tests): every word must appear in one of the fields,
and words that match nothing are widened to close spellings of words that do exist in event
titles, tags, venues and cities.
"""
import difflib
import re

from sqlalchemy import ColumnElement, Text, and_, func, literal, literal_column, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event

MAX_TOKENS = 8
_WORD = re.compile(r"\w+", re.UNICODE)


def tokens(q: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(q or "")][:MAX_TOKENS]


def _c(col):
    return func.coalesce(col, "")


def fts_document():
    """Must match the expression in the ix_search_events_fts index exactly."""
    return (_c(Event.title) + " " + _c(Event.venue_name) + " " + _c(Event.city) + " "
            + _c(Event.tags) + " " + _c(Event.description))


def name_document():
    """Must match the expression in the ix_search_events_name_trgm index exactly."""
    return func.lower(_c(Event.title) + " " + _c(Event.tags) + " " + _c(Event.venue_name) + " " + _c(Event.city))


def is_postgres(db: AsyncSession) -> bool:
    return db.get_bind().dialect.name == "postgresql"


async def text_search(db: AsyncSession, q: str) -> tuple[ColumnElement[bool] | None, ColumnElement | None]:
    """A WHERE clause for events matching q, and a relevance score to sort by (None when the
    database can't score). (None, None) when q has no searchable words."""
    words = tokens(q)
    if not words:
        return None, None
    if is_postgres(db):
        return _postgres(words, await _has_trigrams(db))
    return await _portable(db, words), None


_trgm_cache: dict[str, bool] = {}


async def _has_trigrams(db: AsyncSession) -> bool:
    """pg_trgm comes from migration 0009. A database built another way (the test suite's
    create_all) may not have it: search then still works, just without typo tolerance."""
    key = str(db.get_bind().url)
    if key not in _trgm_cache:
        _trgm_cache[key] = bool((await db.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))).scalar())
    return _trgm_cache[key]


def _postgres(words: list[str], trigrams: bool):
    config = literal_column("'simple'::regconfig")
    tsv = func.to_tsvector(config, fts_document())
    # Every word, each as a prefix: "afro lag" -> 'afro':* & 'lag':*. Words are \w+ only, so
    # nothing in them is tsquery syntax.
    tsq = func.to_tsquery(config, literal(" & ".join(f"{w}:*" for w in words), Text))
    phrase = literal(" ".join(words), Text)  # already lower case
    matches = tsv.op("@@")(tsq)
    rank = func.ts_rank(tsv, tsq)
    if not trigrams:
        return matches, rank
    # word_similarity(phrase, names) >= pg_trgm.word_similarity_threshold (0.6 by default)
    fuzzy = phrase.op("<%")(name_document())
    return or_(matches, fuzzy), rank + func.word_similarity(phrase, name_document())


_FIELDS = (Event.title, Event.venue_name, Event.city, Event.tags, Event.description)


async def _vocabulary(db: AsyncSession) -> set[str]:
    rows = (await db.execute(
        select(Event.title, Event.tags, Event.venue_name, Event.city)
        .where(Event.status == "published").order_by(Event.start_date.desc()).limit(2000)
    )).all()
    vocab: set[str] = set()
    for row in rows:
        for value in row:
            vocab.update(tokens(value or ""))
    return vocab


async def _portable(db: AsyncSession, words: list[str]):
    vocab: set[str] | None = None
    per_word = []
    for w in words:
        variants = [w]
        if len(w) >= 4:
            if vocab is None:
                vocab = await _vocabulary(db)
            if not any(v.startswith(w) for v in vocab):
                variants += difflib.get_close_matches(w, vocab, n=3, cutoff=0.75)
        per_word.append(or_(*[f.ilike(f"%{v}%") for v in variants for f in _FIELDS]))
    return and_(*per_word)
