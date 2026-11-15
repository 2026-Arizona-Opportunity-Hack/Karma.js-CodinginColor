"""What one viewer sees of custom values: active fields only, contact fields under DON-3."""

from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import FieldDefinition
from app.schemas.fields import FieldMeta
from app.services.fields import service, values


class _Owned:
    def __init__(self, owner_user_id: int | None) -> None:
        self.owner_user_id = owner_user_id


class FieldView:
    """Loads each entity's definitions once per request, not once per row."""

    def __init__(self, db: Session, actor: Actor) -> None:
        self._db, self._actor = db, actor
        self._defs: dict[str, list[FieldDefinition]] = {}

    def defs(self, entity: str) -> list[FieldDefinition]:
        if entity not in self._defs:
            self._defs[entity] = service.definitions(self._db, entity)
        return self._defs[entity]

    def meta(self, entity: str) -> list[FieldMeta]:
        return service.meta(self.defs(entity))

    def custom(
        self, entity: str, raw: dict[str, Any] | None, owner_user_id: int | None
    ) -> dict[str, Any]:
        if not raw:
            return {}
        allowed = can(self._actor, Action.DONOR_VIEW_CONTACT, _Owned(owner_user_id))
        return values.visible(self.defs(entity), raw, can_see_contact=allowed)
