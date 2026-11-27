"""Export the real structure of PCP, MM, ME and MBA from LMS_v2 into the program seed files.

    backend/venv/bin/python tools/lmsv2_export.py            # writes backend/apps/delivery/seed/programs/*.json
    backend/venv/bin/python tools/lmsv2_export.py --check    # reads and reports, writes nothing

READ ONLY. User decision (2026-11-25, docs/NEEDS-USER.md #2): one read-only export of the
curriculum STRUCTURE tables only. The connection is opened read-only, and the queries name
every column they read: programmes are not read at all; from modules, weeks, components,
ksb_mappings and standard_ksbs only titles, texts, hours, order and KSB codes. Nothing about
learners, tutors, groups, cohorts, Teams meetings, files or links is selected.

The connection string comes from backend/.env.lmsv2 (git-ignored: `.env.*`), one line:
    LMSV2_DATABASE_URL=postgresql://<user>:<password>@<LMS project production host>/neondb?sslmode=require
It is never printed. Only counts are printed.

What a seeded week contains (user decision 2026-11-25, "one materials page per week"):
- every live session and assignment, in full: title, purpose / brief, expected OTJ hours, KSBs;
- one reading, "<week title>: materials", that lists the week's videos, readings, slides,
  podcasts and quizzes by title with their hours. Their files live in LMS_v2's storage and are
  not copied; the page carries their OTJ hours and KSBs so the week's totals stay right.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "backend" / "apps" / "delivery" / "seed" / "programs"
ENV_FILE = ROOT / "backend" / ".env.lmsv2"
MAX_OTJ_MIN = 1440  # one ledger entry per component (catalog.Lecture.expected_otj_min)

# Which LMS_v2 module copy each seeded module comes from (user decisions 2026-11-25): the copy
# with the most weeks, then the most recently updated. (display title, module_catalogue_id)
PROGRAMS = {
    "pcp": [
        ("Project Management Professional", "MOD-20260912111853582488"),
        ("PMI-SP Scheduling Professional", "MOD-20261001105703419367E214F45713C3"),
        ("Risk Management", "MOD-20260916132543446957B40D238B7516"),
        (
            "Managing Successful Programmes: Project Controls for Transformational Change",
            "MOD-20260930110509069516DE05CBE11E6E",
        ),
        ("Stakeholder Management & Reporting", "MOD-KBC-PMP-M01-SMR"),
        ("Project Planning and Control (PPC)", "MOD-20260912132052479676"),
        ("Project Management Office (PMI PMO)", "MOD-2026100111080958797426535A71280F"),
    ],
    "mm": [
        ("Marketing Strategy & Planning", "MOD-20260912130830641004"),
        ("Customer Journey Optimisation", "MOD-202609301354380952694569FE544702"),
        ("Commercial Intelligence", "MOD-20260912131150211624"),
        ("AI In Marketing", "MOD-202609211343157699387AACDDCD8A5B"),
    ],
    "me": [
        ("Marketing Impact and Planning", "MOD-20260912105734147219"),
        ("Social Media", "MOD-202609211208476573216D584A576BEF"),
        ("Marketing Technology (MarTech)", "MOD-20261118151507874997933F33DD244A"),
    ],
    "mba": [
        ("Strategic Management", "MOD-2026082213EA24F03A1D"),
        ("Strategic Leadership", "MOD-20260822F447F8C1470F"),
        ("Strategic Human Resource Management", "MOD-20260822C2ABEFEF6847"),
        ("Marketing Strategy", "MOD-202608223BE5D3D3C97F"),
        ("Business Research Methodology", "MOD-20260822325BB9E81B24"),
        ("Procurement, Risk and Contract Management", "MOD-20260822D074A494D159"),
    ],
}
# MBA had no seed file before the export; these are its program fields (no apprenticeship standard).
MBA_HEADER = {
    "key": "MBA",
    "slug": "mba-level-7",
    "title": "MBA (Level 7)",
    "subtitle": "Strategy, leadership, people, marketing, research and procurement at Level 7.",
    "level": "advanced",
    "intake_months": [2, 6, 10],
}
MATERIAL_LABELS = {
    "video": "Video",
    "reading": "Reading",
    "powerpoint": "Slides",
    "podcast": "Podcast",
    "quiz": "Quiz",
}
SKIPPED_TYPES = {"recording_placeholder"}  # recordings come from each group's own Teams session

WEEKS_SQL = """
SELECT id, title, summary, learning_outcomes
FROM curriculum.weeks
WHERE module_catalogue_id = %s AND deleted_at IS NULL
ORDER BY display_order, week_number, id
"""
# settings_json is read key by key: only the texts below, never links, files, emails or attendees
COMPONENTS_SQL = """
SELECT c.id, c.week_id, c.type, c.title, c.description, c.expected_otjh,
       c.settings_json ->> 'sessionPurpose'          AS session_purpose,
       c.settings_json ->> 'preparationInstructions' AS preparation,
       c.settings_json ->> 'assignmentBrief'         AS brief,
       c.settings_json ->> 'submissionInstructions'  AS submission
