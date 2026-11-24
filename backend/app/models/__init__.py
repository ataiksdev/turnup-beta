from app.models.user import User
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.social import Comment, Follow, Notification
from app.models.auth_tokens import (
    UserSession, EmailVerification, PasswordReset, MagicLink, TwoFactor, OAuthAccount, PhoneOTP
)
from app.models.organizer import (
    OrganizerProfile, TicketTier, TicketOrder, EventTemplate,
    EventCoHost, EventWaitlist, EventView, EventReview,
)

from app.models import venue as _venue  # noqa: F401  (registers venue marketplace tables)
from app.models.discovery import HiddenItem, SearchAlert
from app.models.sharing import ShareConversion, ShareLink
from app.models import activity as _activity  # noqa: F401  (activity log + recommendation features)

__all__ = [
    "User", "Category", "Event", "EventAttendee", "EventSave",
    "Comment", "Follow", "Notification",
    "UserSession", "EmailVerification", "PasswordReset",
    "MagicLink", "TwoFactor", "OAuthAccount", "PhoneOTP",
    "OrganizerProfile", "TicketTier", "TicketOrder", "EventTemplate",
    "EventCoHost", "EventWaitlist", "EventView", "EventReview",
    "HiddenItem", "SearchAlert", "ShareLink", "ShareConversion",
]
