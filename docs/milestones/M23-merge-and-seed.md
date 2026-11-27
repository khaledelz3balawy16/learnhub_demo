# M23: merge old cohorts, seed the real programs, full E2E

Plan: `docs/features/programs-v1/plan.md` §4 M23, D27.

## Part 1: old live cohorts (blocked on the user)
The plan's merge doesn't fit the data: old live cohorts belong to short courses, while new cohorts belong to programs.
The options and our recommendation are in `docs/NEEDS-USER.md` #1. Nothing is built or changed on the old live tables
until the user answers.

## Part 2: seed the four real programs (D27)
A management command, `python manage.py seed_programs` (insert-only, idempotent):
- It reads the programs' real structure from `backend/apps/delivery/seed/programs/*.json`. These are files we made
  from LMS_v2's structure: no learner data, nothing copied at run time from LMS_v2.
- For each of PCP, MBA, MM and ME it creates:
  - the program, owned by the platform: modules, weeks and components (kind, OTJ minutes, CPD minutes), published;
  - its KSB standard (imported apprenticeship standards: code, level, items), with components mapped to KSBs where
    the source maps them, and the program setting pointing at it;
  - an OTJ target from the source, or the client default;
  - offers: whole program live and recorded, plus each module recorded, at a price tier (client question #33 still
    open, so the tier is a placeholder the provider changes in the console);
  - 2 cohorts (one running, one planned), each with 2 groups, a tutor and a weekly timetable;
  - learners placed in the groups (demo accounts `@learnhub.example.com`);
  - planned live sessions, attendance for past sessions, some completed components, and OTJ entries (some
    approved, some pending).
- It runs again safely: it skips a program whose slug exists. `--only PCP` seeds one.
- It never runs in tests against shared data, and never on Neon without the user (it is a command they run).

## Tests
- The command on a test database: four programs published, standards with items, two cohorts and groups each,
  learners placed, sessions planned, and a second run creating nothing new.

## E2E (the last box)
Full E2E for B2C live, B2C recorded with tokens, B2B signup to swap, tutor approvals and the Teams fallback runs in
the long-tests box.
