"""Events and organizers a person has hidden ("Not interested", "Hide this organizer").

Every feed that shows events to a signed-in person filters through here, and the ranker's
exclusions should too (hidden_for() gives both sets in one query).
"""
from dataclasses import dataclass, field

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import HiddenItem
from app.models.event import Event
from app.models.user import User


@dataclass
class Hidden:
    event_ids: set[str] = field(default_factory=set)
    organizer_ids: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.event_ids or self.organizer_ids)

    def hides(self, event: Event) -> bool:
        return event.id in self.event_ids or event.host_id in self.organizer_ids


async def hidden_for(db: AsyncSession, user: User | str | None) -> Hidden:
    if user is None:
        return Hidden()
    user_id = user if isinstance(user, str) else user.id
    rows = (await db.execute(select(HiddenItem.kind, HiddenItem.target_id)
                             .where(HiddenItem.user_id == user_id))).all()
    hidden = Hidden()
    for kind, target in rows:
        (hidden.event_ids if kind == "event" else hidden.organizer_ids).add(target)
    return hidden


def exclude_hidden(stmt: Select, hidden: Hidden) -> Select:
    if hidden.event_ids:
        stmt = stmt.where(Event.id.not_in(hidden.event_ids))
    if hidden.organizer_ids:
        stmt = stmt.where(Event.host_id.not_in(hidden.organizer_ids))
    return stmt
