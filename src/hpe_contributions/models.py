
"""Consent-aware, provenance-preserving contribution record models.

This is a reference implementation, not a production identity,
authorization, encryption, or durable-storage system.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Iterable


class AuthenticationStatus(str, Enum):
    UNKNOWN = "unknown"
    ACCOUNT_AUTHENTICATED = "account_authenticated"
    UNAUTHENTICATED = "unauthenticated"
    NOT_APPLICABLE = "not_applicable"


class ContextOrigin(str, Enum):
    HUMAN_SUPPLIED = "human_supplied"
    AI_GENERATED = "ai_generated"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ConsentPurpose(str, Enum):
    PRESERVE = "preserve"
    ANALYZE = "analyze"
    SHARE = "share"
    PUBLISH = "publish"
    RESEARCH_DEVELOPMENT = "research_development"


class ConsentDecision(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class PrivacyStatus(str, Enum):
    PRIVATE = "private"
    RESTRICTED = "restricted"
    SHARED = "shared"
    PUBLIC = "public"


class DevelopmentStatus(str, Enum):
    PROPOSED = "proposed"
    DOCUMENTED = "documented"
    IMPLEMENTED = "implemented"
    TESTED = "tested"
    VERIFIED = "verified"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class SourceProvenance:
    source_platform: str
    source_type: str
    authentication_status: AuthenticationStatus = AuthenticationStatus.UNKNOWN
    account_reference: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None

    def __post_init__(self):
        if not self.source_platform.strip() or not self.source_type.strip():
            raise ValueError("source_platform and source_type are required")


@dataclass(frozen=True)
class OriginalContext:
    content: str
    origin: ContextOrigin = ContextOrigin.UNKNOWN
    is_ai_summary: bool = False


@dataclass(frozen=True)
class ConsentEvent:
    purpose: ConsentPurpose
    decision: ConsentDecision
    occurred_at: datetime
    contributor_reference: str | None = None
    explanation: str | None = None

    def __post_init__(self):
        _require_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True)
class IdentityRecord:
    author_id: str
    tenant_id: str
    created_at: datetime

    def __post_init__(self):
        if not self.author_id or not self.tenant_id:
            raise ValueError("author_id and tenant_id are required")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True)
class ContributionRecord:
    record_id: str
    author_id: str
    tenant_id: str
    original_wording: str
    provenance: SourceProvenance
    submitted_at: datetime
    recorded_at: datetime
    original_context: tuple[OriginalContext, ...] = ()
    consent_history: tuple[ConsentEvent, ...] = ()
    privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE
    development_status: DevelopmentStatus = DevelopmentStatus.PROPOSED
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.record_id or not self.author_id or not self.tenant_id:
            raise ValueError("record_id, author_id, and tenant_id are required")
        if not self.original_wording:
            raise ValueError("original_wording must not be empty")

        _require_aware(self.submitted_at, "submitted_at")
        _require_aware(self.recorded_at, "recorded_at")

        if self.development_status in {
            DevelopmentStatus.IMPLEMENTED,
            DevelopmentStatus.TESTED,
            DevelopmentStatus.VERIFIED,
        } and not self.evidence_references:
            raise ValueError(
                "implemented, tested, and verified statuses require evidence_references"
            )

    def has_consent(self, purpose: ConsentPurpose) -> bool:
        """Absence of a consent event never means consent."""
        events = [
            event for event in self.consent_history
            if event.purpose == purpose
        ]

        if not events:
            return False

        latest = max(events, key=lambda event: event.occurred_at)
        return latest.decision == ConsentDecision.GRANTED

    def require_consent(self, *purposes: ConsentPurpose) -> None:
        missing = [
            purpose.value
            for purpose in purposes
            if not self.has_consent(purpose)
        ]

        if missing:
            raise PermissionError(
                "Missing current consent for: " + ", ".join(missing)
            )

    def add_consent_event(self, event: ConsentEvent):
        """Append consent history without replacing previous events."""
        return replace(
            self,
            consent_history=self.consent_history + (event,)
        )

    def with_development_status(
        self,
        status: DevelopmentStatus,
        evidence_references: Iterable[str] = (),
    ):
        return replace(
            self,
            development_status=status,
            evidence_references=tuple(evidence_references),
        )

    def export_for_sharing(self) -> dict:
        """Export only when privacy and purpose-specific consent permit."""
        if self.privacy_status in {
            PrivacyStatus.PRIVATE,
            PrivacyStatus.RESTRICTED,
        }:
            raise PermissionError("This record cannot be exported")

        self.require_consent(ConsentPurpose.SHARE)

        if self.privacy_status == PrivacyStatus.PUBLIC:
            self.require_consent(ConsentPurpose.PUBLISH)

        # Private identity and source identifiers are excluded.
        return {
            "record_id": self.record_id,
            "original_wording": self.original_wording,
            "source_platform": self.provenance.source_platform,
            "source_type": self.provenance.source_type,
            "submitted_at": self.submitted_at.isoformat(),
            "original_context": [
                {
                    "content": item.content,
                    "origin": item.origin.value,
                    "is_ai_summary": item.is_ai_summary,
                }
                for item in self.original_context
            ],
            "privacy_status": self.privacy_status.value,
        }


class ContributionStore:
    """In-memory tenant-scoped reference store."""

    def __init__(self):
        self._identities = {}
        self._contributions = {}

    def add_identity(self, identity: IdentityRecord):
        key = (identity.tenant_id, identity.author_id)

        if key in self._identities:
            raise ValueError("Identity already exists in this tenant")

        self._identities[key] = identity

    def add_contribution(self, record: ContributionRecord):
        identity_key = (record.tenant_id, record.author_id)

        if identity_key not in self._identities:
            raise ValueError(
                "Author identity must exist in the same tenant"
            )

        key = (record.tenant_id, record.record_id)

        if key in self._contributions:
            raise ValueError(
                "Contribution already exists in this tenant"
            )

        self._contributions[key] = record

    def get_contribution(self, tenant_id: str, record_id: str):
        try:
            return self._contributions[(tenant_id, record_id)]
        except KeyError as exc:
            raise KeyError(
                "Contribution not found in this tenant"
            ) from exc
