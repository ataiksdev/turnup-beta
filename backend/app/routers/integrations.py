"""The agent API: outside bots and agents submit events with an API key. Every event lands in
the admin approval queue as pending. Reference: docs/agent-connections.md, and /api/docs.
"""
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import limiter
from app.models.agent import AgentConnection, AgentSubmission
from app.models.event import Category, Event
from app.schemas.admin import AIEventDraft
from app.schemas.agent import AgentEventIn, AgentMe, AgentSubmissionStatus
from app.services import agent_intake as intake
from app.services.ai_agent import MAX_IMAGE_BYTES

router = APIRouter(prefix="/api/integrations/v1", tags=["agent API"])


async def get_api_connection(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> AgentConnection:
    key = x_api_key or (authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None)
    if not key or not key.startswith(intake.API_KEY_PREFIX):
        raise HTTPException(401, "Send your API key as 'Authorization: Bearer tuk_…' or 'X-API-Key: tuk_…'.",
                            headers={"WWW-Authenticate": "Bearer"})
    conn = (await db.execute(
        select(AgentConnection).where(AgentConnection.api_key_hash == intake.hash_api_key(key))
    )).scalar_one_or_none()
    if not conn:
        raise HTTPException(401, "Unknown API key.", headers={"WWW-Authenticate": "Bearer"})
    if not conn.is_active:
        raise HTTPException(403, "This connection is paused. Ask a Turnup admin to resume it.")
    return conn


_STATUS_MESSAGES = {
    "created": "Thanks! It's with the Turnup team for review and goes live once approved.",
    "skipped_duplicate": "This event is already on Turnup, so it wasn't added again.",
    "skipped_no_event": ("Couldn't find an event in that. It needs at least a name, a date and time, "
                         "and a few words about it: try a clearer poster, or add the details as text."),
    "failed": "The event couldn't be read. Please try again later.",
    "over_limit": "Turnup has received a lot of events from this bot today. Please try again tomorrow.",
}


def _status_out(sub: AgentSubmission, ev: Event | None, repeated: bool = False) -> AgentSubmissionStatus:
    own = ev is not None and sub.status == "created"  # a duplicate points at someone else's event
    message = _STATUS_MESSAGES.get(sub.status, sub.status)
    if own and ev.review_status == "approved" and ev.status == "published":
        message = f"Approved and live on Turnup: {intake.event_public_url(ev)}"
    elif own and ev.review_status == "rejected":
        message = "Not approved for Turnup." + (f" Note from the team: {ev.review_note}" if ev.review_note else "")
    return AgentSubmissionStatus(
        submission_id=sub.id, status=sub.status, repeated=repeated,
        external_id=sub.external_id, submitted_by=sub.submitted_by,
        event_id=ev.id if ev else None, event_title=ev.title if ev else None,
        start_date=ev.start_date if ev else None, venue_name=ev.venue_name if ev else None,
        review_status=ev.review_status if own else None,
        review_note=ev.review_note if own and ev.review_status == "rejected" else None,
        event_url=intake.event_public_url(ev) if own and ev.review_status == "approved" and ev.status == "published" else None,
        message=message, created_at=sub.created_at,
    )


_HTTP_STATUS = {"created": 201, "skipped_duplicate": 409, "skipped_no_event": 422, "failed": 422, "over_limit": 429}


def _respond(response: Response, result: intake.SubmitResult) -> AgentSubmissionStatus:
    response.status_code = 200 if result.repeated else _HTTP_STATUS.get(result.submission.status, 200)
    return _status_out(result.submission, result.event, result.repeated)


@router.get("/me", response_model=AgentMe)
async def agent_me(conn: AgentConnection = Depends(get_api_connection), db: AsyncSession = Depends(get_db)):
    """Check the key works, and how much of today's allowance is left."""
    return AgentMe(name=conn.name, daily_limit=conn.daily_limit, used_today=await intake.used_today(db, conn))


@router.get("/categories", response_model=list[str])
async def agent_categories(_: AgentConnection = Depends(get_api_connection), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Category.name).order_by(Category.name))).scalars().all())


