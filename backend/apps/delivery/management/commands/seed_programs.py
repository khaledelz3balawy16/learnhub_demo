"""Seed the provider's real programs (Programs plan M23, D27) with demo cohorts.

Reads one JSON file per program from `apps/delivery/seed/programs/` (or `--dir`). The files
are the only thing that changes when the real week-by-week structure arrives: this command
reads them, it never reaches into another system.

For each program it creates, through the normal services: the program (modules, weeks and
components) published; its KSB standard and settings; offers at a placeholder price tier;
a running and a planned cohort with two groups each, a tutor and a weekly timetable; demo
learners (`@learnhub.example.com`, no password) placed in the groups; planned sessions;
and, for the running cohort, attendance, completed readings and off-the-job logs.

Insert-only and safe to run again: a program whose slug exists is skipped. It never sends
mail and never creates Teams meetings (staff create those from the console).
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.engagement import notify
from core.errors import ServiceError
from core.tenancy import tenant_context

SEED_DIR = Path(__file__).resolve().parents[2] / "seed" / "programs"
DOMAIN = "learnhub.example.com"

# LMS_v2's standard week (NEEDS-USER #2). Its recording and video slots are left out: a
# recording comes from each group's Teams session, and a video needs a real upload.
WEEK_TEMPLATE = [
    {"kind": "live_session", "title": "Live session: {module}, week {week}", "otj_min": 120, "cpd_min": 120},
    {"kind": "article", "title": "Reading: {module}, week {week}", "otj_min": 120, "cpd_min": 120,
     "body": "<p>This week's reading for {module}. Your tutor goes through it in the live session.</p>"},
    {"kind": "assignment", "title": "Reflection: {module}, week {week}", "otj_min": 30, "cpd_min": 30,
     "instructions": "<p>Write a short reflection: what you learnt this week and how you will use it at work.</p>"},
]  # fmt: skip

# (name, weekday 0 = Monday, starts, ends)
GROUPS = (("Group A", 1, time(10), time(12)), ("Group B", 3, time(14), time(16)))
RUNNING_PER_GROUP, PLANNED_PER_GROUP = 4, 2
NAMES = (
    "Amira Khan", "Ben Carter", "Chloe Evans", "Daniel Osei", "Ella Morris", "Farah Ali",
    "George Hill", "Hana Sato", "Isaac Reid", "Jade Lewis", "Kofi Mensah", "Lucy Ward",
)  # fmt: skip


class Command(BaseCommand):
    help = "Seed the real programs from apps/delivery/seed/programs/*.json, with demo cohorts."

    def add_arguments(self, parser):
        parser.add_argument("--only", nargs="*", default=None, help="Program keys to seed, e.g. PCP MM")
        parser.add_argument("--dir", default=str(SEED_DIR), help="Folder with the program files")
        parser.add_argument("--by", default=None, help="Email of the staff member recorded as the author")
        parser.add_argument("--offline", action="store_true", help="Don't look standards up online")

    def handle(self, *args, **opts):
        from apps.identity.models import User

        specs = _load(Path(opts["dir"]), opts["only"])
        users = User.objects.filter(is_active=True, is_staff=True)
        if opts["by"]:
            by = users.filter(email=opts["by"].strip().lower()).first()
            if by is None:
                raise CommandError(f"{opts['by']} isn't an active staff member.")
        else:
            by = users.filter(is_superuser=True).order_by("created_at").first()
            if by is None:
                raise CommandError("No superuser found. Pass --by with an active staff member's email.")
        for spec in specs:
            # demo people are never told anything: no notices, no email, whatever the templates say
            with tenant_context(user_id=by.id, staff=True), notify.muted():
                self._one(spec, by=by, offline=opts["offline"])
        self.stdout.write(
            "Offers are off, at placeholder prices: set prices and switch them on in Console > Programs > Offers."
        )

    def _one(self, spec: dict, *, by, offline: bool) -> None:
        from apps.catalog.models import Course

        if Course.objects.filter(slug=spec["slug"]).exists():
            self.stdout.write(f"{spec['key']}: already there, skipped.")
            return
        try:
            with transaction.atomic():  # all of a program, or none of it
                note = Seeder(spec, by=by, offline=offline).run()
        except ServiceError as e:
            raise CommandError(f"{spec['key']}: {e.message} {e.details or ''}".strip()) from None
        self.stdout.write(self.style.SUCCESS(f"{spec['key']}: seeded. {note}"))


def _load(folder: Path, only: list[str] | None) -> list[dict]:
    if not folder.is_dir():
        raise CommandError(f"No folder {folder}.")
    specs = []
    for path in sorted(folder.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        missing = {"key", "slug", "title", "modules"} - set(spec)
        if missing:
            raise CommandError(f"{path.name} is missing {', '.join(sorted(missing))}.")
        specs.append(spec)
    if only:
        wanted = {k.upper() for k in only}
        unknown = wanted - {s["key"].upper() for s in specs}
        if unknown:
            raise CommandError(f"No file for {', '.join(sorted(unknown))}.")
        specs = [s for s in specs if s["key"].upper() in wanted]
    return specs


def _first_monday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7)


def intakes(months: list[int], today: date, weeks: int) -> tuple[date, date]:
    """(running start, planned start). The running cohort is the latest intake at least three
    weeks old with two weeks still to teach; when no intake fits a program this short, it
    started on the Monday three weeks ago. The planned one is the next intake after today."""
    starts = sorted(_first_monday(y, m) for y in (today.year - 1, today.year, today.year + 1) for m in months)
    fits = [d for d in starts if d <= today - timedelta(days=21) and d + timedelta(weeks=weeks - 2) > today]
    three_weeks_ago = today - timedelta(days=21)
    running = max(fits) if fits else three_weeks_ago - timedelta(days=three_weeks_ago.weekday())
    planned = min(d for d in starts if d > today)
    return running, planned


def total_weeks(spec: dict) -> int:
    return sum(m["weeks"] if isinstance(m["weeks"], int) else len(m["weeks"]) for m in spec["modules"])


class Seeder:
    def __init__(self, spec: dict, *, by, offline: bool):
        self.spec, self.by, self.offline = spec, by, offline
        self.key = spec["key"].upper()
        self.ksb_codes: dict = {}  # lecture_key -> KSB codes the source maps

    def run(self) -> str:
        program = self.program()
        standard = self.standard()
        self.settings(program, standard)
        self.offers(program)
        tutor = self.tutor()
        months = self.spec.get("intake_months") or [2, 6, 10]
        running_on, planned_on = intakes(months, timezone.localdate(), total_weeks(self.spec))
        learners = iter(self.learners(len(GROUPS) * (RUNNING_PER_GROUP + PLANNED_PER_GROUP)))
        running = self.cohort(program, running_on, tutor, learners, RUNNING_PER_GROUP, running=True)
        self.cohort(program, planned_on, tutor, learners, PLANNED_PER_GROUP, running=False)
        self.activity(running, tutor)
        return "No KSB standard yet: import it in the console." if standard is None else ""

    # ------------------------------------------------------------ content
    def program(self):
        from apps.catalog import services
        from apps.catalog.models import Course

        s = self.spec
        course = services.create_course(
            title=s["title"], slug=s["slug"], ownership=Course.Ownership.PLATFORM, created_by=self.by,
            kind=Course.Kind.PROGRAM, in_subscription=False, subtitle=s.get("subtitle", "")[:240],
            level=s.get("level", Course.Level.ALL), description=f"<p>{s.get('subtitle', '')}</p>",
        )  # fmt: skip
        version = course.versions.get(number=1)
        for m in s["modules"]:
            module = services.add_module(version=version, title=m["title"])
            weeks = m["weeks"]
            if isinstance(weeks, int):  # n weeks of the standard week
                weeks = [{"title": f"Week {n}", "components": WEEK_TEMPLATE} for n in range(1, weeks + 1)]
            for n, week in enumerate(weeks, start=1):
                section = services.add_section(version=version, title=week["title"], module=module)
                for c in week["components"]:
                    self.component(services, section, c, module=m["title"], week=n)
        services.submit(version=version, by=self.by)
        course.refresh_from_db()
        return course

    def component(self, services, section, c: dict, *, module: str, week: int) -> None:
        from apps.catalog.models import Lecture

        fill = {"module": module, "week": week}
        fields = {"expected_otj_min": c.get("otj_min", 0), "cpd_min": c.get("cpd_min", 0)}
        if c["kind"] == Lecture.Kind.ARTICLE or c.get("body"):  # live sessions carry their purpose
            fields["body"] = c["body"].format(**fill)
        lecture = services.add_lecture(
            section=section, kind=c["kind"], title=c["title"].format(**fill), **fields
        )
        if c["kind"] == Lecture.Kind.ASSIGNMENT:
            services.update_assignment(
                assignment=lecture.assignment, instructions=c["instructions"].format(**fill)
            )
        if c.get("ksbs"):
            self.ksb_codes[lecture.lecture_key] = c["ksbs"]

    def standard(self):
        """The program's KSB standard: already imported, given in the file, or looked up on
        the standards feed. None when none can be had (staff import it later)."""
        from apps.catalog import ksb_import
        from apps.catalog.models import KsbStandard

        given = self.spec.get("standard")
        if not given:
            return None
        found = KsbStandard.objects.filter(code=given["code"].upper()).order_by("-created_at").first()
        if found is not None:
            return found
        try:
            if given.get("items"):
                parsed = ksb_import.parse(given)
            elif self.offline:
                return None
            else:
                parsed = ksb_import.fetch(given["code"])
        except ServiceError:
            return None  # feed down or code unknown: the program still seeds
        return ksb_import.save_standard(parsed, by=self.by)[0]

    def settings(self, program, standard) -> None:
        from apps.catalog import ksb_import
        from apps.delivery import services

        otj = self.spec.get("otj") or {}
        services.save_program_settings(
            program_id=program.id, by=self.by, ksb_standard_id=standard.id if standard else None,
            otj_target_mode=otj.get("mode"), otj_target_value=otj.get("value"),
        )  # fmt: skip
        if standard is None:
            return
        items = dict(standard.items.values_list("code", "id"))
        for key, codes in self.ksb_codes.items():
            ids = [items[c] for c in codes if c in items]
            if ids:
                ksb_import.set_component_ksbs(
                    program=program, lecture_key=key, item_ids=ids, standard_id=standard.id
                )

    def offers(self, program) -> None:
        """Whole program live and recorded, and each module recorded, at one placeholder tier
        (client question #33), switched OFF: nothing goes on sale until the provider sets real
        prices and switches the offers on in the console."""
        from apps.commerce.models import PriceTier, ProgramOffer
        from apps.commerce.programs import save_offer

        tiers = PriceTier.objects.filter(is_active=True, gbp_minor__gt=0)
        tier = (
            tiers.filter(name=self.spec.get("price_tier", "")).first() or tiers.order_by("-gbp_minor").first()
        )
        if tier is None:
            return  # no prices set up yet: offers wait for the provider
        save_offer(program=program, mode=ProgramOffer.Mode.LIVE, tier_id=tier.id, is_active=False)
        save_offer(program=program, mode=ProgramOffer.Mode.RECORDED, tier_id=tier.id, is_active=False)
        modules = program.live_version.modules.order_by("position").values_list("module_key", flat=True)
        for key in modules:
            save_offer(
                program=program,
                mode=ProgramOffer.Mode.RECORDED,
                module_key=key,
                tier_id=tier.id,
                is_active=False,
            )

    # ------------------------------------------------------------ people and cohorts
    def tutor(self):
        """Always the demo tutor, so no real staff member's teaching views fill with demo
        learners. It gets a role that may only teach groups: an existing one, else a new one."""
        from apps.identity.models import StaffRole, StaffRoleAssignment

        tutor = self.user(f"tutor@{DOMAIN}", "Tia Tutor", is_staff=True)
        if not tutor.is_staff:
            raise CommandError(
                f"tutor@{DOMAIN} exists but isn't staff. Make it staff, or remove it, then run again."
            )
        # a role that ONLY teaches: never hand the demo tutor an admin role that also teaches
        role = StaffRole.objects.filter(permissions=["groups.teach"]).order_by("created_at").first()
        if role is None:
            name = "Tutor" if not StaffRole.objects.filter(name="Tutor").exists() else "Group tutor (demo)"
            if StaffRole.objects.filter(name=name).exists():
                raise CommandError(
                    f"A staff role named {name} exists with other permissions. Rename it, then run again."
                )
            role = StaffRole.objects.create(
                name=name, permissions=["groups.teach"], description="Teaches program groups."
            )
        StaffRoleAssignment.objects.get_or_create(user=tutor, role=role)
        return tutor

    @staticmethod
    def user(email: str, name: str, **extra):
        from apps.identity.models import User

        user, made = User.objects.get_or_create(email=email, defaults={"full_name": name, **extra})
        if made:
            user.set_unusable_password()  # demo people sign in only after a password reset
            user.save(update_fields=["password"])
        return user

    def learners(self, n: int) -> list:
        prefix = self.key.lower()
        return [
            self.user(f"{prefix}.learner{i:02d}@{DOMAIN}", NAMES[(i - 1) % len(NAMES)])
            for i in range(1, n + 1)
        ]

    def cohort(self, program, start: date, tutor, learners, per_group: int, *, running: bool):
        from apps.delivery import services
        from apps.delivery.models import Cohort
        from apps.delivery.sessions import plan_sessions
        from apps.learning.models import Enrollment
        from apps.learning.placement import place

        cohort = services.create_cohort(
            program_id=program.id, name=f"{start:%B %Y} intake", start_date=start, calendar=None,
            capacity=len(GROUPS) * 12, by=self.by,
        )  # fmt: skip
        if running:
            services.update_cohort(cohort=cohort, status=Cohort.Status.OPEN)
            cohort = services.update_cohort(cohort=cohort, status=Cohort.Status.RUNNING)
        joined = timezone.make_aware(datetime.combine(start, time(9)))
        for name, weekday, starts, ends in GROUPS:
            group = services.save_group(cohort=cohort, name=name, weekday=weekday, starts_at=starts,
                                        ends_at=ends, capacity=12, tutor_id=tutor.id)  # fmt: skip
            placed = place(group_id=group.id, users=[next(learners) for _ in range(per_group)])
            if running:  # they joined when the cohort started
                Enrollment.objects.filter(pk__in=[e.pk for e in placed]).update(enrolled_at=joined)
            plan_sessions(group=group, by=self.by, sync=False)
        return cohort

    def activity(self, cohort, tutor) -> None:
        """The running cohort's past: attendance (one learner missed some sessions), the
        readings of past weeks (some learners are behind), and off-the-job logs (one
        approved, one waiting for the tutor)."""
        from apps.catalog.models import Lecture
        from apps.delivery.models import LiveSession
        from apps.learning import live, records
        from apps.learning.models import Enrollment
        from apps.learning.services import complete_lecture

        now = timezone.now()
        for group in cohort.groups.order_by("name"):
            people = list(
                Enrollment.objects.filter(group=group).select_related("course").order_by("user__email")
            )
            past = list(LiveSession.objects.filter(group=group, starts_at__lte=now).order_by("starts_at"))
            for n, session in enumerate(past):
                marks = {e.id: 0 if i == len(people) - 1 and n % 2 else session.duration_min
                         for i, e in enumerate(people)}  # fmt: skip
                live.mark_session(session=session, marks=marks, by=tutor)
            sections = Lecture.objects.filter(
                version_id=cohort.program.live_version_id, lecture_key__in=[s.lecture_key for s in past]
            ).values_list("section_id", flat=True)
            readings = list(
                Lecture.objects.filter(section_id__in=list(sections), kind=Lecture.Kind.ARTICLE)
                .order_by("section__position").values_list("lecture_key", flat=True)
            )  # fmt: skip
            for i, e in enumerate(people):
                for key in readings[: max(len(readings) - i, 0)]:  # each learner a little further behind
                    complete_lecture(enrollment=e, lecture_key=key)
                for k, day in enumerate(
                    (cohort.start_date + timedelta(days=4), cohort.start_date + timedelta(days=11))
                ):
                    entry = records.log_hours(enrollment=e, occurred_on=day, minutes=90,
                                              note="Used this week's methods on a live work project.")  # fmt: skip
                    if k == 0:
                        records.decide(entry=entry, approve=True, note="", by=tutor)
