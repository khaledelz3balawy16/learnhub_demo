# Current goal: Programs v1 (M18 to M23)

Set by the user on 2026-11-16. Claude Code works through this list **in order, without stopping**, until
every box is ticked. A Stop hook (`.claude/hooks/goal_gate.py`) sends you back to work while boxes remain.
The previous goal (M3–M6, M17) is archived in `docs/goal-archive-m3-m6.md`; its open user actions are in
`docs/user-actions.md`.

**Plan:** `docs/features/programs-v1/plan.md` (decisions D1–D29, data model, milestones).
**Product rule:** it is sold to many providers. Nothing is KBC-specific; rules are settings, staff powers
are permissions (`core/staff_perms.py`).

**Git (user decision, 2026-11-16): no commits, no pushes.** Leave all work uncommitted on `demo-work` for the
user to review.

**Before each milestone:**
1. Re-read `CLAUDE.md`, `docs/build-status.md` and the plan.
2. Write the milestone brief `docs/milestones/<id>-*.md` from the plan, if it doesn't exist (same shape as
   `M18-program-structure.md`). Apply any `docs/milestones/<id>-review.md` from the planner first.

**Testing (user decision, 2026-11-16): small tests only while building.**
- Each milestone: targeted backend tests for its new behaviour (run only those apps/classes, `--keepdb`),
  ruff (check + format), `makemigrations --check`, `tsc -b`, `vite build`, the `reviewer` agent on the
  milestone's files with its findings fixed.
- The full suite, E2E scripts, phone checks and screenshots are the **last box** below.
- Never run two test runs at once (they share the `test_*` database).

**Ticking a milestone box:** every screen in its brief is built against the real backend, the small checks
above pass, reviewer findings are fixed or explained, and `docs/build-status.md` records what was built, the
bugs fixed and the migrations the user must run.

**When you truly need the user** (a business decision, a password or key, a migration that changes existing
data on Neon, a new dependency, anything CLAUDE.md reserves for them):
1. Business questions for the client go to `docs/client-questions.md` with our default; build with the default.
2. Anything that blocks the work goes to `docs/NEEDS-USER.md`: short, numbered, each with your recommended answer.
3. Carry on with every part that doesn't depend on the answer. Stop only when nothing else can be done.

**Running unattended:** don't run `migrate` on Neon, installs or merges. List migrations in build-status.
External services (Microsoft Graph, Skills England, Stripe) are built behind a client with a test double in
tests/harness only; real calls need the user's keys in `backend/.env`.

**Context:** auto-compaction runs at 40%. Keep notes that matter in `docs/build-status.md`.

## Checklist
- [x] M18 program structure, cohorts and groups (`docs/milestones/M18-program-structure.md`): built, small tests and reviewer pass done, programs hidden from selling until M21 (D29).
- [x] M19 KSBs, OTJ ledger and CPD (plan §4 M19)
- [x] M20 Teams live sessions, recordings and workshops (plan §4 M20). The Azure app registration guide goes in `docs/user-actions.md`; build the manual fallback fully.
- [x] M21 B2C buying: program offers, cohort seats, recorded access, token module unlocks, Stripe instalments (plan §4 M21). Lifts D29 for B2C.
- [x] M22 B2B company signup, order, seats, swaps and the line manager view (plan §4 M22): `docs/milestones/M22-b2b-program-seats.md`, built, small tests and reviewer pass done.
- [ ] M23 merge old cohorts (insert-only, user confirms before Neon), seed PCP/MBA/MM/ME from LMS_v2 structure (plan §4 M23).
  - 2026-11-17: the seed (`seed_programs`) is built, tested and reviewed, with provisional files for PCP, MM and ME. Waiting on `docs/NEEDS-USER.md` #1 (the merge) and #2 (the real structure, and MBA).
- [ ] Long tests (deferred by the user until here): the full backend suite, E2E scripts for M18–M23 plus every earlier script, the phone check on every new route in light and dark, the `reviewer` over all Programs work. All green, recorded in build-status.
  - 2026-11-17: full backend suite run (465 tests: 1 timing flake, fixed and re-run). The reviewer over all Programs work is done and its fixes are tested (44 tests OK). The E2E scripts and the phone check wait on `docs/NEEDS-USER.md` #3 (the e2e branch is 32 migrations behind).
