
from datetime import datetime, timedelta, timezone
import unittest

from hpe_contributions import (
    AuthenticationStatus,
    ConsentDecision,
    ConsentEvent,
    ConsentPurpose,
    ContributionRecord,
    ContributionStore,
    DevelopmentStatus,
    IdentityRecord,
    PrivacyStatus,
    SourceProvenance,
)


class ContributionModelTests(unittest.TestCase):

    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        self.provenance = SourceProvenance(
            source_platform="ChatGPT",
            source_type="authenticated_conversation",
            authentication_status=AuthenticationStatus.ACCOUNT_AUTHENTICATED,
            conversation_id="example-conversation",
            message_id="example-message",
        )

        self.record = ContributionRecord(
            record_id="record-1",
            author_id="author-1",
            tenant_id="tenant-1",
            original_wording="Exact original words.",
            provenance=self.provenance,
            submitted_at=self.now,
            recorded_at=self.now,
        )

    def grant(self, purpose, seconds=1):
        return ConsentEvent(
            purpose=purpose,
            decision=ConsentDecision.GRANTED,
            occurred_at=self.now + timedelta(seconds=seconds),
        )

    def test_original_wording_is_preserved(self):
        self.assertEqual(
            self.record.original_wording,
            "Exact original words.",
        )

    def test_consent_is_false_when_no_consent_exists(self):
        self.assertFalse(self.record.has_consent(ConsentPurpose.SHARE))

    def test_granted_consent_is_recognized(self):
        record = self.record.add_consent_event(
            self.grant(ConsentPurpose.SHARE)
        )
        self.assertTrue(record.has_consent(ConsentPurpose.SHARE))

    def test_withdrawn_consent_is_not_valid(self):
        record = self.record.add_consent_event(
            self.grant(ConsentPurpose.SHARE, 1)
        )
        record = record.add_consent_event(
            ConsentEvent(
                purpose=ConsentPurpose.SHARE,
                decision=ConsentDecision.WITHDRAWN,
                occurred_at=self.now + timedelta(seconds=2),
            )
        )
        self.assertFalse(record.has_consent(ConsentPurpose.SHARE))

    def test_private_record_cannot_be_exported(self):
        with self.assertRaises(PermissionError):
            self.record.export_for_sharing()

    def test_shared_record_requires_share_consent(self):
        record = self.record.with_privacy_status(PrivacyStatus.SHARED)

        with self.assertRaises(PermissionError):
            record.export_for_sharing()

    def test_shared_record_can_be_exported_with_share_consent(self):
        record = self.record.add_consent_event(
            self.grant(ConsentPurpose.SHARE)
        )
        record = record.with_privacy_status(PrivacyStatus.SHARED)

        exported = record.export_for_sharing()
        self.assertEqual(exported["original_wording"], "Exact original words.")

    def test_public_record_requires_publish_consent(self):
        record = self.record.add_consent_event(
            self.grant(ConsentPurpose.SHARE, 1)
        )
        record = record.with_privacy_status(PrivacyStatus.PUBLIC)

        with self.assertRaises(PermissionError):
            record.export_for_sharing()

    def test_public_record_requires_both_consents(self):
        record = self.record.add_consent_event(
            self.grant(ConsentPurpose.SHARE, 1)
        )
        record = record.add_consent_event(
            self.grant(ConsentPurpose.PUBLISH, 2)
        )
        record = record.with_privacy_status(PrivacyStatus.PUBLIC)

        exported = record.export_for_sharing()
        self.assertEqual(exported["original_wording"], "Exact original words.")

    def test_tested_status_requires_evidence(self):
        with self.assertRaises(ValueError):
            self.record.with_development_status(
                DevelopmentStatus.TESTED
            )

    def test_tested_status_accepts_evidence(self):
        record = self.record.with_development_status(
            DevelopmentStatus.TESTED,
            evidence_references=("test-example-1",),
        )
        self.assertEqual(record.development_status, DevelopmentStatus.TESTED)

    def test_store_requires_identity_in_same_tenant(self):
        store = ContributionStore()

        with self.assertRaises((ValueError, PermissionError)):
            store.add_contribution(self.record)

    def test_store_rejects_duplicate_identity(self):
        store = ContributionStore()
        identity = IdentityRecord(
            author_id="author-1",
            tenant_id="tenant-1",
            created_at=self.now,
        )
        store.add_identity(identity)

        with self.assertRaises(ValueError):
            store.add_identity(identity)

    def test_store_rejects_duplicate_contribution(self):
        store = ContributionStore()
        identity = IdentityRecord(
            author_id="author-1",
            tenant_id="tenant-1",
            created_at=self.now,
        )
        store.add_identity(identity)
        store.add_contribution(self.record)

        with self.assertRaises(ValueError):
            store.add_contribution(self.record)

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            IdentityRecord(
                author_id="author-2",
                tenant_id="tenant-1",
                created_at=datetime(2026, 1, 1),
            )


if __name__ == "__main__":
    unittest.main()
