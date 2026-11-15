"""Preview proposals and strict field approval validation; no database access."""

from app.errors import Conflict, Invalid
from app.schemas.imports import (
    ApprovedDonorUpdate,
    DonorFieldChange,
    DonorUpdateField,
    SpreadsheetDonorUpdate,
)
from app.services.ingest.adapters import IncomingDonor

FIELDS: tuple[DonorUpdateField, ...] = ("name", "organization", "email", "phone", "notes")


def value(profile: IncomingDonor, field: DonorUpdateField) -> str:
    return str(getattr(profile, "display_name" if field == "name" else field))


class Proposals:
    def __init__(self, donors: dict[int, IncomingDonor], visible: set[int]) -> None:
        self.donors, self.visible = donors, visible
        self.items: dict[int, SpreadsheetDonorUpdate] = {}
        self.baselines: dict[int, dict[DonorUpdateField, str]] = {}
        self.observed: dict[tuple[int, DonorUpdateField], str] = {}

    def consider(self, donor_id: int, incoming: IncomingDonor, provided: list[str]) -> bool:
        old = self.donors[donor_id]
        changed = False
        for field in FIELDS:
            if field not in provided:
                continue
            key, new = (donor_id, field), value(incoming, field)
            if key in self.observed and self.observed[key] != new:
                raise Invalid(
                    f"Conflicting spreadsheet updates for donor {donor_id}, field {field}."
                )
            self.observed[key] = new
            if value(old, field) == new:
                continue
            item = self.items.setdefault(
                donor_id,
                SpreadsheetDonorUpdate(
                    donor_id=donor_id,
                    donor_name=old.display_name,
                    changes={},
                ),
            )
            hidden = donor_id not in self.visible
            item.changes[field] = DonorFieldChange(
                new_value=new, old_value=None if hidden else value(old, field), old_hidden=hidden
            )
            self.baselines.setdefault(donor_id, {})[field] = value(old, field)
            changed = True
        return changed


def approved_changes(
    offered: list[SpreadsheetDonorUpdate],
    baselines: dict[int, dict[DonorUpdateField, str]],
    current: dict[int, IncomingDonor],
    matched: set[int],
    approvals: list[ApprovedDonorUpdate],
) -> dict[int, dict[DonorUpdateField, str]]:
    offers = {item.donor_id: item for item in offered}
    result: dict[int, dict[DonorUpdateField, str]] = {}
    for approval in approvals:
        did = approval.donor_id
        if did in result or did not in offers:
            raise Invalid("Approve each donor once, using only previewed updates.")
        if did not in matched or did not in current:
            raise Conflict("Donor matching changed after preview. Upload again.")
        changes: dict[DonorUpdateField, str] = {}
        for field in approval.fields:
            if field not in offers[did].changes:
                raise Invalid("An approved field was not offered in this preview.")
            new = offers[did].changes[field].new_value
            actual = value(current[did], field)
            if actual != baselines[did][field] and actual != new:
                raise Conflict("Donor data changed after preview. Upload again.")
            if actual != new:
                changes[field] = new
        result[did] = changes
    return {did: fields for did, fields in result.items() if fields}
