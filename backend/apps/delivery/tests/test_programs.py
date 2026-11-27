"""M18 programs: staff permissions, module/week order, cohorts, groups and placement."""

from datetime import date

from apps.catalog.models import Section
from apps.delivery.models import Holiday
from apps.identity.models import StaffRole, StaffRoleAssignment, User
from apps.learning.models import Enrollment
from core.staff_perms import PERMISSIONS
from core.tenancy import tenant_context
from core.tests import factories as f
from core.tests.base import SchemaTransactionTestCase

API = "/api/v1"


class ProgramBase(SchemaTransactionTestCase):
    """Users, roles and helpers shared by the program tests."""

    def setUp(self):
        self.staff, self.teacher, self.sara, self.omar = f.users()
        f.money(self.staff)
        self.tutor = User.objects.create_user(
            'contact+f9997e4b3dd5@example.com', "x", is_staff=True, full_name="Tia Tutor"
        )
        with tenant_context(staff=True):
            admin = StaffRole.objects.create(name="Admin", permissions=list(PERMISSIONS), is_system=True)
            teach = StaffRole.objects.create(name="Tutor", permissions=["groups.teach"], is_system=True)
            StaffRoleAssignment.objects.create(user=self.staff, role=admin)
            StaffRoleAssignment.objects.create(user=self.tutor, role=teach)

    # ------------------------------------------------------------ helpers
    def as_(self, user):
        self.client.force_login(user)

    def call(self, method, path, data=None):
        return getattr(self.client, method)(API + path, data=data, content_type="application/json")

    def ok(self, method, path, data=None):
        r = self.call(method, path, data)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def build_program(self, weeks_per_module=(2, 1)):
        self.as_(self.staff)
        pid = self.ok("post", "/studio/programs", {"title": "Professional Certificate"})["id"]
        v = self.ok("get", f"/studio/courses/{pid}")["working_version"]["id"]
        modules = []
        for i, n in enumerate(weeks_per_module, start=1):
            m = self.ok("post", f"/studio/versions/{v}/modules", {"title": f"Module {i}"})["id"]
            for w in range(1, n + 1):
                sec = self.ok(
                    "post", f"/studio/versions/{v}/sections", {"title": f"M{i} week {w}", "module_id": m}
                )
                self.ok("post", f"/studio/sections/{sec['id']}/lectures",
                        {"kind": "article", "title": f"Read {i}.{w}", "body": "<p>Notes</p>"})  # fmt: skip
            modules.append(m)
        return pid, v, modules

    def publish(self, pid, v):
        self.ok("put", f"/studio/courses/{pid}/price", {"free": True})
        self.assertEqual(self.ok("post", f"/studio/versions/{v}/submit", {})["status"], "published")


