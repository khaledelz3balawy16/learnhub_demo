"""Typed API shapes for the HR system page. Every name starts with Hr (names are unique
project-wide). No shape ever carries the API key."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from ninja import Schema


class HrConnectionOut(Schema):
    id: UUID
    provider: str
    account_name: str
    external_account_id: str
    environment: Literal["production", "sandbox"]
    status: str
    features: list[str]
    last_verified_at: datetime | None
    last_sync_at: datetime | None
    last_error: str


class HrRunCountsOut(Schema):
    """What one sync read and changed (all zero until a run completes)."""

    people: int = 0
    new_people: int = 0
    leavers: int = 0
    departments: int = 0
    training: int = 0
    applied: int = 0
    leave: int = 0
    to_review: int = 0


class HrRunOut(Schema):
    id: UUID
    status: str
    trigger: str
    counts: HrRunCountsOut
    error_message: str
    triggered_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class HrCountsOut(Schema):
    people: int
    to_review: int
    linked: int
    invited: int
    leavers: int
    departments: int
    departments_linked: int
    training: int
    training_applied: int
    on_leave: int


class HrOverviewOut(Schema):
    configured: bool  # the server has an encryption key, so companies can connect
    can_manage: bool  # owner / admin; managers see the page read-only
    connection: HrConnectionOut | None
    counts: HrCountsOut | None
    latest_run: HrRunOut | None


class HrConnectIn(Schema):
    api_key: str
    environment: Literal["production", "sandbox"] = "production"
    features: list[str] = ["departments", "managers", "training", "leave"]


class HrKeyIn(Schema):
    api_key: str


class HrFeaturesIn(Schema):
    features: list[str]


class HrPauseIn(Schema):
    paused: bool


class HrMemberRef(Schema):
    member_id: UUID
    name: str
    email: str


class HrPersonOut(Schema):
    id: UUID
    external_employee_id: str
    name: str
    email: str
    job_title: str
    department: str
    employment_status: str
    start_date: date | None
    contracted_hours: float | None
    working_pattern: str
    status: str  # pending | matched | invited | ignored
    is_leaver: bool
    member: HrMemberRef | None
    suggestion: HrMemberRef | None  # same email as an unlinked member: an admin confirms it


class HrPersonPage(Schema):
    items: list[HrPersonOut]
    next_cursor: str | None


class HrMatchIn(Schema):
    member_id: UUID


class HrInviteIn(Schema):
    role: str = "learner"
    unit_id: UUID | None = None
    job_role_id: UUID | None = None


class HrInviteOut(Schema):
    invite_id: UUID
    email: str


class HrDepartmentOut(Schema):
    id: UUID
    external_department_id: str
    name: str
    status: str
    unit_id: UUID | None
    unit_name: str | None
    people: int


class HrDepartmentLinkIn(Schema):
    unit_id: UUID | None = None
    create: bool = False  # make a new department unit named after the Breathe department


class HrTrainingTitleOut(Schema):
    title: str
    records: int
    applied: int
    requirement_id: UUID | None
    requirement_name: str | None


class HrTrainingMapIn(Schema):
    title: str
    requirement_id: UUID | None = None  # None removes the mapping


class HrTrainingMapOut(Schema):
    applied: int


class HrTrainingRecordOut(Schema):
    id: UUID
    person_name: str | None
    title: str
    completion_date: date | None
    status: str
    applied: bool


class HrLeaveOut(Schema):
    member_id: UUID
    starts_on: date
    ends_on: date
    leave_type: str
    current: bool


class HrMemberLinkOut(Schema):
    linked: bool
    provider: str | None = None
    external_employee_id: str | None = None
    job_title: str | None = None
    department: str | None = None
    employment_status: str | None = None
    start_date: date | None = None
    is_leaver: bool = False
    leave: HrLeaveOut | None = None
