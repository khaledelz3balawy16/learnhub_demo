# Needs your decision

Only real blockers go here. Everything else is in `docs/client-questions.md` (with a default already built) or
`docs/user-actions.md`.

## 1. M23: merging the old live cohorts into the new program cohorts (asked 2026-11-17)

The plan says the old B2B live cohorts (`corporate.LiveCohort`, `Session`, Zoom attendance) become new program
cohorts, groups and live sessions, and the old tables become read-only. They don't fit:

- An old live cohort belongs to a **short course**. Every old cohort on dev is one: today there is 1 cohort,
  1 session, 1 company booking and 1 attendee. A new cohort belongs to a **program** with modules and dated weeks.
- A new live session must point at a live component of the program. Old sessions are Zoom meetings with no
  component.
- Making the old tables read-only would stop the existing company "Live training" pages (request, offer, pay,
  name attendees, Zoom attendance, cancellations) for short courses. Programs already have their own company
  flow (M22).

**Options**
- **A (recommended):** keep both. The old flow stays as "live training for short courses", exactly as today;
  programs use cohorts, groups, Teams and company seats. No data is copied and nothing on Neon changes. The console
  and business navigation label the old pages "Short-course live training" so the two aren't confused.
- **B:** copy each old cohort into a new cohort under its short course, with one group and one dated session per
  old session (insert-only), and switch the old pages to read-only. Old Zoom links and attendance are kept for
  reference. The short course has no weeks or components, so those cohorts have no calendar, OTJ or KSBs.
- **C:** retire the old flow: no new short-course live cohorts; the existing ones finish as they are.

Until you answer, I'm building M23's seed of the four real programs (it doesn't depend on this). I'm not
touching the old live tables.

## 2. M23: the real week-by-week structure of PCP, MBA, MM and ME (asked 2026-11-17)

LMS_v2's code doesn't contain the programs' weeks and components. They live only in LMS_v2's own Neon database
(project "LMS", schema `curriculum`: `programmes` → `modules` → `weeks` → `components`, plus `standard_ksbs` and
`ksb_mappings`). That database also holds learner data, and it isn't this project's, so I haven't touched it.

What the repo does give us, and what the seed uses meanwhile:
- the program names and standards: PCP = Project Controls Professional L6, ST0845; MM = Marketing Manager L6,
  ST0612; ME = Marketing Executive L4, ST0596; MBA has no standard;
- the module titles for PCP, MM and ME;
- LMS_v2's standard week: a live Teams session, a recording, a reading, a video and a reflection.

**Options**
- **A (recommended):** you allow one read-only export of the structure tables only (no learner tables), filtered to
  those four programs. I save it as `backend/apps/delivery/seed/programs/*.json` and the seed uses it; no code
  changes. Or you run the export yourself and drop the files in that folder.
- **B:** keep the provisional structure: the real module titles, 4 weeks each, LMS_v2's standard week. MBA is left
  out until its modules are known.

The seed command is built so that the files are the only thing that changes.

## 3. The long tests: the e2e branch needs the new migrations (asked 2026-11-17)

The last goal box runs the E2E scripts and the phone check against the `e2e` Neon branch. I checked it (read-only,
`showmigrations`): it has **31 migrations pending**, M17's and every Programs migration (M18 to M22), plus the new
`learning.0016_seat_counts_access` from the final review: 32 in all. Without them
the new screens can't load there. All of them only add schemas, tables, columns, policies and rows.

**Options**
- **A (recommended):** you allow me to run `python manage.py migrate --database owner` on the **e2e branch only**
  (never dev or production). I show the `showmigrations` list before and after.
- **B:** you run it on e2e yourself, then tell me.

Also needed for the learner-side phone check: the demo password (`E2E_DEMO_PASSWORD`), as before. The business
phone check doesn't need it.

Until then I'm running the full backend suite, writing the Programs E2E scripts and running the reviewer over all
Programs work. None of that needs the branch.
