"""Data rights: the consent history and "download my data" (Privacy Policy, "Your rights").

export_user_data() walks every table that has a column pointing at users.id (so tables added
later are included without changes here), plus the activity log and computed features, which
are keyed by user id without a foreign key. Secrets and other people's identities are left out.
"""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.models.activity import Activity, UserFeatures
from app.models.discovery import ConsentLog
from app.models.user import User

CONSENT_SETTINGS = ("personalized_recs", "profiling_consent", "event_alerts", "wrapped_opt_in")

# Not exported at all: one-time sign-in secrets, and staff audit logs.
SKIP_TABLES = {"email_verifications", "password_resets", "magic_links", "phone_otps", "kyc_access_log"}
# Never exported from any table.
SECRET_COLUMNS = {"hashed_password", "jti", "token", "token_hash", "secret", "backup_codes",
                  "access_token", "refresh_token", "otp_code", "value_hash", "bank_account_hash",
                  "paystack_email_token", "invite_token"}
# Rows found through one column, where another column names someone else who didn't share
# their data with you: those columns are blanked.
OTHER_PEOPLE = {("share_conversions", "sharer_id"): {"user_id"}}


def log_consent(db: AsyncSession, user: User, changed: dict, source: str = "settings") -> None:
    """Record changes to data choices. `changed` maps setting -> new value."""
    now = datetime.now(timezone.utc)
    for setting, value in changed.items():
        if setting in CONSENT_SETTINGS:
            db.add(ConsentLog(user_id=user.id, setting=setting, value=bool(value), source=source, changed_at=now))


async def consent_history(db: AsyncSession, user_id: str) -> list[ConsentLog]:
    return list((await db.execute(select(ConsentLog).where(ConsentLog.user_id == user_id)
                                  .order_by(ConsentLog.changed_at.desc()))).scalars().all())


def _plain(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _row(obj_row: dict, table: str, matched_on: str) -> dict:
    blank = OTHER_PEOPLE.get((table, matched_on), set())
    return {k: (None if k in blank else _plain(v)) for k, v in obj_row.items() if k not in SECRET_COLUMNS}


async def export_user_data(db: AsyncSession, user: User) -> dict:
    out: dict = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "about": "Everything Turnup holds that is linked to your account. Passwords, sign-in "
                 "secrets and other people's details are left out. Questions: see /privacy.",
        "tables": {},
    }
    for table in Base.metadata.sorted_tables:
        if table.name in SKIP_TABLES:
            continue
        cols = [c for c in table.columns
                if any(fk.column.table.name == "users" and fk.column.name == "id" for fk in c.foreign_keys)]
        if table.name == "users":
            cols = [table.c.id]
        rows: dict = {}
        for col in cols:
            for r in (await db.execute(select(table).where(col == user.id))).mappings().all():
                key = tuple(r[k.name] for k in table.primary_key.columns) or id(r)
                rows.setdefault(key, _row(dict(r), table.name, col.name))
        if rows:
            out["tables"][table.name] = list(rows.values())

    activity = (await db.execute(select(Activity.__table__).where(Activity.user_id == user.id)
                                 .order_by(Activity.occurred_at))).mappings().all()
    if activity:
        out["tables"]["activity_log"] = [_row(dict(r), "activity_log", "user_id") for r in activity]
    feats = (await db.execute(select(UserFeatures.__table__).where(UserFeatures.user_id == user.id))).mappings().all()
    if feats:
        out["tables"]["user_features"] = [_row(dict(r), "user_features", "user_id") for r in feats]
    return out
