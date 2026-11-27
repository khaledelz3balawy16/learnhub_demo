"""KSB standards (M19, plan D12): parse, fetch and save apprenticeship standards, and the
provider's custom sets. Console only (staff RLS key): the tables are reference data.

Two input shapes are accepted (fetched or uploaded):
  * Skills England / IfATE standard JSON: referenceNumber, title, version, level,
    knowledges[{knowledgeId, detail}], skills[{skillId, detail}], behaviours[{behaviourId, detail}]
  * plain: {code, title, version, level, items: [{code, kind, text}]}
Saving never rewrites: the same code and version gains missing items only.
"""

from __future__ import annotations

import json
from urllib.parse import quote, urlsplit

import httpx
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import html
from core.errors import ServiceError

from .models import ComponentKsb, Course, KsbItem, KsbStandard, Lecture

MAX_FEED_BYTES = 2 * 1024 * 1024  # a standard is a few kB
ALLOWED_HOSTS = {"skillsengland.education.gov.uk", "www.instituteforapprenticeships.org"}
MAX_ITEMS = 400
KINDS = {"k": KsbItem.Kind.KNOWLEDGE, "s": KsbItem.Kind.SKILL, "b": KsbItem.Kind.BEHAVIOUR}
PREFIX = {v: k.upper() for k, v in KINDS.items()}


# ---------------------------------------------------------------- parsing
def _text(value, limit: int) -> str:
    return html.plain(str(value or ""), limit).strip()


def parse(payload: dict) -> dict:
    """-> {code, title, version, level, items: [(code, kind, text)]}. Raises ServiceError on
    anything that isn't a standard."""
    if not isinstance(payload, dict):
        raise ServiceError("bad_standard", "That file isn't a standard.")
    if isinstance(payload.get("items"), list):  # plain shape
        code = _text(payload.get("code"), 40)
        items = []
        for row in payload["items"]:
            if not isinstance(row, dict):
                continue
            kind = KINDS.get(str(row.get("kind") or row.get("code") or "")[:1].lower())
            item_code, text = _text(row.get("code"), 12).upper(), _text(row.get("text"), 4000)
            if kind and item_code and text:
                items.append((item_code, kind, text))
    else:  # Skills England / IfATE shape
        code = _text(payload.get("referenceNumber") or payload.get("reference"), 40)
        items = []
        for key, kind in (("knowledges", "knowledge"), ("skills", "skill"), ("behaviours", "behaviour")):
            for i, row in enumerate(payload.get(key) or [], start=1):
                if not isinstance(row, dict):
                    continue
                n = row.get(f"{kind}Id") or i
                text = _text(row.get("detail") or row.get("text"), 4000)
                if text:
                    items.append((f"{PREFIX[kind]}{n}"[:12], kind, text))
    title = _text(payload.get("title"), 300)
    if not code or not title or not items:
        raise ServiceError("bad_standard", "That isn't a standard with a code, a title and its KSBs.")
    if len(items) > MAX_ITEMS:
        raise ServiceError("too_many", f"A standard can have at most {MAX_ITEMS} KSBs.")
    level = payload.get("level")
    return {
        "code": code.upper(),
        "title": title,
        "version": _text(payload.get("version"), 20),
        "level": int(level) if isinstance(level, int | float) and 0 < level < 10 else None,
        "items": items,
    }


def fetch(code: str, *, timeout: float = 15.0) -> dict:
    """Look a standard up by code on the configured feed. Network and HTTP problems become a
    clear 502; the upload is the fallback."""
    from apps.platform.services import get_setting

    code = code.strip().upper()
    if not code.replace("-", "").isalnum() or len(code) > 20:
        raise ServiceError("bad_code", "Enter a standard code like ST0272.")
    template = str(get_setting("learning.ksb_feed_url") or "")
    url = template.replace("{code}", quote(code))
    if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise ServiceError("feed_not_allowed", "The standards feed address in Settings isn't allowed.")
    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=False,
                          headers={"Accept": "application/json"}) as resp:  # fmt: skip
            status, body = resp.status_code, b""
            if status == 200:
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_FEED_BYTES:
                        raise ServiceError("bad_standard", "The feed sent too much data.", status=502)
    except httpx.HTTPError:
        raise ServiceError("feed_unavailable", "The standards feed couldn't be reached. Upload the file instead.",
                           status=502) from None  # fmt: skip
    if status == 404:
        raise ServiceError("not_found", f"No standard {code} was found.", status=404)
    if status != 200:
        raise ServiceError(
            "feed_unavailable", "The standards feed didn't answer. Upload the file instead.", status=502
        )
    try:
        data = json.loads(body)
    except ValueError:
        raise ServiceError("bad_standard", "The feed didn't send a standard.", status=502) from None
    return parse(data[0] if isinstance(data, list) and data else data)