class ProgramsTest(ProgramBase):
    # ------------------------------------------------------------ tests
    def test_permissions_and_week_order(self):
        # staff without programs.build can't create or edit programs
        plain = User.objects.create_user('contact+5baf5057cfb4@example.com', "x", is_staff=True)
        self.as_(plain)
        self.assertEqual(self.call("post", "/studio/programs", {"title": "Nope program"}).status_code, 403)
        self.assertEqual(self.call("get", "/console/programs").status_code, 403)

        pid, v, (m1, m2) = self.build_program((2, 1))
        self.as_(plain)
        self.assertEqual(
            self.call("get", f"/studio/courses/{pid}").status_code, 404
        )  # never confirms it exists

        self.as_(self.staff)
        tree = self.ok("get", f"/studio/courses/{pid}")
        self.assertEqual(tree["kind"], "program")
        self.assertEqual([m["title"] for m in tree["working_version"]["modules"]], ["Module 1", "Module 2"])

        def order():
            return list(
                Section.objects.filter(version_id=v).order_by("position").values_list("title", flat=True)
            )

        self.assertEqual(order(), ["M1 week 1", "M1 week 2", "M2 week 1"])
        # modules swap: weeks follow their module, positions stay one global order
        self.ok("put", f"/studio/versions/{v}/modules/order", {"ids": [m2, m1]})
        self.assertEqual(order(), ["M2 week 1", "M1 week 1", "M1 week 2"])
        # a week moves to the end of another module
        w = Section.objects.get(version_id=v, title="M1 week 1")
        self.ok("put", f"/studio/sections/{w.id}/module", {"module_id": m2})
        self.assertEqual(
            order(), ["M2 week 1", "M1 week 1", "M1 week 2"]
        )  # last in Module 2, which comes first
        self.assertEqual(str(Section.objects.get(pk=w.pk).module_id), m2)
        # version-wide section reorder is refused for programs; weeks reorder inside a module
        ids = [str(i) for i in Section.objects.filter(version_id=v).values_list("id", flat=True)]
        self.assertEqual(
            self.call("put", f"/studio/versions/{v}/sections/order", {"ids": ids}).status_code, 400
        )
        m2_weeks = list(
            Section.objects.filter(module_id=m2).order_by("position").values_list("id", flat=True)
        )
        self.ok("put", f"/studio/modules/{m2}/weeks/order", {"ids": [str(i) for i in reversed(m2_weeks)]})
        self.assertEqual(order(), ["M1 week 1", "M2 week 1", "M1 week 2"])
        # a module with weeks can't be deleted
        self.assertEqual(self.call("delete", f"/studio/modules/{m2}").status_code, 400)

        # the programs list is paged and says what this person may do
        listing = self.ok("get", "/console/programs")
        self.assertEqual([p["id"] for p in listing["items"]], [pid])
        self.assertTrue(listing["can_build"] and listing["can_manage"])
        self.assertEqual(listing["default_calendar"], "england-and-wales")

        # the last staff member holding roles.manage can't lose it (a superuser doesn't count)
        User.objects.create_superuser('contact+dc5c389c3e09@example.com', "x")
        with tenant_context(staff=True):
            admin = StaffRole.objects.get(name="Admin")
        r = self.call("delete", f"/console/roles/{admin.id}/members/{self.staff.id}")
        self.assertEqual(r.json()["error"]["code"], "last_manager")

        # publishing keeps module keys and week placement in the next draft
        self.publish(pid, v)
        draft = self.ok("post", f"/studio/courses/{pid}/draft")["version_id"]

        # until M21 a published program is not listed or sold (user decision 2026-11-16)
        self.as_(self.sara)
        listed = [c["id"] for c in self.ok("get", "/catalog/courses")["items"]]
        self.assertNotIn(pid, listed)
        r = self.call("post", "/commerce/cart", {"course_id": pid})
        self.assertEqual(r.json()["error"]["code"], "not_for_sale")
        self.assertEqual(Section.objects.filter(version_id=draft, module__isnull=True).count(), 0)

    def test_cohort_schedule_groups_and_learner_view(self):
        pid, v, _ = self.build_program((2, 1))
        self.publish(pid, v)
        with tenant_context(staff=True):
            Holiday.objects.create(division="england-and-wales", date=date(2027, 1, 11), title="Test holiday")

        cohort = self.ok("post", f"/console/programs/{pid}/cohorts",
                         {"name": "January 2027", "start_date": "2027-01-04"})["id"]  # fmt: skip
        self.ok("post", "/console/program-closures",
                {"cohort_id": cohort, "starts_on": "2027-01-18", "ends_on": "2027-01-22", "reason": "Half term"})  # fmt: skip
        detail = self.ok("get", f"/console/program-cohorts/{cohort}")
        weeks = [w for m in detail["modules"] for w in m["weeks"]]
        self.assertEqual([w["starts_on"] for w in weeks], ["2027-01-04", "2027-01-12", "2027-01-25"])
        self.assertEqual(weeks[1]["days_off"][0]["title"], "Test holiday")
        self.assertEqual(detail["breaks"][0]["reason"], "Half term")
        self.assertEqual(detail["end_date"], "2027-01-29")

        # groups: tutor must be able to teach; capacity is enforced
        bad = self.call(
            "post", f"/console/program-cohorts/{cohort}/groups", {"name": "A", "tutor_id": str(self.omar.id)}
        )
        self.assertEqual(bad.status_code, 400)
        g = self.ok("post", f"/console/program-cohorts/{cohort}/groups",
                    {"name": "Group A", "tutor_id": str(self.tutor.id), "weekday": 2,
                     "starts_at": "10:00", "ends_at": "12:00", "capacity": 1})["id"]  # fmt: skip
        out = self.ok("post", f"/console/program-groups/{g}/members",
                      {"emails": ['contact+a6b7d7235186@example.com', "nobody@x.example"]})  # fmt: skip
        self.assertEqual(out, {"added": 1, "not_found": ["nobody@x.example"]})
        full = self.call(
            "post", f"/console/program-groups/{g}/members", {"emails": ['contact+95190e115eae@example.com']}
        )
        self.assertEqual(full.status_code, 400)
        self.assertEqual(self.call("delete", f"/console/program-groups/{g}").status_code, 400)  # not empty
        # capacity may come down to the placed learners (never below: 400 "capacity")
        r = self.call("patch", f"/console/program-cohorts/{cohort}", {"capacity": 1})
        self.assertEqual(r.status_code, 200, r.content)

        # a curriculum designer reads structure but never learners' personal data
        designer = User.objects.create_user('contact+44ea00ee6e3c@example.com', "x", is_staff=True)
        with tenant_context(staff=True):
            build = StaffRole.objects.create(name="Designer", permissions=["programs.build"])
            StaffRoleAssignment.objects.create(user=designer, role=build)
        self.as_(designer)
        self.assertFalse(self.ok("get", "/console/programs")["can_manage"])
        self.assertEqual(self.call("get", f"/console/program-groups/{g}/members").status_code, 403)
        self.as_(self.staff)

        # the learner sees modules, their group and dated weeks
        self.as_(self.sara)
        with tenant_context(user_id=self.sara.id):
            eid = Enrollment.objects.get(user=self.sara, course_id=pid).id
        player = self.ok("get", f"/learning/enrollments/{eid}")
        self.assertEqual(player["kind"], "program")
        self.assertEqual(len(player["modules"]), 2)
        self.assertEqual(player["group"]["name"], "Group A")
        self.assertEqual(player["group"]["tutor_name"], "Tia Tutor")
        self.assertEqual(player["sections"][1]["starts_on"], "2027-01-12")
        self.assertEqual(player["modules"][1]["starts_on"], "2027-01-25")

        # My learning shows the group and the first week (the cohort hasn't started yet)
        mine = self.ok("get", "/learning/my/courses")["items"][0]
        self.assertEqual((mine["group_name"], mine["cohort_name"]), ("Group A", "January 2027"))
        self.assertEqual((mine["next_week"]["number"], mine["next_week"]["starts_on"]), (1, "2027-01-04"))

        # learners can't reach the console
        self.assertEqual(self.call("get", f"/console/program-cohorts/{cohort}").status_code, 403)

        # an ended enrolment still blocks deleting its group (no 500 from the protected FK)
        with tenant_context(staff=True):
            Enrollment.objects.filter(pk=eid).update(status="revoked")
        self.as_(self.staff)
        r = self.call("delete", f"/console/program-groups/{g}")
        self.assertEqual(r.json()["error"]["code"], "not_empty")
