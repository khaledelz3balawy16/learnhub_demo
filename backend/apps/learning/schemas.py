"""Pydantic In/Out schemas for the learning API (my learning, player, quizzes,
assignments, notes, certificates)."""

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from ninja import Field, Schema

from apps.catalog.schemas import PlaybackOut, VideoMomentOut, VideoPartOut
from apps.identity.schemas import OkOut  # noqa: F401 - shared response shape


class MyCourseWeek(Schema):
    number: int
    title: str
    starts_on: date
    ends_on: date


class MyCourse(Schema):
    enrollment_id: UUID
    course_id: UUID
    slug: str
    title: str
    thumbnail_url: str
    instructors: list[str]
    progress_pct: float
    status: str
    source: str
    org_id: UUID | None  # set: assigned by a company
    org_name: str | None
    enrolled_at: datetime
    last_accessed_at: datetime | None
    last_lecture_key: UUID | None
    access_expires_at: datetime | None
    certificate_id: UUID | None
    # programs (M18), for a learner placed in a group
    group_name: str | None = None
    cohort_name: str | None = None
    next_week: MyCourseWeek | None = None


class MyCoursePage(Schema):
    items: list[MyCourse]
    next_cursor: str | None


class PlayerLecture(Schema):
    key: UUID
    title: str
    kind: str
    duration_sec: int
    completed: bool
    position_sec: int
    locked: bool = False  # the prerequisite lesson isn't finished yet
    prerequisite_key: UUID | None = None
    prerequisite_title: str | None = None
    module_locked: bool = False  # programs (M21): in a module the learner hasn't bought


class PlayerDayOff(Schema):
    date: date
    title: str


class PlayerSection(Schema):
    id: UUID
    title: str
    lectures: list[PlayerLecture]
    # programs only (M18): the week's module and, when the learner is in a group, its dates
    module_id: UUID | None = None
    week_number: int | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    days_off: list[PlayerDayOff] = []


class PlayerModule(Schema):
    id: UUID
    title: str
    description: str
    starts_on: date | None = None
    ends_on: date | None = None
    owned: bool = True  # M21: False when the learner bought other modules only


class PlayerGroup(Schema):
    name: str
    cohort_name: str
    weekday: int | None = None  # 0 = Monday
    starts_at: time | None = None
    ends_at: time | None = None
    tutor_name: str | None = None


class PlayerOut(Schema):
    enrollment_id: UUID
    course_id: UUID
    slug: str
    title: str
    progress_pct: float
    status: str
    last_lecture_key: UUID | None
    certificate_id: UUID | None
    sections: list[PlayerSection]
    kind: str = "short"  # "program": sections are weeks grouped by `modules`
    modules: list[PlayerModule] = []
    group: PlayerGroup | None = None
    current_section_id: UUID | None = None  # the week running today (placed program learners)


class LiveOut(Schema):
    starts_at: datetime | None
    duration_min: int | None
    join_url: str | None  # appears shortly before the start (programs: setting learning.live_join_early_min)
    provider: str = "manual"
    status: str = "scheduled"  # programs: a cancelled group session says so
    join_early_min: int = 15


class ResourceOut(Schema):
    id: UUID
    title: str
    position: int
    kind: str
    filename: str
    size_bytes: int | None
    mime_type: str


class AttemptSummary(Schema):
    id: UUID
    attempt_no: int
    status: str
    score_pct: float | None
    passed: bool | None
    submitted_at: datetime | None


class LectureQuizOut(Schema):
    mode: str
    pass_mark_pct: int
    time_limit_sec: int | None
    max_attempts: int | None
    question_count: int
    attempts: list[AttemptSummary]


class SubmittedFile(Schema):
    filename: str
    size_bytes: int | None


class SubmissionOut(Schema):
    id: UUID
    attempt_no: int
    status: str
    submitted_at: datetime
    is_late: bool
    score: int | None
    passed: bool | None
    feedback: str
    text: str = ""
    url: str = ""
    files: list[SubmittedFile] = []


class RubricItem(Schema):
    criterion: str = ""
    points: int = 0


class LectureAssignmentOut(Schema):
    instructions: str
    max_score: int
    pass_score: int
    submission_types: list[str]
    due_at: datetime | None
    allow_late: bool
    rubric: list[RubricItem]
    submissions: list[SubmissionOut]


class LectureContent(Schema):
    key: UUID
    title: str
    kind: str
    duration_sec: int
    completed: bool
    position_sec: int
    prev_key: UUID | None
    next_key: UUID | None
    body: str = ""  # readings
    external_url: str = ""
    video: PlaybackOut | None = None  # signed playback
    parts: list[VideoPartOut] = []  # the video's named parts and key moments (from Bunny)
    moments: list[VideoMomentOut] = []
    live: LiveOut | None = None
    resources: list[ResourceOut] = []
    quiz: LectureQuizOut | None = None
    assignment: LectureAssignmentOut | None = None


class HeartbeatIn(Schema):
    lecture_key: UUID
    position_sec: int = Field(..., ge=0, le=86400)
    watched_sec: int = Field(..., ge=0, le=600)
    ended: bool = False  # the video reached its end: write now and say if it completed
    flush_now: bool = False  # pause/exit: save the exact playhead and buffered watch time now


class HeartbeatOut(Schema):
    ok: bool
    completed: bool  # this lecture is complete (always false until the video's end beat)


class LearnerOption(Schema):
    id: str
    body: str


