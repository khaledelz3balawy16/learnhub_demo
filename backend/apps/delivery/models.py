"""Delivery: WHEN and WITH WHOM a program is taught (Programs plan D2-D4, D16).

Postgres schema: delivery. Sits between catalog and learning:
    catalog (content) <- delivery (schedule) <- learning (enrolments)

Content is never copied here. A cohort schedules the program's live version:
    Cohort ─ CohortModule (optional start date per module, by module_key)
           ─ Group (learners, tutor, weekly timetable)
           ─ Closure (weeks off for this cohort; NULL cohort = provider-wide)
    Holiday (GOV.UK bank holidays per division; synced, never hard-coded)

Week dates are calculated (delivery.calendar), not stored, so a republished program or
a new closure can never leave stale dates behind.

All tables are provider reference data: readable by any signed-in request (the API
decides what each person sees), written only by staff (console) and platform jobs.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.db import table
from core.models import BaseModel

SCHEMA = "delivery"
User = settings.AUTH_USER_MODEL


class Division(models.TextChoices):
    """GOV.UK bank-holiday divisions (https://www.gov.uk/bank-holidays.json)."""

    ENGLAND_WALES = "england-and-wales", "England and Wales"
    SCOTLAND = "scotland", "Scotland"
    NORTHERN_IRELAND = "northern-ireland", "Northern Ireland"


class ProgramSetting(BaseModel):
    """Per-program delivery rules (M19+): created on first save; missing = the defaults.
    Later milestones add their settings here (additive columns)."""

    class OtjTarget(models.TextChoices):
        NONE = "none", "No target"
        HOURS_PER_WEEK = "hours_per_week", "Hours per teaching week"
        TOTAL_HOURS = "total_hours", "Total hours over the cohort"

    class SwapCutoff(models.TextChoices):
        NONE = "none", "No cut-off"
        PROGRESS = "progress_pct", "Progress reached (%)"
        WEEK = "week", "Week of the cohort reached"

    program = models.OneToOneField(
        "catalog.Course", on_delete=models.CASCADE, related_name="delivery_setting"
    )
    ksb_standard = models.ForeignKey(
        "catalog.KsbStandard", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    otj_target_mode = models.CharField(max_length=20, choices=OtjTarget.choices, default=OtjTarget.NONE)
    otj_target_value = models.DecimalField(max_digits=7, decimal_places=1, default=0)
    otj_amber_pct = models.PositiveSmallIntegerField(default=80)  # below this share of expected: at risk
    otj_daily_cap_min = models.PositiveSmallIntegerField(default=480)  # most a learner may log per day
    # M22 (D8, D11): company seat orders and seat swaps
    min_seats_per_line = models.PositiveSmallIntegerField(default=2, db_default=2)
    swap_cutoff_mode = models.CharField(
        max_length=12, choices=SwapCutoff.choices, default=SwapCutoff.NONE, db_default=SwapCutoff.NONE
    )
    swap_cutoff_value = models.PositiveSmallIntegerField(default=0, db_default=0)  # % or week number
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = table(SCHEMA, "program_settings")
        constraints = [
            models.CheckConstraint(condition=Q(otj_amber_pct__lte=100), name="ck_program_amber_pct"),
            models.CheckConstraint(condition=Q(otj_target_value__gte=0), name="ck_program_otj_target"),
        ]


class Cohort(BaseModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        OPEN = "open", "Open for enrolment"
        RUNNING = "running", "Running"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    program = models.ForeignKey("catalog.Course", on_delete=models.PROTECT, related_name="cohorts")
    name = models.CharField(max_length=120)  # e.g. "January 2027"
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # last teaching day, refreshed from the calendar
    calendar = models.CharField(max_length=24, choices=Division.choices, default=Division.ENGLAND_WALES)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    capacity = models.PositiveIntegerField(null=True, blank=True)  # NULL = no cohort-wide limit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = table(SCHEMA, "cohorts")
        constraints = [
            models.UniqueConstraint(fields=["program", "name"], name="uq_cohort_name_per_program"),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="ck_cohort_dates",
            ),
        ]
        indexes = [models.Index(fields=["program", "-start_date"], name="ix_cohorts_program")]

    def __str__(self) -> str:
        return self.name


class CohortModule(BaseModel):
    """A per-cohort start date for one module (D16: optional; otherwise the module starts
    the teaching week after the previous one). Keyed by module_key, so it survives
    republishing."""

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="module_dates")
    module_key = models.UUIDField()
    starts_on = models.DateField()

    class Meta:
        db_table = table(SCHEMA, "cohort_modules")
        constraints = [models.UniqueConstraint(fields=["cohort", "module_key"], name="uq_cohort_module")]


class Group(BaseModel):
    """Learners inside a cohort (D3). Every group studies the same modules; each has its
    own tutor and weekly timetable."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=80)
    tutor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)  # 0 = Monday ... 6 = Sunday
    starts_at = models.TimeField(null=True, blank=True)  # provider local time
    ends_at = models.TimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = table(SCHEMA, "groups")
        constraints = [
            models.UniqueConstraint(fields=["cohort", "name"], name="uq_group_name_per_cohort"),
            models.CheckConstraint(
                condition=Q(weekday__isnull=True) | Q(weekday__lte=6), name="ck_group_weekday"
            ),
            models.CheckConstraint(
                condition=Q(starts_at__isnull=True)
                | Q(ends_at__isnull=True)
                | Q(ends_at__gt=models.F("starts_at")),
                name="ck_group_times",
            ),
        ]
        indexes = [models.Index(fields=["tutor"], name="ix_groups_tutor", condition=Q(tutor__isnull=False))]

    def __str__(self) -> str:
        return self.name


class Holiday(BaseModel):
    division = models.CharField(max_length=24, choices=Division.choices)
    date = models.DateField()
    title = models.CharField(max_length=120)

    class Meta:
        db_table = table(SCHEMA, "holidays")
        constraints = [models.UniqueConstraint(fields=["division", "date"], name="uq_holiday_day")]


class Closure(BaseModel):
    """Days the provider does not teach (e.g. a Christmas closure). cohort NULL = every cohort."""

    cohort = models.ForeignKey(
        Cohort, on_delete=models.CASCADE, null=True, blank=True, related_name="closures"
    )
    starts_on = models.DateField()
    ends_on = models.DateField()
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = table(SCHEMA, "closures")
        constraints = [
            models.CheckConstraint(condition=Q(ends_on__gte=models.F("starts_on")), name="ck_closure_dates"),
        ]
        indexes = [models.Index(fields=["cohort", "starts_on"], name="ix_closures_cohort")]


# ---------------------------------------------------------------- live teaching (M20, plan D17, D18, D24)
class MeetingFields(models.Model):
    """What a live event needs, whoever hosts it: a Teams meeting the app created (Graph), or
    a link staff pasted (manual fallback). Only the attendee join URL is stored: the
    organiser's host link is never kept or sent."""

    class Provider(models.TextChoices):
        MANUAL = "manual", "Link added by staff"
        TEAMS = "teams", "Microsoft Teams"

    class Recording(models.TextChoices):
        NONE = "none", "No recording"
        PENDING = "pending", "Being copied"
        READY = "ready", "Ready"
        FAILED = "failed", "Could not copy"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    starts_at = models.DateTimeField()  # UTC
    duration_min = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    provider = models.CharField(max_length=8, choices=Provider.choices, default=Provider.MANUAL)
    join_url = models.URLField(max_length=1000, blank=True)
    teams_meeting_id = models.CharField(max_length=512, blank=True)
    teams_organizer = models.CharField(max_length=254, blank=True)
    meeting_synced_at = models.DateTimeField(null=True, blank=True)  # Teams meeting matches our times
    attendance_synced_at = models.DateTimeField(null=True, blank=True)
    recording = models.ForeignKey(
        "catalog.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    recording_status = models.CharField(max_length=8, choices=Recording.choices, default=Recording.NONE)
    recording_attempts = models.PositiveSmallIntegerField(default=0)
    transcript = models.TextField(blank=True)  # WebVTT from Teams, when there is one
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        abstract = True


class LiveSession(BaseModel, MeetingFields):
    """One live component taught to one group (D3): dated from the group's weekday inside
    the component's week. One per (group, component); never deleted, only cancelled."""

    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="sessions")
    lecture_key = models.UUIDField()  # the program component (kind live_session)
    title = models.CharField(max_length=200)

    class Meta:
        db_table = table(SCHEMA, "live_sessions")
        constraints = [
            models.UniqueConstraint(fields=["group", "lecture_key"], name="uq_session_per_group"),
            models.CheckConstraint(
                condition=Q(duration_min__gte=5, duration_min__lte=720), name="ck_session_len"
            ),
        ]
        indexes = [
            models.Index(fields=["group", "starts_at"], name="ix_sessions_group"),
            models.Index(fields=["starts_at"], name="ix_sessions_teams_due",
                         condition=Q(provider="teams", status="scheduled")),
        ]  # fmt: skip

    def __str__(self) -> str:
        return self.title


class Workshop(BaseModel, MeetingFields):
    """An optional live event outside the timetable (D24): booked, with a capacity, and it
    counts towards OTJ and CPD when attended."""

    program = models.ForeignKey("catalog.Course", on_delete=models.PROTECT, related_name="workshops")
    cohort = models.ForeignKey(
        Cohort, on_delete=models.PROTECT, null=True, blank=True, related_name="workshops"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)  # plain text
    capacity = models.PositiveIntegerField(null=True, blank=True)  # NULL = no limit
    expected_otj_min = models.PositiveIntegerField(default=0)
    cpd_min = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = table(SCHEMA, "workshops")
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_min__gte=5, duration_min__lte=720), name="ck_workshop_len"
            ),
            models.CheckConstraint(condition=Q(expected_otj_min__lte=1440), name="ck_workshop_otj"),
        ]
        indexes = [
            models.Index(fields=["program", "starts_at"], name="ix_workshops_program"),
            models.Index(fields=["starts_at"], name="ix_workshops_teams_due",
                         condition=Q(provider="teams", status="scheduled")),
        ]  # fmt: skip

    def __str__(self) -> str:
        return self.title
