"""DED-3 identity precedence. Never infer identity from a name alone."""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

from app.services.ingest.adapters import IncomingDonor
from app.services.ingest.normalizers import email, name, phone


@dataclass
class Resolution:
    verdict: Literal["new", "link", "review", "anonymous"]
    donor_id: int | None = None
    candidates: list[int] = field(default_factory=list)
    reason: str | None = None


def identity_keys(donor: IncomingDonor) -> list[tuple[str, str]]:
    keys = [
        ("email", email(donor.email)),
        ("phone", phone(donor.phone)),
        ("zeffy_contact", donor.zeffy_contact),
    ]
    if donor.display_name and donor.organization and donor.kind == "person":
        keys.append(("name_org", name(donor.display_name) + "|" + name(donor.organization)))
    return [(kind, value) for kind, value in keys if value]


def fingerprint(donor: IncomingDonor) -> str:
    """Remember a person's explicit review decision without stealing a household email.

    Strong identities stay unique. For conflicts, the existing reviewed incoming
    identity plus normalized name records the exception; a name alone never does.
    """
    keys = fingerprints(donor)
    return keys[0] if keys else ""


def fingerprints(donor: IncomingDonor) -> list[str]:
    return [
        sha256(
            json.dumps(
                (kind, value, name(donor.display_name), donor.kind), ensure_ascii=False
            ).encode()
        ).hexdigest()
        for kind, value in identity_keys(donor)
    ]


def names_conflict(first: IncomingDonor, second: IncomingDonor) -> bool:
    if first.last_name and second.last_name and name(first.last_name) != name(second.last_name):
        return True
    a, b = name(first.first_name), name(second.first_name)
    return bool(a and b and a[0] != b[0])


class IdentityIndex:
    def __init__(
        self,
        donors: dict[int, IncomingDonor] | None = None,
        identities: list[tuple[int, str, str]] | None = None,
        remembered: dict[str, int | None] | None = None,
    ) -> None:
        self.donors = (donors or {}).copy()
        self.remembered = remembered or {}
        self.index: dict[tuple[str, str], list[int]] = {}
        self._next_token = min([0, *self.donors]) - 1
        for did, donor in sorted(self.donors.items()):
            self.learn(did, donor)
        for did, kind, value in identities or []:
            self._add(did, kind, value)

    def _add(self, did: int, kind: str, value: str) -> None:
        ids = self.index.setdefault((kind, value), [])
        if not ids or (kind == "name_org" and did not in ids):
            ids.append(did)

    def learn(self, did: int, donor: IncomingDonor) -> None:
        for kind, value in identity_keys(donor):
            self._add(did, kind, value)

    def resolve(self, donor: IncomingDonor) -> Resolution:
        if donor.anonymous:
            return Resolution("anonymous")
        platform = self.index.get(("zeffy_contact", donor.zeffy_contact), [])
        if platform:
            return Resolution("link", donor_id=platform[0])
        approved_keys = dict(
            zip((kind for kind, _ in identity_keys(donor)), fingerprints(donor), strict=True)
        )

        def approved(kind: str) -> Resolution | None:
            key = approved_keys.get(kind)
            if key not in self.remembered:
                return None
            did = self.remembered[key]
            if did is None:
                return Resolution("anonymous")
            return Resolution("link", donor_id=did) if did in self.donors else None

        if decision := approved("zeffy_contact"):
            return decision
        if decision := approved("email"):
            return decision
        emails = self.index.get(("email", email(donor.email)), [])
        if emails:
            if names_conflict(donor, self.donors[emails[0]]):
                return Resolution("review", candidates=emails.copy(), reason="name_conflict")
            return Resolution("link", donor_id=emails[0])
        if decision := approved("phone"):
            return decision
        phones = self.index.get(("phone", phone(donor.phone)), [])
        if phones:
            return Resolution("review", candidates=phones.copy(), reason="phone")
        if decision := approved("name_org"):
            return decision
        for kind, value in identity_keys(donor):
            if kind == "name_org" and (ids := self.index.get((kind, value))):
                return Resolution("review", candidates=ids.copy(), reason="name_employer")
        return Resolution("new")

    def create(self, donor: IncomingDonor) -> int:
        did = self._next_token
        self._next_token -= 1
        self.donors[did] = donor
        self.learn(did, donor)
        return did