# ---------------------------------------------------------------- saving
@transaction.atomic
def save_standard(parsed: dict, *, by, source: str = KsbStandard.Source.IMPORTED) -> tuple[KsbStandard, int]:
    """Create the standard (or reuse the same code and version) and add the KSBs it lacks.
    Returns (standard, items added)."""
    std, _ = KsbStandard.objects.get_or_create(
        code=parsed["code"], version=parsed["version"],
        defaults={"title": parsed["title"], "level": parsed["level"], "source": source,
                  "imported_at": timezone.now(), "created_by": by},
    )  # fmt: skip
    have = set(std.items.values_list("code", flat=True))
    start = len(have)
    fresh = []
    for code, kind, text in parsed["items"]:
        if code not in have:  # also drops a code repeated inside the same file
            have.add(code)
            fresh.append((code, kind, text))
    new = [
        KsbItem(standard=std, code=code, kind=kind, text=text, position=start + i)
        for i, (code, kind, text) in enumerate(fresh)
    ]
    KsbItem.objects.bulk_create(new, ignore_conflicts=True)
    return std, len(new)


def create_custom(*, code: str, title: str, by) -> KsbStandard:
    code, title = _text(code, 40).upper(), _text(title, 300)
    if not code or not title:
        raise ServiceError("missing", "Give the set a code and a title.")
    try:
        with transaction.atomic():
            return KsbStandard.objects.create(
                code=code, title=title, version="", source=KsbStandard.Source.CUSTOM, created_by=by
            )
    except IntegrityError:
        raise ServiceError("duplicate", "A set with that code already exists.") from None


@transaction.atomic
def add_item(*, standard: KsbStandard, kind: str, text: str) -> KsbItem:
    """Custom sets only: imported standards stay exactly as published."""
    standard = KsbStandard.objects.select_for_update().get(pk=standard.pk)
    if standard.source != KsbStandard.Source.CUSTOM:
        raise ServiceError("imported", "Imported standards can't be changed.")
    if kind not in KsbItem.Kind.values:
        raise ServiceError("bad_kind", "Choose knowledge, skill or behaviour.")
    text = _text(text, 4000)
    if len(text) < 3:
        raise ServiceError("missing_text", "Describe the KSB.")
    n = standard.items.filter(kind=kind).count() + 1
    prefix = PREFIX[kind]
    have = set(standard.items.values_list("code", flat=True))
    while f"{prefix}{n}" in have:
        n += 1
    return KsbItem.objects.create(
        standard=standard, code=f"{prefix}{n}", kind=kind, text=text, position=standard.items.count()
    )


# ---------------------------------------------------------------- mapping
def program_components(program: Course) -> list[dict]:
    """Components of the program's newest version (working draft, else live): what staff map."""
    version = program.versions.order_by("-created_at").only("id").first()
    if version is None:
        return []
    return list(
        Lecture.objects.filter(version=version)
        .order_by("section__position", "position")
        .values("lecture_key", "title", "kind", "section_id", "section__title", "section__module__title")
    )


@transaction.atomic
def set_component_ksbs(*, program: Course, lecture_key, item_ids: list, standard_id) -> int:
    """Replace one component's KSB list. Items must belong to the program's standard; the
    component must exist in a version of the program. Returns how many are mapped."""
    if standard_id is None:
        raise ServiceError("no_standard", "Choose the program's KSB standard first.")
    if not Lecture.objects.filter(version__course=program, lecture_key=lecture_key).exists():
        raise ServiceError("not_found", "Component not found in this program.", status=404)
    ids = set(item_ids)
    valid = set(KsbItem.objects.filter(standard_id=standard_id, pk__in=ids).values_list("pk", flat=True))
    if valid != ids:
        raise ServiceError("bad_ksb", "Some KSBs aren't part of this program's standard.")
    current = set(
        ComponentKsb.objects.filter(program=program, lecture_key=lecture_key).values_list(
            "item_id", flat=True
        )
    )
    ComponentKsb.objects.filter(program=program, lecture_key=lecture_key, item_id__in=current - ids).delete()
    ComponentKsb.objects.bulk_create(
        [ComponentKsb(program=program, lecture_key=lecture_key, item_id=i) for i in ids - current],
        ignore_conflicts=True,
    )
    return len(ids)