class LearnerQuestion(Schema):
    """A question as the learner sees it: never the correct answers."""

    id: str
    kind: str
    prompt: str
    points: int
    options: list[LearnerOption] | None = None  # choice questions
    left: list[LearnerOption] | None = None  # matching: items to pair...
    right: list[str] | None = None  # ...with these (shuffled)
    blanks: int | None = None  # fill_blank: how many "___"


class LearnerQuiz(Schema):
    id: str
    time_limit_sec: int | None
    questions: list[LearnerQuestion]


class ReviewItem(Schema):
    """One question of a submitted attempt, self-contained so the review page can be
    reloaded: the prompt and choices come back with the result."""

    question_id: str
    kind: str
    prompt: str
    options: list[LearnerOption] = []
    points: float | None
    max: float
    explanation: str
    your_answer: Any = None
    correct_option_ids: list[str] | None = None


class AttemptOut(Schema):
    id: UUID
    attempt_no: int
    status: str
    started_at: datetime
    expires_at: datetime | None
    submitted_at: datetime | None
    score_pct: float | None
    passed: bool | None
    quiz: LearnerQuiz | None = None  # questions, while in progress (never with answers)
    review: list[ReviewItem] | None = None  # per question, only when the quiz allows revealing


class SubmitAnswersIn(Schema):
    answers: dict[str, Any] = Field(default_factory=dict)


class SubmissionIn(Schema):
    text: str = Field("", max_length=50000)
    url: str = Field("", max_length=500)
    asset_ids: list[UUID] = Field([], max_length=5)  # from submission-uploads


class SubmissionUploadIn(Schema):
    filename: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., gt=0)


class SubmissionUploadOut(Schema):
    asset_id: UUID
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int
    max_bytes: int


class NotePatchIn(Schema):
    timestamp_sec: int | None = Field(None, ge=0, le=86400)
    clear_timestamp: bool = False  # unpin the note from the video
    body: str | None = Field(None, min_length=1, max_length=10000)


class NoteIn(Schema):
    lecture_key: UUID
    timestamp_sec: int | None = Field(None, ge=0, le=86400)
    body: str = Field(..., min_length=1, max_length=10000)


class NoteOut(Schema):
    id: UUID
    lecture_key: UUID
    timestamp_sec: int | None
    body: str
    created_at: datetime


class CertificateOut(Schema):
    id: UUID
    verification_code: str
    course_id: UUID
    course_title: str
    recipient_name: str
    instructor_names: str
    cpd_hours: float | None
    issued_at: datetime
    org_id: UUID | None


class DownloadOut(Schema):
    url: str
    expires_in: int


class ProgressOut(Schema):
    progress_pct: float
    status: str


class VerifyOut(Schema):
    """Public certificate check: only safe fields."""

    verification_code: str
    recipient_name: str
    course_title: str
    cpd_hours: float | None
    issued_at: datetime
    is_revoked: bool
    expires_at: datetime | None = None
    is_expired: bool = False


# ---------------------------------------------------------------- program record (M19)
class LearnerOtjSummaryOut(Schema):
    counted_min: int
    pending_min: int
    expected_min: int | None
    target_min: int | None
    target_mode: str
    rag: str | None  # on_track | behind | at_risk | None (no target)
    daily_cap_min: int


class LearnerKsbOut(Schema):
    id: UUID
    code: str
    kind: str
    text: str
    status: str  # met | in_progress | not_started | not_mapped
    done: int
    total: int


class LearnerCpdModuleOut(Schema):
    module_key: UUID
    title: str
    earned_min: int
    available_min: int


class LearnerCpdOut(Schema):
    workshops_min: int = 0  # CPD from attended workshops (M20), included in earned_min
    earned_min: int
    available_min: int
    modules: list[LearnerCpdModuleOut]


class LearnerModuleCertificateOut(Schema):
    module_key: UUID
    module_title: str
    cpd_min: int
    verification_code: str
    issued_at: datetime


class LearnerRecordOut(Schema):
    enrollment_id: UUID
    program_title: str
    slug: str
    otj: LearnerOtjSummaryOut
    ksbs: list[LearnerKsbOut]
    cpd: LearnerCpdOut
    certificates: list[LearnerModuleCertificateOut]


class LearnerOtjEntryOut(Schema):
    id: UUID
    source: str
    minutes: int
    occurred_on: date
    status: str
    note: str
    decision_note: str


class LearnerOtjPageOut(Schema):
    items: list[LearnerOtjEntryOut]
    next_cursor: str | None


class LearnerOtjLogIn(Schema):
    occurred_on: date
    minutes: int = Field(..., ge=1, le=1440)
    note: str = Field(..., min_length=3, max_length=1000)


class LearnerIdOut(Schema):
    id: UUID


# ---------------------------------------------------------------- live sessions and workshops (M20)
class LearnerSessionOut(Schema):
    id: UUID
    lecture_key: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    status: str
    provider: str
    join_url: str | None  # only while the join window is open
    has_link: bool
    recording: PlaybackOut | None
    attended_min: int | None


class LearnerSessionsOut(Schema):
    items: list[LearnerSessionOut]
    group_name: str | None
    join_early_min: int
    present_min: int  # minutes that count as attended


class LearnerWorkshopOut(Schema):
    id: UUID
    title: str
    description: str
    starts_at: datetime
    ends_at: datetime
    status: str
    capacity: int | None
    spaces_left: int | None
    booked: bool
    join_url: str | None
    recording: PlaybackOut | None
    attended_min: int | None
    expected_otj_min: int
    cpd_min: int


class LearnerWorkshopsOut(Schema):
    items: list[LearnerWorkshopOut]
    present_min: int
