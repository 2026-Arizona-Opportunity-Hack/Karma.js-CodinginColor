"""Drafts from templates and the template screens (MSG-1, MSG-2, MSG-8, D-127)."""

from urllib.parse import quote

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Donor, Gift, Message, MessageTemplate
from app.errors import Conflict, Invalid
from app.repos import audit, messages, templates, users
from app.schemas.common import MemberRef
from app.schemas.messages import MessageCreate, MessageListOut, MessageOut
from app.schemas.settings import TemplateIn, TemplateListOut, TemplateOut
from app.services.messaging import defaults


def _ref(db: Session, user_id: int | None) -> MemberRef | None:
    user = users.get_for_session(db, user_id) if user_id is not None else None
    if user is None:
        return None
    return MemberRef(id=user.id, display_name=user.display_name, is_active=user.is_active)


def sms_link(db: Session, m: Message) -> str | None:
    """A pre-filled `sms:` link for an approved text, for the owner to tap (MSG-5)."""
    if m.channel != "sms" or m.status != "approved":
        return None
    phone = messages.donor_phone(db, m.donor_id)
    return f"sms:{quote(phone, safe='+')}?body={quote(m.body, safe='')}" if phone else None


def to_out(db: Session, m: Message) -> MessageOut:
    return MessageOut(
        id=m.id, donor_id=m.donor_id, donor_name=messages.donor_name(db, m.donor_id),
        gift_id=m.gift_id, kind=m.kind, channel=m.channel, status=m.status,
        subject=m.subject, body=m.body, created_by=_ref(db, m.created_by),
        approved_by=_ref(db, m.approved_by), sent_by=_ref(db, m.sent_by),
        created_at=m.created_at, approved_at=m.approved_at, sent_at=m.sent_at,
        delivery_mode=m.delivery_mode, provider_ref=m.provider_ref,
        error=m.error, sms_link=sms_link(db, m),
    )  # fmt: skip


def _first_name(donor: Donor) -> str:
    if donor.first_name:
        return donor.first_name
    if donor.kind != "person":
        return donor.display_name
    return donor.display_name.split()[0]


def _values(db: Session, donor: Donor, gift: tuple[Gift, str] | None) -> dict[str, str]:
    values = {
        "first_name": _first_name(donor),
        "owner_name": messages.owner_name(db, donor),
        "org_name": defaults.ORG_NAME,
    }
    if gift is not None:
        g, program = gift
        values.update(
            gift_amount=defaults.money(g.gross_cents),
            gift_date=f"{g.gift_date:%B} {g.gift_date.day}, {g.gift_date.year}",
            program=program,
        )
    return values


def create_draft(
    db: Session, actor: Actor, donor_id: int, body: MessageCreate
) -> tuple[MessageOut, bool]:
    """Returns the message and whether it is new. A second request returns the open draft."""
    if body.kind not in defaults.TEMPLATE_KINDS:
        raise Invalid("Only thank-you, quarterly update and lapsed nudge messages exist so far.")
    donor = messages.donor_to_act_on(db, actor, donor_id)
    if donor.do_not_contact:
        raise Conflict("This donor is marked do not contact, so no message can be drafted.")
    gift = None
    if body.kind == "thank_you":
        if body.gift_id is None:
            raise Invalid("A thank-you needs the gift it thanks for (gift_id).")
        gift = messages.gift_of(db, donor.id, body.gift_id)
        if gift is None:
            raise Invalid("That gift is not one of this donor's gifts.")
        if gift[0].is_matching_gift:  # D-127: an employer match is not the employee's giving
            raise Invalid("An employer match gets no thank-you draft; thank the donation itself.")
    elif body.gift_id is not None:
        raise Invalid("Only a thank-you is tied to a gift.")
    existing = messages.find_open(db, donor.id, body.kind, body.gift_id)
    if existing is not None:
        return to_out(db, existing), False
    tpl = templates.get_for_draft(db, body.kind, body.channel)
    values = _values(db, donor, gift)
    msg, created = messages.insert_draft(
        db, actor, donor_id=donor.id, gift_id=body.gift_id, kind=body.kind, channel=body.channel,
        subject=defaults.render(tpl.subject, values) if tpl.subject else None,
        body=defaults.render(tpl.body, values),
    )  # fmt: skip
    if created:
        audit.write(
            db, actor, "message.draft", entity="message", entity_id=msg.id,
            data={"donor_id": donor.id, "kind": body.kind, "channel": body.channel},
        )  # fmt: skip
    return to_out(db, msg), created


def list_messages(db: Session, actor: Actor, status: str | None) -> MessageListOut:
    return MessageListOut(items=[to_out(db, m) for m in messages.list_for(db, actor, status)])


def _template_out(t: MessageTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id, kind=t.kind, channel=t.channel, subject=t.subject,
        body=t.body, merge_fields=list(defaults.MERGE_FIELDS), updated_at=t.updated_at,
    )  # fmt: skip


def list_templates(db: Session, actor: Actor) -> TemplateListOut:
    return TemplateListOut(items=[_template_out(t) for t in templates.list_all(db, actor)])


def put_template(db: Session, actor: Actor, body: TemplateIn) -> TemplateOut:
    if body.kind not in defaults.TEMPLATE_KINDS:
        raise Invalid(
            "Only thank-you, quarterly update and lapsed nudge templates can be edited so far."
        )
    bad = defaults.unknown_fields(body.body + " " + (body.subject or ""))
    if bad:
        names = ", ".join("{" + b + "}" for b in bad)
        allowed = ", ".join("{" + f + "}" for f in defaults.MERGE_FIELDS)
        raise Invalid(f"Unknown merge field {names}. Use: {allowed}.")
    row = templates.upsert(
        db, actor, kind=body.kind, channel=body.channel, subject=body.subject, body=body.body
    )
    audit.write(
        db, actor, "template.update", entity="message_template", entity_id=row.id,
        data={"kind": body.kind, "channel": body.channel},
    )  # fmt: skip
    return _template_out(row)
