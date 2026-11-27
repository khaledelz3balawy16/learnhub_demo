"""Console > Programs > program > Offers (M21): how a program and its modules are sold to people.

Reading needs programs.build or cohorts.manage; adding and editing offers needs programs.build.
Offers are switched off, never deleted (orders point at them). Every change is audited.
Schema names start with ConsoleProgramOffer.
"""

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.catalog.models import Course, Module
from apps.commerce import programs as selling
from apps.commerce.models import PriceTier, ProgramOffer
from core.staff_perms import has_perm, require_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, router, staff
from .programs import _reader


class ConsoleProgramOfferOut(Schema):
    id: UUID
    module_key: UUID | None
    module_title: str | None
    mode: str
    tier_id: UUID | None
    tier_name: str | None
    gbp_minor: int | None  # the tier's base price
    token_price: int | None
    instalments_max: int
    is_active: bool


class ConsoleProgramOfferTierOut(Schema):
    id: UUID
    name: str
    gbp_minor: int


class ConsoleProgramOfferModuleOut(Schema):
    module_key: UUID
    title: str


class ConsoleProgramOffersOut(Schema):
    items: list[ConsoleProgramOfferOut]
    tiers: list[ConsoleProgramOfferTierOut]
    modules: list[ConsoleProgramOfferModuleOut]
    published: bool
    can_edit: bool


class ConsoleProgramOfferIn(Schema):
    module_key: UUID | None = None
    mode: str = Field(..., pattern="^(live|recorded)$")
    tier_id: UUID | None = None
    token_price: int | None = Field(None, ge=1, le=100_000)
    instalments_max: int = Field(1, ge=1, le=24)
    is_active: bool = True


class ConsoleProgramOfferPatchIn(Schema):
    tier_id: UUID | None = None
    token_price: int | None = Field(None, ge=1, le=100_000)
    instalments_max: int | None = Field(None, ge=1, le=24)
    is_active: bool | None = None


def _program(program_id) -> Course:
    return get_object_or_404(Course, pk=program_id, kind=Course.Kind.PROGRAM, deleted_at__isnull=True)


@router.get("/programs/{program_id}/offers", response=ConsoleProgramOffersOut)
def offers(request, program_id: UUID):
    _reader(request)
    program = _program(program_id)
    titles = (
        dict(Module.objects.filter(version_id=program.live_version_id).order_by("position")
             .values_list("module_key", "title"))
        if program.live_version_id else {}
    )  # fmt: skip
    rows = ProgramOffer.objects.filter(program=program).select_related("tier").order_by("created_at")
    return {
        "items": [
            {"id": o.id, "module_key": o.module_key, "module_title": titles.get(o.module_key) if o.module_key else None,
             "mode": o.mode, "tier_id": o.tier_id, "tier_name": o.tier.name if o.tier_id else None,
             "gbp_minor": o.tier.gbp_minor if o.tier_id else None, "token_price": o.token_price,
             "instalments_max": o.instalments_max, "is_active": o.is_active}
            for o in rows
        ],
        "tiers": list(PriceTier.objects.filter(is_active=True).values("id", "name", "gbp_minor")),
        "modules": [{"module_key": k, "title": t} for k, t in titles.items()],
        "published": program.live_version_id is not None and program.owner_org_id is None,
        "can_edit": has_perm(request, "programs.build"),
    }  # fmt: skip


@router.post("/programs/{program_id}/offers", response=ConsoleIdOut)
def create_offer(request, program_id: UUID, body: ConsoleProgramOfferIn):
    staff(request)
    require_perm(request, "programs.build")
    offer = selling.save_offer(program=_program(program_id), **body.dict())
    audit_request(request, "program.offer_create", "program_offer", str(offer.id),
                  {"program": str(program_id), "mode": offer.mode, "module": str(offer.module_key or "")})  # fmt: skip
    return {"id": offer.id}


@router.patch("/program-offers/{offer_id}", response=ConsoleOkOut)
def update_offer(request, offer_id: UUID, body: ConsoleProgramOfferPatchIn):
    staff(request)
    require_perm(request, "programs.build")
    offer = get_object_or_404(ProgramOffer.objects.select_related("program"), pk=offer_id)
    changes = body.dict(exclude_unset=True)
    selling.save_offer(program=offer.program, offer=offer, **changes)
    audit_request(request, "program.offer_update", "program_offer", str(offer.id),
                  {k: str(v) for k, v in changes.items()})  # fmt: skip
    return {"ok": True}
