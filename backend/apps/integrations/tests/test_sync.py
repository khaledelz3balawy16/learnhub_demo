"""The Breathe sync (M17), service level: idempotent create/update, department auto-link,
email match suggestions, placement in departments (and line managers, add only), failures
(run failed, connection "needs attention", admins told), the hourly dedupe, training map
-> imported CompletionRecord -> compliant, the leave upsert and leavers flagged (never
removed). Breathe is the MockTransport from test_fixtures; everything else is real and
runs as lms_app under RLS. Celery runs inline in tests (core/test_runner.py)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from apps.catalog import services as cat
from apps.compliance import services as compliance
from apps.compliance.models import CompletionRecord, MemberStatus
from apps.engagement.models import Notification
from apps.identity.models import User
from apps.integrations import breathe, selectors, services, tasks
from apps.integrations.models import (
    ExternalDepartment,
    ExternalLeave,
    ExternalPerson,
    ExternalTrainingRecord,
    HrConnection,
    HrSyncRun,
)
from apps.org import services as org_services
from apps.org.models import MemberUnit, OrgMember, OrgUnit, UnitManager
from core.errors import ServiceError
from core.permissions import OrgRole, Scope
from core.tenancy import tenant_context
from core.tests.base import SchemaTransactionTestCase

from .test_fixtures import API_KEY, breathe_transport, default_data

HR_SETTINGS = {
    "CREDENTIAL_KEY": 'CHANGE_ME',  # throwaway, never a real key
    "ALLOWED_HOSTS": ("api.breathehr.com", "api.sandbox.breathehr.info"),
}
ALL = list(HrConnection.FEATURES)


@override_settings(HR_INTEGRATION=HR_SETTINGS)
class HrBase(SchemaTransactionTestCase):
    """Acme (owner Hana, admin Ada, manager Mia, learners Sara and Omar) and Beta (Bob)."""

    def setUp(self):
        mk = User.objects.create_user
        self.hr = mk('contact+5f2e507d492f@example.com', "x", full_name="Hana HR")
        self.ada = mk('contact+b43594824b17@example.com', "x", full_name="Ada Admin")
        self.mia = mk('contact+b33449133e5b@example.com', "x", full_name="Mia Manager")
        self.sara = mk('contact+6d840705b10d@example.com', "x", full_name="Sara Ahmed")
        self.omar = mk('contact+d4c523bfc479@example.com', "x", full_name="Omar Ali")
        self.bob = mk('contact+10f11c3b3f96@example.com', "x", full_name="Bob Beta")
        self.acme = org_services.create_organization(name="Acme", slug="acme", owner=self.hr)
        self.beta = org_services.create_organization(name="Beta", slug="beta", owner=self.bob)
        self.ACME = {"org_id": self.acme.id, "user_id": self.hr.id}
        self.BETA = {"org_id": self.beta.id, "user_id": self.bob.id}
        with tenant_context(**self.ACME):
            now = timezone.now()
            self.root = OrgUnit.objects.get(org=self.acme, parent__isnull=True)
            self.m_hr = OrgMember.objects.get(org=self.acme, user=self.hr)

            def member(user, role="learner"):
                return OrgMember.objects.create(org=self.acme, user=user, role=role, joined_at=now)

            self.m_ada = member(self.ada, "admin")
            self.m_mia = member(self.mia, "manager")
            self.m_sara = member(self.sara)
            self.m_omar = member(self.omar)
        self.serve()

    # ------------------------------------------------------------ helpers
    def serve(self, data=None, **kw):
        """Answer Breathe calls with the fixture (replaces any earlier one)."""
        transport = breathe_transport(data, **kw)
        patcher = mock.patch.object(breathe, "transport", transport)
        patcher.start()
        self.addCleanup(patcher.stop)
        return transport

    def connect(self, features=None, ctx=None, org=None, by=None):
        ctx = ctx or self.ACME
        with tenant_context(**ctx):
            return services.connect(org_id=ctx["org_id"], api_key=API_KEY, environment="sandbox",
                                    features=ALL if features is None else features, by=by or self.hr)  # fmt: skip

    def sync(self, ctx=None) -> HrSyncRun:
        ctx = ctx or self.ACME
        with tenant_context(**ctx):
            run = services.queue_sync(conn=HrConnection.objects.get(), by=self.hr)
        # the task ran inline when that block committed
        with tenant_context(**ctx):
            return HrSyncRun.objects.select_related("connection").get(pk=run.pk)

    def person(self, ext_id: str) -> ExternalPerson:
        with tenant_context(**self.ACME):
            return ExternalPerson.objects.select_related("connection").get(external_employee_id=ext_id)

    def match(self, ext_id, member):
        with tenant_context(**self.ACME):
            return services.match_person(person=self.person(ext_id), member=member)

    def notes(self, user, kind):
        with tenant_context(staff=True):
            return list(Notification.objects.filter(user=user, kind=kind))

    def admin_scope(self):
        return Scope(self.acme.id, OrgRole.OWNER, self.m_hr.id, None)

    def requirement(self, name="Fire Safety", targets=None, renewal_months=12):
        with tenant_context(**self.ACME):
            course = cat.create_course(title=f"Course {name}", slug=name.lower().replace(" ", "-"),
                                       ownership="organization", created_by=self.hr, owner_org_id=self.acme.id)  # fmt: skip
            v = course.versions.get()
            sec = cat.add_section(version=v, title="Basics")
            cat.add_lecture(section=sec, kind="article", title="Read", body="<p>Exits</p>")
            cat.submit(version=v, by=self.hr)
            course.refresh_from_db()
            return compliance.create_requirement(org_id=self.acme.id, course=course, name=name, created_by=self.hr,
                                                 targets=targets or [{}], renewal_months=renewal_months)  # fmt: skip


class ImportTest(HrBase):
    def test_first_sync_imports_everything_and_a_second_is_idempotent(self):
        conn = self.connect()
        self.assertEqual((conn.account_name, conn.external_account_id), ("Acme Care Ltd", "4242"))
        self.assertEqual(conn.base_url, breathe.SANDBOX)
        run = self.sync()
        self.assertEqual(run.status, "completed", run.error_message)
        self.assertEqual(
            run.counts,
            {"people": 4, "new_people": 4, "leavers": 1, "departments": 2, "training": 4, "applied": 0,
             "leave": 2, "to_review": 3},
        )  # fmt: skip
        sara = self.person("101")
        self.assertEqual(
            (sara.display_name, sara.email, sara.job_title, sara.department_external_id, sara.department_name,
             sara.manager_external_id, sara.contracted_hours, sara.working_pattern, str(sara.start_date)),
            ("Sara Ahmed", 'contact+6d840705b10d@example.com', "Senior Carer", "12", "Care", "102", Decimal("37.5"),
             "Full time", "2021-04-01"),
        )  # fmt: skip
        self.assertEqual(sara.mapping_status, "pending")
        self.assertEqual(self.person("102").department_external_id, "11")  # flat department_id alias
        with tenant_context(**self.ACME):
            conn = HrConnection.objects.get()
            self.assertIsNotNone(conn.last_sync_at)
            self.assertEqual(ExternalDepartment.objects.count(), 2)
            self.assertEqual(ExternalTrainingRecord.objects.count(), 4)
            # Breathe's training row for Nina used a differently spaced title: same key
            keys = set(ExternalTrainingRecord.objects.values_list("title_key", flat=True))
            self.assertEqual(keys, {"fire safety awareness", "food hygiene", "manual handling"})

        # Breathe changes: Sara's job title, a new starter, a renamed department
        data = default_data()
        data["employees"][0]["job_title"] = "Care Lead"
        data["employees"].append(
            {"id": 105, "first_name": "Ravi", "last_name": "Shah", "email": 'contact+66c07edb0dd7@example.com'}
        )
        data["departments"][0]["name"] = "Kitchen and Catering"
        self.serve(data)
        again = self.sync()
        self.assertEqual(again.status, "completed", again.error_message)
        self.assertEqual(
            (again.counts["people"], again.counts["new_people"], again.counts["to_review"]), (5, 1, 4)
        )
        with tenant_context(**self.ACME):
            self.assertEqual(ExternalPerson.objects.count(), 5)
            self.assertEqual(ExternalDepartment.objects.count(), 2)
            self.assertEqual(ExternalTrainingRecord.objects.count(), 4)
            self.assertEqual(ExternalLeave.objects.count(), 2)
            self.assertEqual(
                ExternalDepartment.objects.get(external_department_id="11").name, "Kitchen and Catering"
            )
            self.assertEqual(HrSyncRun.objects.count(), 2)
        self.assertEqual(self.person("101").job_title, "Care Lead")

    def test_features_switch_resources_off(self):
        transport = breathe_transport()
        with mock.patch.object(breathe, "transport", transport):
            self.connect(features=[])
            run = self.sync()
        self.assertEqual(run.status, "completed", run.error_message)
        self.assertEqual((run.counts["people"], run.counts["departments"], run.counts["training"],
                          run.counts["leave"]), (4, 0, 0, 0))  # fmt: skip
        paths = {r.url.path for r in transport.requests}
        self.assertEqual(paths, {"/v1/account", "/v1/employees"})  # nothing else is even read

    def test_another_company_cannot_take_the_same_account(self):
        self.connect()
        with self.assertRaises(ServiceError) as ctx:
            self.connect(ctx=self.BETA, by=self.bob)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("account_in_use", 409))
        with tenant_context(**self.BETA):
            self.assertFalse(HrConnection.objects.exists())

    def test_a_refused_key_never_connects(self):
        self.serve(api_key='CHANGE_ME')
        with self.assertRaises(ServiceError) as ctx:
            self.connect()
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("bad_key", 400))
        with tenant_context(**self.ACME):
            self.assertFalse(HrConnection.objects.exists())

    def test_disconnect_keeps_the_rows_and_forgets_the_key(self):
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            services.disconnect(conn=HrConnection.objects.get())
            conn = HrConnection.objects.get()
            self.assertEqual((conn.status, conn.secret_ciphertext), ("disabled", ""))
            self.assertEqual(ExternalPerson.objects.count(), 4)
            with self.assertRaises(ServiceError) as ctx:
                services.queue_sync(conn=conn)
            self.assertEqual(ctx.exception.code, "not_active")
        # reconnecting re-opens the same connection (same account)
        conn = self.connect()
        self.assertEqual(conn.status, "active")
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.count(), 1)

    def test_a_second_sync_while_one_is_running_is_refused(self):
        conn = self.connect()
        with tenant_context(**self.ACME):
            HrSyncRun.objects.create(
                org_id=self.acme.id, connection=conn, status="running", idempotency_key="x"
            )
            with self.assertRaises(ServiceError) as ctx:
                services.queue_sync(conn=conn)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("already_running", 409))


class MatchingTest(HrBase):
    def test_departments_auto_link_by_code_and_email_matches_are_suggestions(self):
        with tenant_context(**self.ACME):
            care = org_services.create_unit(parent=self.root, kind="department", name="Care team", code="12")
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            depts = {d.external_department_id: d for d in ExternalDepartment.objects.all()}
        self.assertEqual((depts["12"].status, depts["12"].unit_id), ("linked", care.id))
        self.assertEqual((depts["11"].status, depts["11"].unit_id), ("pending", None))

        # an email match is only a suggestion: nobody is linked until an admin confirms
        with tenant_context(**self.ACME):
            page, suggestions, _ = selectors.people(self.admin_scope(), HrConnection.objects.get(),
                                                    status=None, q=None, cursor=None, limit=50)  # fmt: skip
        self.assertEqual([p.display_name for p in page], ["Lee Long", "Nina Patel", "Omar Ali", "Sara Ahmed"])
        self.assertTrue(all(p.member_id is None for p in page))
        self.assertEqual({e: m.id for e, m in suggestions.items()},
                         {'contact+6d840705b10d@example.com': self.m_sara.id, 'contact+d4c523bfc479@example.com': self.m_omar.id})  # fmt: skip

        # the line manager (Omar, Breathe 102) joins as a manager of Sara's unit; Mia,
        # set by hand, stays
        with tenant_context(**self.ACME):
            org_services.set_unit_managers(unit=care, members=[self.m_mia])
        self.match("102", self.m_omar)
        self.match("101", self.m_sara)
        sara = self.person("101")
        self.assertEqual(sara.mapping_status, "matched")
        with tenant_context(**self.ACME):
            self.assertTrue(MemberUnit.objects.filter(member=self.m_sara, unit=care).exists())
            self.assertEqual(set(UnitManager.objects.filter(unit=care).values_list("member_id", flat=True)),
                             {self.m_mia.id, self.m_omar.id})  # fmt: skip
            m = OrgMember.objects.get(pk=self.m_sara.pk)
            self.assertEqual((m.employee_ref, m.job_title), ("101", "Senior Carer"))  # blanks filled
            page, suggestions, _ = selectors.people(self.admin_scope(), HrConnection.objects.get(),
                                                    status="pending", q=None, cursor=None, limit=50)  # fmt: skip
        self.assertEqual([p.display_name for p in page], ["Lee Long", "Nina Patel"])
        self.assertEqual(suggestions, {})

        # one Breathe person per member
        with self.assertRaises(ServiceError) as ctx:
            self.match("103", self.m_sara)
        self.assertEqual(ctx.exception.code, "already_linked")

    def test_creating_a_department_unit_places_matched_people(self):
        self.connect()
        self.sync()
        self.match("101", self.m_sara)
        with tenant_context(**self.ACME):
            dept = ExternalDepartment.objects.select_related("connection").get(external_department_id="12")
            dept = services.link_department(dept=dept, create=True)
            unit = dept.unit
            self.assertEqual(
                (unit.kind, unit.code, unit.name, unit.parent_id), ("department", "12", "Care", self.root.id)
            )
            self.assertTrue(MemberUnit.objects.filter(member=self.m_sara, unit=unit).exists())
        # the next sync keeps the link and does not make a second unit
        self.sync()
        with tenant_context(**self.ACME):
            self.assertEqual(OrgUnit.objects.filter(code="12").count(), 1)
            self.assertEqual(ExternalDepartment.objects.get(external_department_id="12").unit_id, unit.id)

    def test_leavers_are_flagged_never_removed(self):
        self.connect()
        self.sync()
        self.match("101", self.m_sara)
        lee = self.person("104")
        self.assertTrue(lee.is_leaver)
        data = default_data()
        data["employees"][0]["status"] = "Leaver"
        self.serve(data)
        run = self.sync()
        self.assertEqual((run.counts["leavers"], run.counts["to_review"]), (2, 2))  # Omar, Nina
        sara = self.person("101")
        self.assertEqual(
            (sara.is_leaver, sara.mapping_status, sara.member_id), (True, "matched", self.m_sara.id)
        )
        with tenant_context(**self.ACME):
            self.assertIsNone(OrgMember.objects.get(pk=self.m_sara.pk).removed_at)


class FailureTest(HrBase):
    def test_a_failed_sync_needs_attention_and_tells_the_admins(self):
        self.connect()
        self.serve(fail={"employees": 500})
        run = self.sync()
        self.assertEqual((run.status, run.error_code), ("failed", "busy"))
        self.assertTrue(run.error_message)
        self.assertIsNotNone(run.finished_at)
        with tenant_context(**self.ACME):
            conn = HrConnection.objects.get()
            self.assertEqual(conn.status, "attention")
            self.assertTrue(conn.last_error)
            self.assertEqual(ExternalPerson.objects.count(), 0)  # nothing half-imported
        for admin in (self.hr, self.ada):
            [note] = self.notes(admin, "hr_sync_failed")
            self.assertEqual(note.url, "/business/hr-system")
        for other in (self.mia, self.sara, self.bob):
            self.assertEqual(self.notes(other, "hr_sync_failed"), [])

        # Breathe recovers: the next sync completes and the connection is active again
        self.serve()
        run = self.sync()
        self.assertEqual(run.status, "completed", run.error_message)
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "active")

    def test_a_revoked_key_asks_for_a_new_one(self):
        self.connect()
        self.serve(api_key='CHANGE_ME')
        run = self.sync()
        self.assertEqual((run.status, run.error_code), ("failed", "bad_key"))
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "attention")
        self.assertEqual(len(self.notes(self.hr, "hr_connection_attention")), 1)
        self.assertEqual(self.notes(self.hr, "hr_sync_failed"), [])

    def test_new_people_to_review_are_announced_once(self):
        self.connect()
        self.sync()
        self.assertEqual(len(self.notes(self.hr, "hr_people_to_review")), 1)
        self.sync()  # nobody new: no second notice
        self.assertEqual(len(self.notes(self.hr, "hr_people_to_review")), 1)


class HourlyTest(HrBase):
    def test_one_run_per_company_per_hour(self):
        self.connect()
        self.serve(default_data(account_id="5151", account_name="Beta Ltd"))
        self.connect(ctx=self.BETA, by=self.bob)
        hour = datetime(2026, 11, 25, 9, 15, tzinfo=UTC)
        with mock.patch("apps.integrations.tasks.timezone") as tz:
            tz.now.return_value = hour
            tasks.hr_hourly_task()
            tasks.hr_hourly_task()  # a second beat in the same hour
            tasks.hr_hourly_task()

            def runs(ctx):
                with tenant_context(**ctx):
                    return list(HrSyncRun.objects.values_list("idempotency_key", "trigger", "status"))

            acme_conn, beta_conn = self.person_conn(self.ACME), self.person_conn(self.BETA)
            self.assertEqual(runs(self.ACME), [(f"hourly:{acme_conn}:2026-11-25T09", "hourly", "completed")])
            self.assertEqual(runs(self.BETA), [(f"hourly:{beta_conn}:2026-11-25T09", "hourly", "completed")])

            # the next hour runs again; a paused company is skipped
            with tenant_context(**self.BETA):
                services.set_paused(conn=HrConnection.objects.get(), paused=True)
            tz.now.return_value = hour + timedelta(hours=1)
            tasks.hr_hourly_task()
            self.assertEqual(len(runs(self.ACME)), 2)
            self.assertEqual(len(runs(self.BETA)), 1)

    def person_conn(self, ctx):
        with tenant_context(**ctx):
            return HrConnection.objects.get().id


class TrainingAndLeaveTest(HrBase):
    def test_mapped_training_becomes_evidence_and_the_person_is_compliant(self):
        req = self.requirement(renewal_months=12)
        self.connect()
        self.sync()
        self.match("101", self.m_sara)
        self.match("102", self.m_omar)
        with tenant_context(**self.ACME):
            self.assertEqual(
                MemberStatus.objects.get(member=self.m_sara, requirement=req).status, "not_started"
            )
            applied = services.map_training(conn=HrConnection.objects.get(), title="Fire Safety Awareness",
                                            requirement=req)  # fmt: skip
        self.assertEqual(applied, 1)  # Sara's; Nina is not linked, Omar's is another course
        with tenant_context(**self.ACME):
            [record] = CompletionRecord.objects.filter(requirement=req)
            self.assertEqual((record.member_id, record.source), (self.m_sara.id, "import"))
            self.assertEqual(record.note, "Breathe: Fire Safety Awareness (certificate FS-501)")
            done = (timezone.now() - timedelta(days=30)).date()
            self.assertEqual(record.completed_at.date(), done)
            self.assertEqual((record.expires_at.year, record.expires_at.month),
                             (done.year + 1, done.month))  # the requirement's renewal rule  # fmt: skip
            status = MemberStatus.objects.get(member=self.m_sara, requirement=req)
            self.assertEqual(status.status, "compliant")
            self.assertEqual(
                MemberStatus.objects.get(member=self.m_omar, requirement=req).status, "not_started"
            )
            rec = ExternalTrainingRecord.objects.get(external_training_id="501")
            self.assertEqual(rec.applied_record_id, record.id)
            self.assertFalse(ExternalTrainingRecord.objects.get(external_training_id="503").applied_record_id)

        # syncing again never imports the same record twice
        run = self.sync()
        self.assertEqual(run.counts["applied"], 0)
        with tenant_context(**self.ACME):
            self.assertEqual(CompletionRecord.objects.filter(requirement=req).count(), 1)

    def test_a_record_for_someone_linked_later_is_applied_on_link(self):
        req = self.requirement()
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            self.assertEqual(services.map_training(conn=HrConnection.objects.get(), title="fire safety awareness",
                                                   requirement=req), 0)  # fmt: skip
        self.match("101", self.m_sara)
        with tenant_context(**self.ACME):
            self.assertEqual(
                MemberStatus.objects.get(member=self.m_sara, requirement=req).status, "compliant"
            )

    def test_approved_leave_is_upserted_and_cancelled_leave_disappears(self):
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            rows = {lv.source_ref: lv for lv in ExternalLeave.objects.select_related("person")}
        self.assertEqual(set(rows), {"901", "904"})  # pending and past leave are not kept
        self.assertEqual(rows["901"].person.external_employee_id, "101")
        self.assertEqual(rows["901"].leave_type, "Holiday")

        today = timezone.now().date()
        data = default_data()
        data["leave_requests"][0]["end_date"] = (today + timedelta(days=9)).isoformat()  # extended
        del data["leave_requests"][3]  # 904 cancelled in Breathe
        data["leave_requests"].append({"id": 905, "employee_id": 102, "start_date": today.isoformat(),
                                       "end_date": today.isoformat(), "status": "Approved", "leave_type": "Sick"})  # fmt: skip
        self.serve(data)
        run = self.sync()
        self.assertEqual(run.counts["leave"], 2)
        with tenant_context(**self.ACME):
            rows = {lv.source_ref: lv for lv in ExternalLeave.objects.all()}
        self.assertEqual(set(rows), {"901", "905"})
        self.assertEqual(rows["901"].ends_on, today + timedelta(days=9))

        # shown for linked people only, as current leave
        self.match("101", self.m_sara)
        with tenant_context(**self.ACME):
            found = selectors.leave_for_members(self.admin_scope(), [self.m_sara.id, self.m_omar.id])
        self.assertEqual(list(found), [self.m_sara.id])
        self.assertEqual(found[self.m_sara.id].source_ref, "901")


class ReviewFixesTest(HrBase):
    """Fixes from the M17 review: no transaction held across Breathe calls, a pause or
    disconnect is never undone by a sync, the run claim, training imported at link time,
    archived units, and request-path limits."""

    def pause_acme(self, request=None):
        with tenant_context(**self.ACME):
            HrConnection.objects.update(status="paused")

    def test_breathe_is_read_with_no_transaction_open(self):
        from django.db import connection

        self.connect()
        open_tx = []
        self.serve(on_request=lambda r: open_tx.append(connection.in_atomic_block))
        run = self.sync()
        self.assertEqual(run.status, "completed", run.error_message)
        self.assertEqual(len(open_tx), 8)  # 4 resources x 2 pages
        self.assertEqual(set(open_tx), {False})

    def test_a_pause_during_the_read_is_kept_and_nothing_is_written(self):
        self.connect()
        self.serve(on_request=self.pause_acme)
        run = self.sync()
        self.assertEqual((run.status, run.error_code), ("failed", "cancelled"))
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "paused")
            self.assertFalse(ExternalPerson.objects.exists())
        self.assertEqual(self.notes(self.hr, "hr_sync_failed"), [])

    def test_a_failure_after_a_pause_does_not_reopen_the_connection(self):
        self.connect()
        self.serve(fail={"departments": 500}, on_request=self.pause_acme)
        run = self.sync()
        self.assertEqual((run.status, run.error_code), ("failed", "busy"))
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "paused")
        self.assertEqual(self.notes(self.hr, "hr_sync_failed"), [])

    def test_disconnect_closes_queued_runs_and_a_stopped_run_is_cancelled(self):
        conn = self.connect()
        with tenant_context(**self.ACME):
            queued = HrSyncRun.objects.create(org_id=self.acme.id, connection=conn, idempotency_key="q")
            services.disconnect(conn=HrConnection.objects.get())
            queued.refresh_from_db()
        self.assertEqual((queued.status, queued.error_code), ("failed", "cancelled"))
        # a run still queued for a paused connection is cancelled, not run
        conn = self.connect()
        with tenant_context(**self.ACME):
            services.set_paused(conn=HrConnection.objects.get(), paused=True)
            late = HrSyncRun.objects.create(org_id=self.acme.id, connection=conn, idempotency_key="late")
        transport = self.serve()
        run = services.process_sync(late.id, org_id=self.acme.id)
        self.assertEqual((run.status, run.error_code), ("failed", "cancelled"))
        self.assertEqual(transport.requests, [])
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "paused")

    def test_a_run_is_claimed_once(self):
        conn = self.connect()
        with tenant_context(**self.ACME):
            busy = HrSyncRun.objects.create(org_id=self.acme.id, connection=conn, idempotency_key="b",
                                            status="running")  # fmt: skip
        transport = self.serve()
        run = services.process_sync(busy.id, org_id=self.acme.id)
        self.assertEqual(run.status, "running")  # another worker has it
        self.assertEqual(transport.requests, [])

    def test_training_counts_as_soon_as_a_person_is_linked_into_a_targeted_unit(self):
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            dept = ExternalDepartment.objects.select_related("connection").get(external_department_id="12")
            unit = services.link_department(dept=dept, create=True).unit
        req = self.requirement(targets=[{"unit_id": unit.id}])
        with tenant_context(**self.ACME):
            conn = HrConnection.objects.get()
            self.assertEqual(
                services.map_training(conn=conn, title="Fire Safety Awareness", requirement=req), 0
            )
        # matching places Sara in the Care unit; compliance assigns her at once and her
        # Breathe record counts in the same step (not on the next sync)
        self.match("101", self.m_sara)
        with tenant_context(**self.ACME):
            self.assertEqual(
                MemberStatus.objects.get(member=self.m_sara, requirement=req).status, "compliant"
            )
            self.assertEqual(CompletionRecord.objects.filter(requirement=req).count(), 1)
            # mapping again never imports twice
            self.assertEqual(
                services.map_training(conn=conn, title="Fire Safety Awareness", requirement=req), 0
            )
            self.assertEqual(CompletionRecord.objects.filter(requirement=req).count(), 1)

    def test_archived_units_are_not_used(self):
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            kitchen = org_services.create_unit(
                parent=self.root, kind="department", name="Kitchen", code="old"
            )
            dept = ExternalDepartment.objects.select_related("connection").get(external_department_id="11")
            services.link_department(dept=dept, unit=kitchen)
            org_services.archive_unit(unit=kitchen)
            lee = ExternalPerson.objects.select_related("connection").get(external_employee_id="104")
            inv, _ = services.invite_person(person=lee, role="learner", unit=None, job_role=None, by=self.hr,
                                            by_role="owner")  # fmt: skip
        self.assertIsNone(inv.unit_id)  # not the archived Kitchen unit

    def test_case_insensitive_suggestions(self):
        User.objects.filter(pk=self.omar.pk).update(email='contact+d4c523bfc479@example.com')
        self.connect()
        self.sync()
        with tenant_context(**self.ACME):
            _, suggestions, _ = selectors.people(self.admin_scope(), HrConnection.objects.get(),
                                                 status=None, q=None, cursor=None, limit=50)  # fmt: skip
        self.assertEqual(suggestions['contact+d4c523bfc479@example.com'].id, self.m_omar.id)

    def test_replace_key_checks_before_calling_breathe(self):
        self.connect()
        transport = self.serve()
        with tenant_context(**self.ACME):
            conn = HrConnection.objects.get()
            for key in ("", "   ", "short"):
                with self.subTest(key=key), self.assertRaises(ServiceError) as ctx:
                    services.replace_key(conn=conn, api_key=key)
                self.assertEqual(ctx.exception.code, "bad_key")
            with override_settings(HR_INTEGRATION={**HR_SETTINGS, "CREDENTIAL_KEY": ""}):
                with self.assertRaises(ServiceError) as ctx:
                    services.replace_key(conn=conn, api_key=API_KEY)
                self.assertEqual(ctx.exception.code, "not_configured")
        self.assertEqual(transport.requests, [])

    def test_a_busy_breathe_on_connect_retries_once_only(self):
        transport = self.serve(fail={"account": 429})
        with self.assertRaises(ServiceError) as ctx:
            self.connect()
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("busy", 502))
        self.assertEqual(len(transport.requests), 2)