@router.post("/events", response_model=AgentSubmissionStatus, status_code=201,
             responses={200: {"description": "Repeat of an earlier external_id"},
                        409: {"description": "Already on Turnup"}, 422: {"description": "Not an event"},
                        429: {"description": "Daily limit reached"}})
@limiter.limit(settings.rate_limit_agent_api)
async def agent_submit_event(
    request: Request,
    response: Response,
    body: AgentEventIn,
    conn: AgentConnection = Depends(get_api_connection),
    db: AsyncSession = Depends(get_db),
):
    """Submit an event your bot already extracted, as structured fields. No AI call."""
    tags = body.tags if isinstance(body.tags, str) else ",".join(t.strip() for t in body.tags or [] if t.strip())
    draft = AIEventDraft(
        title=body.title, description=body.description, cover_image=body.cover_image,
        venue_name=body.venue_name, address=body.address, city=body.city, country=body.country,
        start_date=body.start_date.isoformat(),
        end_date=body.end_date.isoformat() if body.end_date else "",
        is_free=body.is_free, price_min=body.price_min, price_max=body.price_max,
        currency=body.currency.upper(), event_type=body.event_type,
        category_guess=body.category or "", tags=tags or "",
    )
    result = await intake.submit(db, conn, intake.Submission(
        submitted_by=body.submitted_by, external_id=body.external_id, draft=draft, ticket_url=body.ticket_url,
    ))
    return _respond(response, result)


@router.post("/drafts", response_model=AgentSubmissionStatus, status_code=201,
             responses={200: {"description": "Repeat of an earlier external_id"},
                        409: {"description": "Already on Turnup"}, 422: {"description": "Not an event"},
                        429: {"description": "Daily limit reached"}})
@limiter.limit(settings.rate_limit_agent_api)
async def agent_submit_raw(
    request: Request,
    response: Response,
    text: str | None = Form(None, max_length=20000, description="Event details as the person typed them"),
    url: str | None = Form(None, max_length=1000, description="A link to the event's page"),
    image: UploadFile | None = File(None, description="A poster or flyer (max 8MB)"),
    external_id: str | None = Form(None, max_length=200),
    submitted_by: str | None = Form(None, max_length=200),
    conn: AgentConnection = Depends(get_api_connection),
    db: AsyncSession = Depends(get_db),
):
    """Forward what your bot received (pasted text, a link, and/or a poster image) and Turnup's
    AI extracts the event. Multipart form; send at least one of text, url, image."""
    image_bytes = image_type = None
    if image is not None:
        image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image is too large (max 8MB).")
        image_type = (image.content_type or "image/jpeg").lower()
        if image_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            raise HTTPException(415, "The image must be a JPEG, PNG, WebP or GIF.")
    if not (text and text.strip()) and not (url and url.strip()) and not image_bytes:
        raise HTTPException(422, "Send at least one of: text, url, image.")
    result = await intake.submit(db, conn, intake.Submission(
        submitted_by=submitted_by, external_id=external_id,
        text=(text or "").strip() or None, url=(url or "").strip() or None,
        image_bytes=image_bytes, image_media_type=image_type,
    ))
    return _respond(response, result)


@router.get("/submissions", response_model=list[AgentSubmissionStatus])
async def agent_list_submissions(
    limit: int = Query(20, ge=1, le=100),
    conn: AgentConnection = Depends(get_api_connection),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AgentSubmission, Event).outerjoin(Event, Event.id == AgentSubmission.event_id)
        .where(AgentSubmission.connection_id == conn.id)
        .order_by(AgentSubmission.created_at.desc()).limit(limit)
    )).all()
    return [_status_out(s, ev) for s, ev in rows]


@router.get("/submissions/{submission_id}", response_model=AgentSubmissionStatus)
async def agent_get_submission(
    submission_id: str,
    conn: AgentConnection = Depends(get_api_connection),
    db: AsyncSession = Depends(get_db),
):
    """A submission's current review state, if you'd rather poll than take callbacks."""
    sub = await db.get(AgentSubmission, submission_id)
    if not sub or sub.connection_id != conn.id:
        raise HTTPException(404, "Submission not found")
    ev = await db.get(Event, sub.event_id) if sub.event_id else None
    return _status_out(sub, ev)