FROM curriculum.components c
JOIN curriculum.weeks w ON w.id = c.week_id
WHERE w.module_catalogue_id = %s AND w.deleted_at IS NULL AND c.deleted_at IS NULL
ORDER BY c.display_order, c.id
"""
KSB_SQL = """
SELECT km.component_id, km.ksb_code
FROM curriculum.ksb_mappings km
JOIN curriculum.weeks w ON w.id = km.week_id
WHERE w.module_catalogue_id = %s AND w.deleted_at IS NULL AND km.deleted_at IS NULL AND km.component_id IS NOT NULL
"""
STANDARD_SQL = """
SELECT ksb_code, ksb_type, ksb_description
FROM curriculum.standard_ksbs
WHERE standard_ref = %s
ORDER BY id
"""

_INVISIBLE = re.compile(r"[​‌‍⁠﻿]")
_TAGS = re.compile(r"<[^>]+>")


def text(value, limit: int | None = None) -> str:
    """Plain text: entities decoded, tags and zero-width characters removed, spaces collapsed."""
    s = html.unescape(_TAGS.sub(" ", str(value or "")))
    s = " ".join(_INVISIBLE.sub("", s).split())
    return s[:limit] if limit else s


def safe(s: str) -> str:
    """The seed runs str.format() on titles and texts: keep real braces literal."""
    return s.replace("{", "{{").replace("}", "}}")


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def minutes(hours) -> int:
    return max(0, round(float(hours or 0) * 60))


def hours_label(mins: int) -> str:
    if not mins:
        return ""
    return f"{mins} min" if mins < 60 else f"{mins / 60:.1f}".rstrip("0").rstrip(".") + " h"


def paragraphs(*parts: str) -> str:
    return "".join(f"<p>{esc(p)}</p>" for p in parts if p)


def outcomes(raw) -> list[str]:
    items = raw if isinstance(raw, list) else []
    out = []
    for o in items:
        if isinstance(o, dict):
            o = o.get("text") or o.get("title") or o.get("outcome") or ""
        if t := text(o, 400):
            out.append(t)
    return out


def connect():
    if not ENV_FILE.exists():
        sys.exit(
            f"{ENV_FILE.relative_to(ROOT)} is missing: add LMSV2_DATABASE_URL=... (see this file's docstring)."
        )
    url = ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("LMSV2_DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip("'\"")
    if not url:
        sys.exit("backend/.env.lmsv2 has no LMSV2_DATABASE_URL line.")
    import psycopg

    conn = psycopg.connect(url, options="-c default_transaction_read_only=on")
    conn.read_only = True
    return conn


def module_weeks(cur, module_id: str, counts: dict) -> list[dict]:
    cur.execute(WEEKS_SQL, (module_id,))
    weeks = cur.fetchall()
    cur.execute(COMPONENTS_SQL, (module_id,))
    comps = cur.fetchall()
    cur.execute(KSB_SQL, (module_id,))
    ksbs = defaultdict(set)
    for component_id, code in cur.fetchall():
        if code:
            ksbs[component_id].add(code.strip().upper())

    by_week = defaultdict(list)
    for row in comps:
        by_week[row[1]].append(row)

    out = []
    for n, (week_id, title, summary, raw_outcomes) in enumerate(weeks, start=1):
        week_title = text(title, 200) or f"Week {n}"
        components, materials = [], defaultdict(list)
        mat_min, mat_ksbs = 0, set()
        for cid, _, kind, ctitle, desc, otjh, purpose, prep, brief, submission in by_week[week_id]:
            name, mins, codes = text(ctitle, 200) or "Untitled", minutes(otjh), sorted(ksbs.get(cid, ()))
            if kind == "live_session":
                capped = min(mins, MAX_OTJ_MIN)
                counts["capped"] += capped != mins
                body = paragraphs(text(purpose, 2000) or text(desc, 2000), text(prep, 2000))
                components.append({"kind": "live_session", "title": safe(name), "otj_min": capped, "cpd_min": capped,
                                   **({"body": safe(body)} if body else {}), **({"ksbs": codes} if codes else {})})  # fmt: skip
                counts["live"] += 1
            elif kind == "assignment":
                capped = min(mins, MAX_OTJ_MIN)
                counts["capped"] += capped != mins
                instructions = "\n\n".join(
                    p for p in (text(brief, 4000), text(desc, 2000), text(submission, 2000)) if p
                )
                components.append({"kind": "assignment", "title": safe(name), "otj_min": capped, "cpd_min": capped,
                                   "instructions": safe(instructions or name), **({"ksbs": codes} if codes else {})})  # fmt: skip
                counts["assignments"] += 1
            elif kind in MATERIAL_LABELS:
                materials[kind].append((name, mins))
                mat_min += mins
                mat_ksbs |= set(codes)
                counts["listed"] += 1
            elif kind not in SKIPPED_TYPES:
                counts["unknown_types"][kind] += 1

        listed = sum(len(v) for v in materials.values())
        learn = outcomes(raw_outcomes)
        if listed or not components:  # every week needs at least one component to publish
            parts = [paragraphs(text(summary, 2000))]
            if learn:
                parts.append(
                    "<h3>What you'll learn</h3><ul>" + "".join(f"<li>{esc(o)}</li>" for o in learn) + "</ul>"
                )
            if listed:
                parts.append("<h3>This week's materials</h3>")
                for kind, label in MATERIAL_LABELS.items():
                    rows = materials.get(kind)
                    if rows:
                        parts.append(
                            f"<h4>{label}s ({len(rows)})</h4><ul>"
                            + "".join(
                                f"<li>{esc(t)}{' · ' + hours_label(m) if m else ''}</li>" for t, m in rows
                            )
                            + "</ul>"
                        )
            body = "".join(parts) or "<p>No materials are listed for this week.</p>"
            capped = min(mat_min, MAX_OTJ_MIN)
            counts["capped"] += capped != mat_min
            components.insert(0, {"kind": "article", "title": safe(f"{week_title}: materials"[:200]),
                                  "otj_min": capped, "cpd_min": capped, "body": safe(body),
                                  **({"ksbs": sorted(mat_ksbs)} if mat_ksbs else {})})  # fmt: skip
            counts["material_pages"] += 1
        out.append({"title": safe(week_title), "components": components})
        counts["weeks"] += 1
    return out


def standard_items(cur, code: str) -> list[dict]:
    cur.execute(STANDARD_SQL, (code,))
    items = []
    for ksb_code, ksb_type, desc in cur.fetchall():
        if ksb_code and ksb_type and desc:
            items.append(
                {"code": ksb_code.strip().upper(), "kind": ksb_type.strip().lower(), "text": text(desc, 4000)}
            )
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="read and report counts; write nothing")
    args = ap.parse_args()

    with connect() as conn, conn.cursor() as cur:
        for key, modules in PROGRAMS.items():
            path = SEED_DIR / f"{key}.json"
            spec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(MBA_HEADER)
            counts = defaultdict(int, unknown_types=defaultdict(int))
            spec["modules"] = [
                {"title": safe(title), "weeks": module_weeks(cur, mid, counts)} for title, mid in modules
            ]
            if spec.get("standard"):
                items = standard_items(cur, spec["standard"]["code"])
                if items:
                    spec["standard"]["items"] = items
                counts["standard_items"] = len(items)
            spec["_source"] = (
                f"Exported read-only from LMS_v2 (Neon project LMS, branch production, schema curriculum) on "
                f"{date.today().isoformat()} by tools/lmsv2_export.py: real modules and weeks; live sessions and "
                f"assignments in full; each week's videos, readings, slides, podcasts and quizzes listed on one "
                f"materials page (their files are not copied)."
            )
            spec = {"_source": spec.pop("_source"), **spec}
            unknown = dict(counts.pop("unknown_types"))
            print(f"{spec['key']:4} modules {len(modules)} | " + " | ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                  + (f" | unknown types {unknown}" if unknown else ""))  # fmt: skip
            if not args.check:
                path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("checked only, nothing written" if args.check else f"written to {SEED_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
