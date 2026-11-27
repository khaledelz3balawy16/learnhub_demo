"""Full-course access opens the player: token unlocks, packages and staff grants create a
personal enrolment that always matches the entitlement (commerce.unlock.enrol_on_course_access)."""

import json
from datetime import timedelta

from django.utils import timezone

from apps.commerce.tests import test_unlock
from apps.commerce.unlock import enrol_on_course_access, unlock_course
from apps.learning.models import Enrollment
from apps.platform.access import resolve
from apps.platform.models import ContentEntitlement
from core.errors import ServiceError
from core.tenancy import tenant_context
from core.tests.base import SchemaTransactionTestCase


class CourseAccessEnrolTests(test_unlock.UnlockFixture, SchemaTransactionTestCase):
    def _as_user(self):
        return tenant_context(user_id=str(self.user.id), staff=True)

    def _enrolments(self):
        with self._as_user():
            return list(
                Enrollment.objects.filter(user=self.user, course=self.course, org__isnull=True).exclude(
                    status=Enrollment.Status.SUPERSEDED
                )
            )

    def _unlock(self):
        self._grant(200)
        with self._as_user():
            return unlock_course(user=self.user, course_id=self.course.id)

    def test_unlock_creates_lifetime_purchase_enrolment(self):
        self.course.access_days = 30  # the course's access period must not cut lifetime access short
        with tenant_context(staff=True):
            self.course.save(update_fields=["access_days"])
        ent = self._unlock()
        [e] = self._enrolments()
        self.assertEqual(e.status, Enrollment.Status.ACTIVE)
        self.assertEqual(e.source, Enrollment.Source.PURCHASE)
        self.assertEqual(e.source_ref, ent.id)
        self.assertIsNone(e.access_expires_at)

    def test_resolver_still_reports_the_entitlement(self):
        self._unlock()
        with self._as_user():
            d = resolve(self.user, "course", self.course.id)
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason_code, 'CHANGE_ME')

    def test_idempotent(self):
        self._unlock()
        with self._as_user():
            a = enrol_on_course_access(user=self.user, course_id=self.course.id)
            b = enrol_on_course_access(user=self.user, course_id=self.course.id)
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(self._enrolments()), 1)

    def test_no_entitlement_is_refused(self):
        with self._as_user(), self.assertRaises(ServiceError) as cm:
            enrol_on_course_access(user=self.user, course_id=self.course.id)
        self.assertEqual(cm.exception.status, 403)

    def test_refunded_enrolment_is_reactivated(self):
        with self._as_user():
            Enrollment.objects.create(
                user=self.user, course=self.course, source=Enrollment.Source.PURCHASE,
                status=Enrollment.Status.REVOKED, enrolled_at=timezone.now(),
            )  # fmt: skip
        ent = self._unlock()
        [e] = self._enrolments()
        self.assertEqual(e.status, Enrollment.Status.ACTIVE)
        self.assertEqual(e.source_ref, ent.id)

    def test_lapsed_plan_enrolment_gets_lifetime_access(self):
        with self._as_user():
            Enrollment.objects.create(
                user=self.user, course=self.course, source=Enrollment.Source.SUBSCRIPTION,
                enrolled_at=timezone.now() - timedelta(days=60),
                access_expires_at=timezone.now() - timedelta(days=1),
            )  # fmt: skip
        self._unlock()
        [e] = self._enrolments()
        self.assertEqual(e.source, Enrollment.Source.PURCHASE)
        self.assertIsNone(e.access_expires_at)

    def test_completed_enrolment_keeps_its_status(self):
        with self._as_user():
            Enrollment.objects.create(
                user=self.user, course=self.course, source=Enrollment.Source.SUBSCRIPTION,
                status=Enrollment.Status.COMPLETED, enrolled_at=timezone.now(),
                access_expires_at=timezone.now() - timedelta(days=1),
            )  # fmt: skip
        self._unlock()
        [e] = self._enrolments()
        self.assertEqual(e.status, Enrollment.Status.COMPLETED)
        self.assertIsNone(e.access_expires_at)

    def test_revoked_entitlement_no_longer_opens_the_course(self):
        ent = self._unlock()
        with tenant_context(staff=True):
            ContentEntitlement.objects.filter(pk=ent.id).update(revoked_at=timezone.now())
        with self._as_user():
            d = resolve(self.user, "course", self.course.id)
        self.assertFalse(d.allowed)

    def test_api_enrols_existing_access(self):
        with tenant_context(staff=True):
            ent = ContentEntitlement.objects.create(
                user=self.user, scope=ContentEntitlement.Scope.COURSE, target_id=self.course.id,
                source=ContentEntitlement.Source.ADMIN_GRANT, granted_at=timezone.now(),
            )  # fmt: skip
        self.client.force_login(self.user)
        r = self.client.post(
            f"/api/v1/commerce/tokens/access/course/{self.course.id}/enrol",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        [e] = self._enrolments()
        self.assertEqual(str(e.id), r.json()["enrollment_id"])
        self.assertEqual(e.source, Enrollment.Source.ADMIN_GRANT)
        self.assertEqual(e.source_ref, ent.id)

    def test_api_without_access_is_403(self):
        self.client.force_login(self.user)
        r = self.client.post(
            f"/api/v1/commerce/tokens/access/course/{self.course.id}/enrol",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)
