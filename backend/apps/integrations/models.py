"""HR system integration (M17): a company connects its Breathe HR account and LearnHub keeps
people, departments, training records and approved leave in step with it.

Postgres schema: integrations
RLS (core.rls): every table company_only(); composite foreign keys (org_id, x_id) ->
(org_id, id) are added in migration 0002 so a row can never point at another company's.

Nothing here is ever written back to Breathe. The API key is stored only encrypted
(integrations.secrets) and never leaves the server.
"""

from django.conf import settings
from django.db import models

from core.db import table
from core.models import TenantModel

SCHEMA = "integrations"


class HrConnection(TenantModel):
    """One HR system per company."""

    class Provider(models.TextChoices):
        BREATHE = "breathe", "Breathe HR"

    class Status(models.TextChoices):
        ACTIVE = "active", "Connected"
        ATTENTION = "attention", "Needs attention"
        PAUSED = "paused", "Paused"
        DISABLED = "disabled", "Disconnected"

    FEATURES = ("departments", "managers", "training", "leave")

    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.BREATHE)
    external_account_id = models.CharField(max_length=64)
    account_name = models.CharField(max_length=200, blank=True)
    base_url = models.CharField(max_length=200)
    secret_ciphertext = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    enabled_features = models.JSONField(default=list)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        db_table = table(SCHEMA, "hr_connections")
        constraints = [
            models.UniqueConstraint(fields=["org"], name="uq_hrconn_org"),
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrconn_org_id"),
            models.UniqueConstraint(fields=["provider", "external_account_id"], name="uq_hrconn_account"),
        ]

    def has(self, feature: str) -> bool:
        return feature in (self.enabled_features or [])


class ExternalPerson(TenantModel):
    """An employee as Breathe reports them, and who they are in LearnHub (if anyone yet)."""

    class Mapping(models.TextChoices):
        PENDING = "pending", "To review"
        MATCHED = "matched", "Linked"
        INVITED = "invited", "Invited"
        IGNORED = "ignored", "Ignored"

    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="people", db_index=False
    )
    external_employee_id = models.CharField(max_length=64)
    email = models.CharField(max_length=254, blank=True)
    display_name = models.CharField(max_length=200)
    job_title = models.CharField(max_length=120, blank=True)
    department_external_id = models.CharField(max_length=64, blank=True)
    department_name = models.CharField(max_length=160, blank=True)
    manager_external_id = models.CharField(max_length=64, blank=True)
    employment_status = models.CharField(max_length=40, blank=True)
    start_date = models.DateField(null=True, blank=True)
    contracted_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    working_pattern = models.CharField(max_length=120, blank=True)
    member = models.ForeignKey(
        "org.OrgMember", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    invite = models.ForeignKey(
        "org.Invite", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    mapping_status = models.CharField(max_length=10, choices=Mapping.choices, default=Mapping.PENDING)
    is_leaver = models.BooleanField(default=False)  # flagged only, never removed (client question 27)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = table(SCHEMA, "external_people")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrperson_org_id"),
            models.UniqueConstraint(fields=["connection", "external_employee_id"], name="uq_hrperson_ext"),
        ]
        indexes = [
            models.Index(fields=["org", "display_name", "id"], name="ix_hrperson_name"),
            models.Index(fields=["org", "mapping_status"], name="ix_hrperson_status"),
            models.Index(fields=["member"], name="ix_hrperson_member"),
        ]


class ExternalDepartment(TenantModel):
    class Link(models.TextChoices):
        PENDING = "pending", "Not linked"
        LINKED = "linked", "Linked"
        IGNORED = "ignored", "Ignored"

    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="departments", db_index=False
    )
    external_department_id = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    unit = models.ForeignKey(
        "org.OrgUnit", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    status = models.CharField(max_length=8, choices=Link.choices, default=Link.PENDING)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = table(SCHEMA, "external_departments")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrdept_org_id"),
            models.UniqueConstraint(fields=["connection", "external_department_id"], name="uq_hrdept_ext"),
        ]
        indexes = [models.Index(fields=["unit"], name="ix_hrdept_unit")]


class HrTrainingMap(TenantModel):
    """A Breathe training title counts as evidence for one LearnHub requirement."""

    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="training_maps", db_index=False
    )
    title_key = models.CharField(max_length=200)  # lower-cased, trimmed title
    title = models.CharField(max_length=200)
    requirement = models.ForeignKey("compliance.Requirement", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = table(SCHEMA, "hr_training_maps")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrmap_org_id"),
            models.UniqueConstraint(fields=["connection", "title_key"], name="uq_hrmap_title"),
        ]
        indexes = [models.Index(fields=["requirement"], name="ix_hrmap_requirement")]


class ExternalTrainingRecord(TenantModel):
    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="training", db_index=False
    )
    external_training_id = models.CharField(max_length=64)
    external_employee_id = models.CharField(max_length=64)
    person = models.ForeignKey(
        ExternalPerson, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    title = models.CharField(max_length=200)
    title_key = models.CharField(max_length=200)
    category = models.CharField(max_length=120, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=40, blank=True)
    certificate_ref = models.CharField(max_length=120, blank=True)
    # plain FK: completion_records has no UNIQUE (org_id, id) to point a composite key at
    applied_record = models.ForeignKey(
        "compliance.CompletionRecord", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = table(SCHEMA, "external_training_records")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrtrain_org_id"),
            models.UniqueConstraint(fields=["connection", "external_training_id"], name="uq_hrtrain_ext"),
        ]
        indexes = [
            models.Index(fields=["org", "title_key"], name="ix_hrtrain_title"),
            models.Index(fields=["person"], name="ix_hrtrain_person"),
        ]


class ExternalLeave(TenantModel):
    """Approved leave only: shown as "On leave until …" (client question 28)."""

    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="leave", db_index=False
    )
    person = models.ForeignKey(
        ExternalPerson, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    external_employee_id = models.CharField(max_length=64)
    source_ref = models.CharField(max_length=64)
    starts_on = models.DateField()
    ends_on = models.DateField()
    leave_type = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = table(SCHEMA, "external_leave")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrleave_org_id"),
            models.UniqueConstraint(fields=["connection", "source_ref"], name="uq_hrleave_ref"),
        ]
        indexes = [models.Index(fields=["org", "person", "ends_on"], name="ix_hrleave_person")]


class HrSyncRun(TenantModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    connection = models.ForeignKey(
        HrConnection, on_delete=models.CASCADE, related_name="runs", db_index=False
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    trigger = models.CharField(max_length=10, default="manual")  # manual | hourly | connect
    idempotency_key = models.CharField(max_length=120)
    counts = models.JSONField(default=dict)
    error_code = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = table(SCHEMA, "hr_sync_runs")
        constraints = [
            models.UniqueConstraint(fields=["org", "id"], name="uq_hrrun_org_id"),
            models.UniqueConstraint(fields=["connection", "idempotency_key"], name="uq_hrrun_key"),
        ]
        indexes = [models.Index(fields=["connection", "-created_at"], name="ix_hrrun_recent")]
