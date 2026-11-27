"""Pydantic In/Out schemas for the catalog API."""

from datetime import date, datetime
from uuid import UUID

from ninja import Schema


class CategoryOut(Schema):
    id: UUID
    slug: str
    name: str
    icon: str


class PriceOut(Schema):
    currency: str
    exponent: int
    free: bool
    list_minor: int | None = None
    sale_minor: int | None = None  # set during a site-wide sale


class InstructorBrief(Schema):
    id: UUID
    name: str
    headline: str = ""
    avatar_url: str = ""
    slug: str | None = None


class CourseCard(Schema):
    id: UUID
    slug: str
    title: str
    subtitle: str
    thumbnail_url: str
    level: str
    category: str | None
    rating_avg: float
    rating_count: int
    student_count: int
    lecture_count: int
    total_duration_sec: int
    instructors: list[str]
    price: PriceOut | None  # None: not sold individually (e.g. company course)
    price_from: bool = False  # programs (M21): the lowest of several offers ("from £X")


class CoursePage(Schema):
    items: list[CourseCard]
    next_cursor: str | None
    total: int | None = None  # on the first page only ("1,248 courses")


class LectureOut(Schema):
    id: UUID  # the live lecture row's pk — the target_id for token unlock / access checks
    key: UUID
    title: str
    kind: str
    duration_sec: int
    is_preview: bool
    # B2C token monetization (additive). token_price is the price in tokens to unlock this
    # lecture on its own; None means it is not individually sold for tokens.
    token_price: int | None = None
    is_free_preview: bool = False
    excluded_from_subscription: bool = False


class SectionOut(Schema):
    id: UUID
    title: str
    lectures: list[LectureOut]
    module_id: UUID | None = None  # programs: the week's module


class CourseModuleOut(Schema):
    id: UUID
    module_key: UUID  # offers and purchases point at this (stable across versions)
    title: str
    description: str


class ProgramOfferOut(Schema):
    """One way to buy a program or one of its modules (M21)."""

    id: UUID
    module_key: UUID | None  # None = the whole program
    mode: str  # live | recorded
    price: PriceOut | None  # None: tokens only
    token_price: int | None
    instalments_max: int


class ProgramIntakeOut(Schema):
    id: UUID
    name: str
    start_date: date
    end_date: date | None
    places_left: int | None  # None = no limit


class ProgramAccessOut(Schema):
    """What the signed-in learner already has in this program."""

    enrollment_id: UUID
    scope: str  # program | modules
    module_keys: list[UUID]  # the modules bought (scope "modules")
    live: bool  # placed in a group
    cohort_id: UUID | None
    paused: bool = False  # a monthly payment failed and the grace period is over
    paying_monthly: bool = False  # a monthly plan is still running (nothing else is sold meanwhile)


class ViewerOut(Schema):
    enrollment_id: UUID | None = None
    progress_pct: float | None = None
    in_cart: bool = False
    in_wishlist: bool = False
    is_instructor: bool = False
    plan_access: bool = False  # included in the viewer's active Personal Plan


class CourseDetail(CourseCard):
    description: str
    cpd_hours: float | None
    published_at: datetime | None
    updated_at: datetime
    topics: list[str]
    instructor_profiles: list[InstructorBrief]
    rating_breakdown: dict[str, int]  # {"5": 120, "4": 30, ...}
    sections: list[SectionOut]
    viewer: ViewerOut
    # B2C token monetization (additive). full_course_token_price: tokens to unlock the whole
    # course (None = not sold for tokens). in_subscription: included in the unlimited plan.
    full_course_token_price: int | None = None
    token_pricing_mode: str | None = None
    in_subscription: bool = True
    kind: str = "short"  # "program": sections are weeks grouped by `modules`
    modules: list[CourseModuleOut] = []
    # programs (M21): how to buy, the intakes for a live place, and what the viewer has
    offers: list[ProgramOfferOut] = []
    intakes: list[ProgramIntakeOut] = []
    program_access: ProgramAccessOut | None = None


class PlaybackOut(Schema):
    kind: str  # "bunny" | "placeholder"
    url: str | None
    expires_at: int | None
    duration_sec: int


class VideoPartOut(Schema):
    """A named part of a video (a Bunny chapter): from `start` to the next part."""

    title: str
    start: int


class VideoMomentOut(Schema):
    """A key moment the instructor marked in a video (a Bunny moment)."""

    label: str
    timestamp: int
