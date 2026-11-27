# Build status

Maintained by Claude Code (`/status`) and read by the planner session. Newest milestone first.

## Inclusion test (2026-11-25, user request)

A learner questionnaire built from the client's `safeguarding-questions.json`: six sections of ten questions, each answered on a 0 to 3 scale. Admins edit it and read the results in the console. User decisions: results and the editor are for admins only; the test is optional and can be taken again; flag thresholds are edited by admins.

- **Backend:** new app and schema `inclusion` (`apps/inclusion`, `core/migrations/0005_inclusion_schema.py`).
  - Sections and questions are reference data, with RLS `reference`. Attempts have RLS `personal`: the learner or staff.
  - Nothing links to a company, so an employer can never read answers. `lms_readonly` gets no grant on this schema, because any role can set the staff key itself.
  - Each submitted attempt keeps a copy of the questions, answers and section scores. Flags are recomputed from the current thresholds whenever a threshold changes or a section is deleted.
  - Advisory locks: one per learner, so a save and a submit never create two drafts; and one for flags, so threshold edits run one at a time and submissions wait for them.
  - Learner endpoints: `GET /api/v1/inclusion/me`, `PUT /me/draft`, `POST /me/submit`.
- **Console** (`apps/platform/console/inclusion.py`): `/console/inclusion/questions`, sections (create, edit, delete, reorder), questions (create, edit, delete, reorder), and `/console/inclusion/results` (keyset list with search, a flagged filter and a section filter, plus a detail view with earlier attempts).
  - Admins only: superusers, or anyone holding `roles.manage`. Every edit and every opened result is written to the audit log.
- **Frontend:**
  - Learner page `/learn/inclusion` ("Inclusion test" in the My learning sidebar). A consent note comes first; questions go one section at a time and save as the learner goes; the thank-you screen offers "Take it again", which starts from the last answers.
  - Console pages "Inclusion results" and "Inclusion questions" (new nav section "Learner support").
  - New backdrop `spectrum`.
- **Migrations:** `core 0005_inclusion_schema`, then `inclusion 0001_initial`, `0002_seed_questions` (insert-only) and `0003_security`.
- **Review** (`reviewer` agent) found no access gap. Fixed: autosave racing with submit (server locks, and the page now queues saves and waits for them before sending); flags going stale when two admins edit at once; the read-only role's grant; the score bar's motion duration; the section state carrying over between attempts in the results; and the results filter not refreshing after a new section.
  - Raised with the client rather than decided: keeping and deleting answers, the right to withdraw, and what happens after a flag (client questions #50 and #51).
- **Company access (user decision, same day):**
  - A company's owners and admins read their current members' latest answers in Business › People › Inclusion results (`/business/inclusion`), through `GET /api/v1/inclusion/company/results` and `/results/{id}`.
  - The database enforces it: migration `inclusion 0004_company_admin_read` adds a SELECT-only policy that requires the caller to be an active owner or admin of the request's company, and the learner an active member. Managers, learners, other companies and removed members see nothing.
  - The results view is shared with the console (`features/inclusion/ResultsView.tsx`, `scope` console or company). The learner's consent note now says company owners and admins can see the answers.
  - Client question #52 asks the client to confirm.
- **Checks:** all 11 inclusion tests pass, as do the row-security and API-contract tests, the type check and the production build. Neon dropped the network during the full run, so four tests were re-run on their own and passed. The main chunk is 147 kB, up from 143 kB because of the new backdrop and the sign-in switch.

## Learner / organisation sign-in (2026-11-25, user request)

- Header (logged out, desktop): a "For organisations" button opens `/login?as=org`.
- `/login` and `/signup` have a Learner / Organisation switch (`pages/auth/AudienceSwitch.tsx`). The choice is in the URL (`?as=org`) and `next` is kept when switching.
- Organisation mode only changes the wording and where you land. Log in goes to `/business` for someone who is an owner, admin or manager of a company (the guard sends companies still setting up to `/business/start`). Someone who manages no company, platform staff included, goes to `/business/start` to set one up, instead of being bounced to `/learn`. Sign-up goes to `/business/start`. An explicit `?next=` always wins. There is still one account system, and the backend is unchanged.
- Known gap: a sign-up that needs email confirmation loses `?next=` (the link opens a new tab), so an organisation then lands on `/learn`. The "Set up your company" route is still reachable from there.
- Also fixed: on `/courses`, the course-count skeleton was a `<div>` inside a `<p>` (a React console error).
- Checked: type check passes. Screenshots of the header, the two log-in sides and organisation sign-up, in light and dark. Phone width 375 px with no horizontal scroll.

## Finishing the "built, checks owed" milestones (2026-11-25, in progress)

User request: finalise M4, M5, M6, B2C, B2B, M17 and M18–M22 (browser tests, phone checks, reviewer).
- **Setup on this Linux machine:** hooks call `python3` (the guard works again); ruff, waitress, Playwright and
  Chromium installed. The `e2e` Neon branch was **reset from dev** (user decision), so it is fully migrated.
- **Harness:** always forces `MAIL_MODE=console` (serve.py, on_e2e.py, lib.js), so E2E never sends real email;
  `lib.js` reads `E2E_DEMO_PASSWORD` from `backend/.env.e2e` if it isn't in the environment.
- **Waiting on the user:** `backend/.env.e2e` (e2e URLs + demo password). E2E, phone checks and Lighthouse need it.
- **Reviewer, M17:** a "signal receivers garbage-collected" finding was checked and is false (the real receivers
  fire). Real findings (transactions held across Breathe calls, disconnect undone by a running sync, sync races,
  manager seeing company-wide training records, training not imported at link time, archived units, untyped
  counts) are being fixed with tests together with the missing M17 tests. Frontend fixed: People page leave badges
  (one request per page, past 200 people), HR page offline crash, "Breathe" on the Units badge. New client
  question #48 (Breathe line managers become company managers automatically).
- **M17 tests now exist:** `apps/integrations/tests/` (client 17, secrets 5, sync 24, API 6): **52 tests OK**;
  `test_api_contract` + `test_rls` OK; ruff clean. Review fixes done with tests: a sync reads Breathe with no
  transaction open (claim, fetch, then write under a lock; request paths use an 8 s timeout and one retry); a
  paused or disconnected connection's runs are cancelled ("failed", code `cancelled`, nobody notified) and never
  reopen the connection; one claim per run and `select_for_update` before the busy check; training imports take
  the org lock (never twice); managers see training records only for their own people; compliance is assigned at
  link time so training counts at once; archived units are never used; `HrRunCountsOut` types the run counts
  (types regenerated, the HR page's cast removed); case-insensitive email suggestions. Found by the tests: the
  training title spelling could change between loads. **Not built:** the brief's sync "dry run" (needs a new
  column). Still company-wide for managers: the overview counts and department people counts.
- **Harness for M17:** `tools/harness/fake_breathe.py` (accepts `e2e-fake-breathe-key-0001` only) is installed in
  `e2e_wsgi.py` and in the new worker entry `e2e_celery.py` (serve.py starts `celery -A e2e_celery`).
- **Reviewer, whole frontend (M4–M6, B2C, B2B):** fixed 17 items, among them: console Approvals click did nothing
  (two URL setters overwrote each other; new `usePatchParams`), "Tokens added" shown before payment, links to tabs
  and params pages ignored, 11 routes without titles, hard-coded "30-day refund", destructive actions without
  confirmation, stale learner caches after B2C admin changes, wrong access/grant/ledger codes, money formatting for
  non-2-decimal currencies, lecture token unlock button on the course page, My learning capped at 24 courses, B2B
  "Confirming payment" spinning after an old abandoned checkout, wording and reduced-motion scrolls. Main entry
  142.9 → 143.3 kB (route titles). New client question #49 (the console's "2× fair price" token rule).

## Local setup on Linux and dev migrations (2026-11-17)

- **Every API call returned 500 locally.** `REDIS_URL` is set but no Redis ran on this machine. Redis now runs in
  Docker (`learnhub-redis`, `redis:7.4-alpine`, bound to 127.0.0.1:6379, restarts with Docker).
- **Dev was 27 migrations behind** (the M18–M22 set and `learning.0016`), so the course lists failed on
  `commerce.program_offers`. With the user's OK, `migrate --database owner` ran on dev: all applied, none pending.
- **Bug fixed: `identity.0006_staff_roles_seed_and_security` failed on any database that has staff users**
  ("cannot ALTER TABLE staff_role_assignments because it has pending trigger events"): the seeded assignments
  left deferred foreign-key checks queued before RLS was switched on. Tests never saw it (no staff exist at
  migration time). Fix: `SET CONSTRAINTS ALL IMMEDIATE` between the seed and the RLS steps; the result is unchanged.
  The e2e branch and production need this fix before they migrate.

## Programs v1: cross-milestone review and fixes (2026-11-17, part of the long-tests box)

The `reviewer` read all Programs work (M18 to M23) for problems that only show up across milestones. Fixed:
- **A refunded live learner kept their group.** A refund (and a lapsed re-grant) now clears the cohort and group,
  and gives back future workshop places. A later module unlock never brings the old group back.
- **A paid live learner waiting for a group could be charged again.** A place in the cohort with no group now
  counts as owned.
- **Buying one module showed every live session of the group**, with join links and recordings. The learner now
  sees only the sessions of the modules they own.
- **Expired access kept its place.** One rule, `learning.models.holds_place()` (active or completed, and access not
  run out), now drives group and cohort counts, the tutor's register, attendance marking and workshop booking.
  Its SQL twin is the new `learning.0016_seat_counts_access` (replaces the count function's body; no table or row
  changes).
- **A bad company seat payment was dropped silently.** A wrong amount or a payment through an old checkout page
  now raises: the error is stored on the Stripe event (Console) and Stripe retries, as for B2C.
- A released or swapped company seat gives back its future workshop places.
- Staff can place a seat holder whose personal enrolment was refunded (the company seat is used).
- A hand-written response type in `features/programs/ui.tsx` now comes from the generated schema.
- `seed_programs` creates its offers **switched off**, so nothing goes on sale at a placeholder price.

**Tests:** new `test_refund_gives_the_place_back` (B2C), and the B2B wrong-amount test now expects the stored error.
Run: `test_program_buying`, `test_program_seats`, `apps.delivery`, `apps.learning`: 44 tests OK.
`makemigrations --check` clean, ruff clean, `tsc -b` clean, `vite build` passes (entry 142.9 kB, unchanged).

**Recorded, not fixed:** client questions #45 (one person with a personal place and a company seat), #46 (a seat
holder leaving the company), #47 (module learners and workshops). B2B seat orders get no invoice row (the seat
orders list is their record). Console seat swaps: the newest 100 (known limit since M22).

**Migration the user must run:** `learning.0016_seat_counts_access` (with the others, `--database owner`).

## M23 Seed the real programs (2026-11-17, Part 2 built; Part 1 waits for the user)

Brief: `docs/milestones/M23-merge-and-seed.md`.

**Part 1, the old live cohorts merge, is not built.** The plan's merge doesn't fit the data (old cohorts belong to
short courses). The options are in `docs/NEEDS-USER.md` #1. Nothing on the old live tables was changed.

**Part 2: `python manage.py seed_programs`** (`apps/delivery/management/commands/seed_programs.py`)
- Reads one file per program from `backend/apps/delivery/seed/programs/*.json`. Today these are PCP, MM and ME.
- The files are **provisional** (`docs/NEEDS-USER.md` #2): the real module titles and standards from LMS_v2, with
  4 weeks of LMS_v2's standard week per module. MBA has no file until its modules are known. When the real
  structure is exported, only the files change.
- The standard week: a live session (2 h OTJ and CPD), a reading (2 h) and a reflection assignment (30 min).
  LMS_v2's recording and video slots are left out: recordings come from each group's Teams session, and a video
  needs a real upload.
- For each program, through the normal services:
  - the program, owned by the platform, published;
  - its KSB standard: already imported, given in the file, or looked up on the standards feed (`--offline` skips
    the feed); components mapped to KSBs where the file maps them;
  - settings: the standard and an OTJ target of 6 hours a week (from the file);
  - offers: the whole program live and recorded, and each module recorded, at one placeholder tier (client
    question #33). The provider sets real prices in the console;
  - a running cohort (the latest intake at least three weeks old that still has two weeks to teach, else the
    Monday three weeks ago) and a planned one (the next intake), each with two groups, the demo tutor and a weekly
    timetable;
  - 12 demo learners (`<key>.learnerNN@learnhub.example.com`, no usable password) placed in the groups;
  - planned sessions for every group, and for the running cohort: attendance for past sessions, completed
    readings, and two OTJ logs each (one approved by the tutor, one waiting).
- One transaction per program. A program whose slug exists is skipped. `--only PCP MM` seeds some; `--by` names
  the staff author (default: the first superuser).
- It never notifies anyone, never sends mail and never creates Teams meetings:
  - `engagement.notify.muted()` (new) wraps the whole seed, so no notice or email goes out whatever the templates
    say;
  - `plan_sessions` gained `sync=False`. Staff create the meetings from the console.
- The tutor is always the demo tutor (`contact+dfaf885b3a70@example.com`, no password), never a real staff member. It gets
  a role that may only teach groups (an existing one, else a new "Tutor" role), never an admin role.
- `--by` with an unknown email stops with an error instead of falling back.

**Reviewer fixes**
- The seed could notify demo learners (OTJ approvals) and email them if staff switched that template's email on.
- On about half of all dates the "running" cohort had already finished (an intake up to 20 weeks old for a
  12-week program).
- Demo groups could be given to a real staff tutor. A matching role could be an admin role.
- A mistyped `--by` was silently ignored.
- Known limit: automatic OTJ hours for completed readings are dated the seed day (the service dates them "today").

**Tests:** `apps.delivery.tests.test_seed_programs`, 3 tests, OK:
- a program from a test file: published, standard and mapped KSBs, settings, offers, two cohorts with two groups
  each, 12 learners placed, sessions, attendance, readings and OTJ logs;
- with Teams counted as connected, no meeting job is queued; no notification is created;
- the demo tutor has no password and only a teaching role;
- a second run creates nothing (16 tables counted);
- for every day of a year and every real file, the running cohort is three weeks old or more and still has weeks
  left;
- the real files are valid.

ruff is clean.

**Full backend suite (2026-11-17, first long-test run):** 465 tests, 464 passed, 1 failed:
`core.tests.test_query_budgets` "me" (11 → 10 queries). The cause: platform settings are cached for 60 s, and on
Neon a page round takes over a minute, so a settings reload landed in one count but not the other. The budget test
now leaves out settings reads (a fixed, timed cost, never per row). Re-run: 4 tests OK (with the seed tests).

**Not run on Neon.** It is a command the user runs (`docs/user-actions.md` #5), after the M18 to M22 migrations.

## M22 B2B program seats: company signup, orders, allocation, swaps, line manager view (2026-11-16, built; long tests pending by user decision)

Brief: `docs/milestones/M22-b2b-program-seats.md`. Plan D8–D11, D22. **D29 is lifted for B2B**: companies can buy
seats on programs and modules.

**Tests: small targeted tests only.**
- `apps.corporate.tests.test_program_seats` covers:
  - signup locks the workspace;
  - order rules;
  - checkout and the paid webhook (wrong amount refused, retries ignored);
  - expiry;
  - an old Stripe page's expiry not resetting a newer one, and a just-paid page never replaced;
  - allocation (group placement, module scope, no seat left, a manager's area, release before starting);
  - swaps (company step, cut-off reason, tutor refused, provider reject and approve, the old progress kept);
  - the team view's scope and a query count that doesn't grow with rows.
- Regression set: `core.tests.test_api_contract`, `core.tests.test_rls`, `apps.commerce.tests.test_program_buying`, `apps.delivery`, `apps.org`, `apps.corporate` and `apps.learning` pass (147 tests); after the reviewer fixes, `test_program_seats`, `test_program_buying` and `apps.delivery` pass again (29 tests).
- ruff, `makemigrations --check`, `tsc -b`, oxlint and `vite build` are clean.
- The main entry is 142.9 kB (was 140 kB): the new routes, the menu item and the workspace guard.

**Built**
- **Data (additive, new tables).** `SeatPurchase.offering` and `AllocationEvent.allocation` are NOT NULL, so program
  seats have their own tables rather than altering those columns:
  - `corporate.ProgramSeatOrder`, `ProgramSeatLine`, `ProgramSeatAllocation`, `SeatSwapRequest`, `ProgramSeatEvent`
    (the audit trail);
  - `company_only` RLS on all of them, plus composite foreign keys so two companies' rows can never be linked;
  - `Organization.onboarding_state` (db_default `active`: existing companies are unchanged);
  - three `ProgramSetting` columns (minimum seats per line, swap cut-off mode and value);
  - `EnrollmentModule.Source.SEAT`;
  - staff permission `seats.approve_swap`.
- **Signup and the gate** (`POST /corporate/program-seats/signup`, `/business/start`): the company starts at
  `ordering`.
  - `core.permissions` refuses every workspace endpoint with `workspace_locked` until the first order is paid. Only
    setup, catalogue, draft and checkout pass `allow_setup`. It is still one query.
  - The frontend guard sends a company still being set up to `/business/start`.
  - The user menu has "Train your team" and "Finish setting up …".
- **Order** (one draft per company): server prices from the offer's tier in the company's currency, seats ≥ the
  program's minimum, and live lines need an intake with enough places across every line.
  - Checkout re-prices; `prices_changed` re-saves the draft.
  - Changing an order closes its open Stripe page first; a page that was paid a moment ago is kept (`already_paid`).
  - The webhook checks session, amount and currency, then opens the workspace. Expiry of the current page only
    goes back to the draft.
- **Allocation** (`/business/program-seats`): owner, admin or a manager for people in their units.
  - It gives a company enrolment that covers exactly what the person's active seats pay for (`_resync`): the whole
    program, or modules.
  - Live seats go to the group with the most room. A full intake leaves the person in the cohort and cohort
    managers are told.
  - Placement locks are now advisory (`placement._advisory`), and capacity is counted through
    `learning.cohort_seat_counts`, so company and learner requests can place without seeing others' rows.
  - Release only before the learner has started.
- **Swaps**:
  - A request; the company step is skipped when the requester may approve it (owner, admin, or the new person's
    line manager).
  - Past the program's cut-off (progress % or cohort week), a reason is required and the request is flagged.
  - The provider decides in Console › Seat swaps (`seats.approve_swap`). Approving revokes the old enrolment
    (progress kept) and gives the seat to the new person, in the old group first.
  - Every step is in `ProgramSeatEvent` and the audit log, with notifications to approvers and requester.
- **Line manager view** (`/business/team`): progress, KSBs met, OTJ RAG and hours, and attendance, for the caller's
  area. Keyset pages; a table on desktop, cards on a phone.
- Console › Programs › Settings has a "Company seats" card.

**Reviewer fixes**
- An expiry webhook from an older Stripe page reset the order waiting on a newer one (charged, never credited).
- A just-paid page could be replaced on a second "Pay".
- `/business/start` fell into an endless skeleton after payment and for admins of open companies.
- Staff placing a seat holder from the console created a free personal enrolment. `place()` now uses their company
  enrolment.
- A returning seat holder skipped the capacity check: a seat-less enrolment now leaves its group.
- KSB data is now batched across programs.
- Holders were stale after a company swap decision.
- The new person's managers are now told about swaps.
- The places check now spans every line on the same intake.
- The team view now has a Ring.

**Known limits (recorded, not fixed)**
- Releasing one seat is refused once the person has started anything on that program, because the check is on the
  shared enrolment; use a swap.
- Console › Seat swaps shows the newest 100.
- The team view's queries grow per program on the page (component lists) and per cohort schedule (cached), not
  per row.

**Client questions:** #35 updated; new #41 (company prices), #42 (holding intake places), #43 (company refunds),
#44 (who approves for the company).

**User actions:** tick **Approve company seat swaps** on a staff role (`docs/user-actions.md` #3).

**Migrations the user must run** (`python manage.py migrate --database owner`; all additive):
- `org.0003_onboarding_state`
- `delivery.0007_seat_settings`
- `learning.0015_enrollment_module_seat` (choices only, no SQL change)
- `corporate.0017_program_seats`
- `corporate.0018_program_seats_security` (RLS and composite foreign keys)
- `engagement.0012_program_seat_templates` (inserts four notice wordings)

## M21 B2C buying: program offers, seats, modules, monthly payments (2026-11-16, built; long tests pending by user decision)

Brief: `docs/milestones/M21-b2c-buying.md`. Plan D5–D7, D10. **D29 is lifted for B2C**: a published program with an
active offer is listed, priced ("From £X") and sold. B2B selling stays hidden until M22.

**Tests: small targeted tests only.** The new `apps.commerce.tests.test_program_buying` (offer rules and permissions,
listing, emptiest-group placement, full intakes, module-only access in the player, refund then token unlock, the whole
monthly plan: first payment fulfils, repeats ignored, wrong amount refused, failure pauses after the grace period, late
payment restores, last payment completes and cancels, token module unlock) passes. `core.tests.test_api_contract`,
`core.tests.test_rls`, `apps.commerce.tests.test_commerce`, `test_unlock`, `apps.learning`, `apps.catalog`,
`apps.delivery` and `core.tests.test_api_learner` pass. ruff (check + format), `makemigrations --check`, `tsc -b`,
oxlint and `vite build` are clean; the main entry is still 140 kB.
- **Watch in the long tests:** `core.tests.test_query_budgets.test_pages_do_not_query_per_row` failed twice on
  pages M21 doesn't touch (compliance dashboard 14 → 13, then assignments 10 → 9): the count went **down** on the
  second call, a warm-cache effect, not growth. Look at it in the full-suite run.

- **Offers** (`commerce.ProgramOffer`, Console › Programs › program › **Offers**, `programs.build`): whole program or
  one module, live or recorded, a price tier, tokens for recorded modules (D6), up to 24 monthly payments for live
  places (D7). Switched off, never deleted. Database constraints back every rule.
- **Intakes**: the program's planned/open/running cohorts with an active group; places left = the groups' spare
  places capped by the cohort. Counted by the SECURITY DEFINER `learning.cohort_seat_counts` (numbers only).
- **Checkout** (`POST /commerce/programs/checkout`): server-side price from the tier; a live place needs an intake.
  Paid in full = a normal order (existing webhook, amount check, receipt, success page). After payment the learner
  goes to the active group with the most spare places (`placement.place` re-checks under a lock); if a race filled
  every group they keep the place in the cohort without a group and cohort managers are notified.
- **What an enrolment covers**: `Enrollment.scope` (`program`/`modules`) and `learning.EnrollmentModule`. The player
  refuses lessons in other modules (`module_locked`) and marks them locked with a "See buying options" link.
- **Monthly payments** (`commerce.InstalmentPlan`, `InstalmentPayment`): Stripe Checkout in subscription mode with an
  inline monthly price of ⌈price ÷ N⌉. Each paid invoice is counted once (unique invoice id); the first fulfils the
  order; after the Nth the subscription is cancelled (an already-cancelled subscription counts as done). A failed
  payment sets `grace_until` (setting `payments.instalment_grace_days`, default 7) and access pauses then; the
  player says "Your access is paused" and the notice links to Account › Orders, which shows "2 of 6 paid" and an
  "Update your card" button (Stripe billing portal). While a plan runs, nothing else is sold for that program.
- **Tokens** (`POST /commerce/programs/unlock-module`): recorded modules, spent once under an advisory lock.
- **Refunds**: a program paid in full follows the refund window, but only when it is all the learner holds in that
  program; monthly plans are refunded by staff in Stripe (client question #34).
- **Reviewer fixes**: a refunded module came back after any later unlock; a second purchase cut the enrolment loose
  from its monthly plan (stopped plans kept access; paused learners were offered a second plan); a lost Stripe
  cancel response could end a fully paid plan; refunding one line revoked access bought in other orders; one query
  per order on the orders list; offers of a removed module couldn't be switched off and null PATCH values gave a 500;
  paused learners got a generic error.
- **Client questions**: #33 and #34 now record the defaults; new #39 (grace period) and #40 (who sets prices).
- **Deferred**: coupons and promotions don't apply to programs; no waitlist when every group is full (#31); recorded
  learners don't yet see the group's session recordings (a "master recording" per program).
- **Migrations the user must run** (`python manage.py migrate --database owner`; all additive):
  - `commerce.0011_program_offers`, `commerce.0012_program_offers_security`
  - `learning.0013_enrollment_scope_modules`, `learning.0014_enrollment_modules_security` (a SECURITY DEFINER function)
  - `engagement.0011_program_buying_templates` (inserts two notice wordings)

## M20 Live sessions, recordings and workshops (2026-11-16, built; long tests pending by user decision)

Brief: `docs/milestones/M20-live-sessions-workshops.md`. Plan D3, D14, D17–D19, D24. Teams setup guide:
`docs/teams-setup.md` (the user action is in `docs/user-actions.md`).

**Tests: small targeted tests only.** `apps.delivery` (including the new `test_live`: planning, scope, join window,
manual and Teams attendance → OTJ with a fake Graph transport, workshop capacity, booking and CPD), `apps.learning`,
`core.tests.test_api_contract` and `core.tests.test_rls` all pass. ruff (check + format) is clean,
`makemigrations --check` is clean, and `tsc -b`, oxlint and `vite build` pass. The main entry is 140 kB (+2 kB for the
new routes).

- **Sessions** (`delivery.LiveSession`, one per group and live component):
  - "Plan sessions" dates each one on the group's weekday inside the component's week, falling back to the next
    working day if that day is off. Weekend groups keep their own day.
  - Times come from the group timetable in the provider time zone (`general.time_zone`) and are stored in UTC.
  - Re-planning moves only future sessions with no attendance, never brings back a cancelled one, and never deletes.
  - Managers move or cancel sessions. Tutors (their own groups only) add links, mark attendance and upload
    recordings.
- **Teams** (`catalog/teams.py`, app-only Graph): meetings are created or moved after commit by Celery, and only the
  attendee join link is kept. Attendance reports are matched by email, and staff marks always win. Recordings are
  copied by the `delivery.live_followup` beat job (every 30 min) and **streamed through the Celery worker** to Bunny
  (not a Bunny fetch: Graph needs a token).
  - The job claims each recording first, tries up to 5 times, and one failure never stops the rest.
  - It tries attendance for 2 days.
  - Without Teams everything works by hand: paste a link, mark attendance, upload the recording (TUS).
- **Attendance → OTJ**: present (≥ setting `learning.live_present_min`, default 3) gives one automatic OTJ entry per
  session or workshop, capped at the length. Re-marking updates it and marking absent removes it.
- **Workshops** (`delivery.Workshop`, `learning.WorkshopBooking`): capacity under a per-workshop advisory lock.
  Learners only see their own rows under RLS, so places are counted by a SECURITY DEFINER function that returns
  counts only. "Present" gives the workshop's expected OTJ minutes, and attended workshops add CPD to the record and
  the program certificate.
- **Join window**: the link is sent only from `learning.live_join_early_min` (default 15) minutes before until the
  end, in the Sessions page and in the player.
- **Screens**:
  - console: the cohort group sheet's Live sessions, **My teaching** (`/console/teaching`, tutors) and
    **Workshops** (`/console/workshops`);
  - learner: **Live sessions** (`/learn/:slug/sessions`), linked from the player and My record.
- **New settings**: `learning.live_present_min`, `learning.live_join_early_min`, `learning.recording_pull_after_min`,
  `learning.teams_record_automatically` (client question #37).
- **Reviewer fixes**:
  - the workshop "Present" mark gave session minutes instead of expected OTJ minutes;
  - tutors could write to any workshop (now read only, per brief B6; client question #38);
  - re-planning brought back cancelled sessions;
  - weekend groups got no sessions;
  - the recording job could copy twice, and one error stopped the run;
  - jobs weren't ordered and attendance was retried forever;
  - N+1 on recording libraries;
  - the player ignored cancellation and the join setting;
  - a too-short or too-long timetable caused a 500;
  - capacity changes raced bookings;
  - a cleared Teams link left the session stranded;
  - two meetings could be created at once;
  - uploads were possible before the event;
  - stale caches (booking after "full", My teaching);
  - the workshop program picker showed only the first page;
  - "Attended" showed under the threshold;
  - phone overflow on long titles.
- **Learned the hard way:** `SELECT … FOR UPDATE` on a reference table fails for learners under RLS (they can't
  update it), so booking uses an advisory lock. Learner counts across users need a SECURITY DEFINER function.
- **Deferred**:
  - recorded-mode learners (the program's master recording) come with M21 buying modes;
  - no notifications yet for moved or cancelled sessions;
  - a recording upload's progress is lost if the sheet is closed, though the upload carries on.
- **Migrations the user must run** (`python manage.py migrate --database owner`; all additive):
  - `delivery.0005_livesession_workshop`, `delivery.0006_live_security`
  - `learning.0010_sessionattendance_workshopbooking`, `learning.0011_live_security`,
    `learning.0012_workshop_booked_counts` (a SECURITY DEFINER function)

## M19 KSBs, off-the-job hours and CPD (2026-11-16, built; long tests pending by user decision)

Brief: `docs/milestones/M19-ksb-otj-cpd.md`. Plan D12–D15, D25.

**Tests: small targeted tests only.** `apps.delivery` (programs + records), `apps.learning`,
`core.tests.test_api_contract` and `core.tests.test_rls` all pass. ruff (check + format) is clean,
`makemigrations --check` is clean, and `tsc -b` and `vite build` pass. The main entry is still 138 kB.

- **KSB standards** (catalog, reference data): `KsbStandard`, `KsbItem`, `ComponentKsb` (keyed by `lecture_key`,
  so the mapping survives new versions).
  - Import fetches by code from the setting `learning.ksb_feed_url`: https only, allow-listed hosts, no redirects,
    capped at 2 MB. Upload of the same JSON (IfATE shape or a plain shape, object or list) is the fallback.
  - Custom standards and items serve programs that aren't apprenticeships.
  - Console paths are `/console/ksb-imports/fetch|upload` and `/console/ksb-standards`.
- **Program settings** (`delivery.ProgramSetting`): the standard, the OTJ target (none / hours per week /
  total hours), the amber % and the daily cap. Console program page has new **KSBs** and **Settings** tabs.
- **Components** gain `expected_otj_min` (up to 1440: one ledger entry) and `cpd_min`, edited in the lesson editor
  for programs.
- **Off-the-job ledger** (`learning.OtjEntry`, unique per enrolment + source + ref): automatic entries when a
  component is completed. Learner logs (cap per day, row lock, no future days or days before joining) wait for the
  group's tutor or a cohort manager, who approves or rejects with a reason. The learner is notified. Nobody can
  approve their own hours.
- **RAG**: expected = target × teaching weeks **ended** in the learner's own span (from the day they joined).
  `total_hours` is pro-rated to that span.
- **KSB status** is computed from completion. **CPD** rolls up by module and program. **Module certificates** are
  issued when a module's required components are done, and their codes verify on `/verify` (new SECURITY DEFINER
  function).
- **Screens**:
  - learner `/learn/:slug/record` (Hours, KSBs, CPD, Certificates), linked from the player and from My learning;
  - console "Hours to approve" (`/console/programs/otj`);
  - a learner record sheet from the cohort page.
- **Reviewer fixes**:
  - RAG counted a week as owed on its first day, and owed late joiners weeks they couldn't log;
  - self-approval was possible;
  - OTJ minutes over 1440 were cut silently;
  - module certificate codes didn't verify;
  - the completion hook re-inserted every entry and queried Module and User on every flush (now it inserts only
    what is new);
  - My record went stale after completing a component;
  - hand-written response types, the upload shape (list), the feed size cap, the reject reason carrying over,
    the chip labels, and a clearer message when a tutor opens another group's record.
- **Deferred**:
  - module certificate PDF and KSBs on the program certificate (D25), which use the existing templates later;
  - the CPD roll-up by week;
  - the company (line manager) view, which comes in M22;
  - the Skills England feed URL is unverified, so upload is the fallback.
- **Migrations the user must run** (`python manage.py migrate --database owner`; all additive):
  - `catalog.0013`, `catalog.0014_ksb_security`
  - `delivery.0003_programsetting`, `delivery.0004_program_settings_security`
  - `learning.0007`, `learning.0008_programs_security`, `learning.0009_verify_module_certificate`
  - `engagement.0010_program_record_templates`

## M18 Program structure (2026-11-16, built; long tests pending by user decision)

Brief: `docs/milestones/M18-program-structure.md`. Plan and decisions D1–D28: `docs/features/programs-v1/plan.md`.

**Tests: small targeted tests only (user decision, 2026-11-16).** Ran `apps.delivery`, `apps.catalog`,
`core.tests.test_api_contract` and `core.tests.test_rls`, plus `apps.commerce.tests.test_unlock` and `test_packages`
after the review fixes (47 tests, all pass). **Long tests pending:** the full
suite, `e2e_m18.js`, the phone check and the light/dark screenshots. ruff (check + format) clean,
`makemigrations --check` clean, `tsc -b` and `vite build` pass. The main entry is 137 kB with vendors split out,
and the new pages are lazy chunks.

- **Programs in the catalog.** `Course.kind` is short or program. New `Module` per course version
  (`module_key` is stable across drafts). `Section.module` makes sections the program's weeks, and lectures are
  its components. Weeks keep one global position order (module by module), so progress, the player and certificates
  read them unchanged. Studio: `POST /studio/programs` (needs `programs.build`), plus module add, rename, reorder
  and delete (only when empty). Weeks reorder inside a module, and move between modules with a drop. The publish
  checklist asks for at least one module, no empty module and every week in a module.
- **Staff roles** (`identity.StaffRole`, `StaffRoleAssignment`, `core/staff_perms.py`). Permissions:
  `programs.build`, `cohorts.manage`, `groups.teach`, `roles.manage`, `reports.view`. Default roles are Admin,
  Curriculum designer, Cohort manager and Tutor. The seed migration gives Admin to every existing staff user.
  System roles can't be deleted, and the last role manager can't be removed.
- **Delivery app** (schema `delivery`): `Cohort`, `CohortModule` (optional per-module start), `Group` (tutor
  with `groups.teach`, weekday and times, capacity), `Holiday` (GOV.UK bank holidays for 3 divisions, synced
  monthly by Celery beat and by `sync_bank_holidays`), `Closure` (one cohort or provider-wide). A pure calendar
  (`calendar.py`) dates the weeks from the cohort start. It skips weekends, holidays and closures, turns a week
  with no working day into a break and warns on overlapping module starts. Schedules are cached in Redis, and a
  bump on any change refreshes them. Placement (`learning/placement.py`) locks the group and checks group and
  cohort capacity.
- **Console** (`/console/programs`, `/console/programs/:id`, `/console/cohorts/:id`, `/console/roles`).
  Programs list, new program, provider closures and holiday sync. Program: cohorts and structure. Cohort: status,
  edit, schedule with module start overrides, groups with members (add by email), closures. Staff roles: role
  cards, permissions and members. Every change is audited. New art variant `curriculum`.
- **Learner.** The player groups weeks under modules, with each week's dates, days off and a "This week" badge,
  and shows the learner's group (timetable and tutor). The course page shows "Program content" (modules, weeks,
  components).

**Migrations the user must run** (owner connection; all additive):
`core.0004_delivery_schema`, `catalog.0010_course_kind_module_section_module_and_more`, `catalog.0011_module_security`,
`catalog.0012_module_position_unique`, `identity.0005_staffrole_staffroleassignment`, `identity.0006_staff_roles_seed_and_security`, `delivery.0001_initial`, `delivery.0002_security`,
`learning.0006_enrollment_cohort_enrollment_group_and_more`. Then run `python manage.py sync_bank_holidays` once.

**Reviewer pass (2026-11-16), fixed:**
- Deleting a group with only ended enrolments gave a 500 (protected FK). Any enrolment now blocks the delete with a clear message.
- Cohort end dates went stale after a program was republished. Publishing now refreshes them after commit.
- "Last role manager" was never enforced, because any superuser counted. Superusers no longer count, and role
  changes lock every manager role first (no write skew).
- Curriculum designers could list learners' names and emails. Group members now need `cohorts.manage`, in the
  API and the UI.
- My learning now shows the group, the cohort and this (or the next) week's dates.
- The default cohort calendar and the minimum working days per teaching week are provider settings
  (`learning.program_calendar`, `learning.program_min_working_days`), not constants.
- Module positions are unique per version (a deferred constraint, migration `catalog.0012_module_position_unique`).
  Module and week changes lock the version row.
- Schedule cache bumps run after commit, and writers compute end dates fresh. Provider-wide closures and the
  holiday sync refresh end dates inline, without needing a worker. A calendar error is a 400, not a 500.
- Closures and module start dates are refused on finished or cancelled cohorts. A cohort's capacity can't drop
  below its placed learners, and group edits lock the group (capacity race).
- The programs list uses a keyset cursor. It returns `can_build`, `can_manage` and the default calendar, so the
  page hides buttons people can't use.
- Weeks can move to another module from the ••• menu, so keyboard and touch users can do it, and an empty module
  can receive a week. "Add week" only spins on its own module.
- A superuser who isn't staff now gets every permission. Identity 0006 seeds a frozen copy of the default roles.
  `delivery` was added to the RLS structure test.
- Route names differ from the brief: `/studio/modules/{id}/weeks/order`, and console `/program-cohorts/…`,
  `/program-groups/…` and `/program-closures/…`.

**Decided by the user (2026-11-16): programs are hidden from selling until M21.** `Course.SELLABLE_KINDS` filters
the catalogue and search, cart and checkout, plan enrolment, token unlocks, packages and the business library.
Programs need no price to publish. The course page shows "Places are arranged by your training provider"
instead of buy buttons. Learners join only through staff placing them in a group.

Bugs found and fixed while building: Ninja path params broke under `from __future__ import annotations`.
`POST /programs/closures` was caught by `/programs/{program_id}`, so the routes moved to `/program-*` prefixes.
An unsaved `Group`'s pk is a DB default, so the code now checks `_state.adding`. Two schema names duplicated
corporate live training, so they were renamed.

## M17 HR system: Breathe HR (2026-11-16, built; tests pending by user decision)

**Tests: not written or run (user decision, 2026-11-16: "finish breathe and skip the tests").** No backend
tests for `apps.integrations`, no `e2e_m17.js`, no phone check or screenshots, no reviewer pass. Checked with
ruff (check + format), `makemigrations --check` (no changes), `tsc -b` and `vite build`. The brief's test list
(`docs/milestones/M17-hr-system.md`) is the to-do list when tests come back.

- **Backend app `apps.integrations`** (schema `integrations`, 7 tables, all `company_only` RLS, composite
  same-company foreign keys): `HrConnection`, `ExternalPerson`, `ExternalDepartment`, `HrTrainingMap`,
  `ExternalTrainingRecord`, `ExternalLeave`, `HrSyncRun`.
  - API key encrypted at rest (Fernet, key from `CREDENTIAL_ENCRYPTION_KEY`); never returned by any endpoint.
  - Breathe client (httpx): host allow-list (`api.breathehr.com`, `api.sandbox.breathehr.info`), no redirects,
    rate limit, retries honouring `Retry-After`, `Link` pagination with a loop guard.
  - Sync: **hourly** (Celery beat `hr-sync-hourly`, minute 15, one run per company per hour) plus **Sync now**
    (Q24). One run at a time per company (409 `already_running`).
  - People: never added automatically. Matched by email as a suggestion; an admin links, invites (normal
    invitation email) or ignores. Leavers are **flagged**, never removed (Q27). Departments link to units (or
    create one); linked people are placed in it (add-only), line managers become unit managers (Q25/26).
  - Training: each Breathe course title maps to a requirement; records become `CompletionRecord`s (source
    import, expiry from the requirement), then compliance recomputes and renewals open (Q28).
  - Leave: approved leave only, never the reason; "On leave until …" for admins and managers (Q23).
  - Notifications: `hr_sync_failed`, `hr_people_to_review`, `hr_connection_attention` (insert-only migration),
    all linking to `/business/hr-system`. Every change is audited.
  - 19 endpoints under `/api/v1/integrations/hr…`, all typed (`Hr*` schemas); prefix added to `TYPED_PREFIXES`.
    Admin for changes, manager (own scope) for reads.
- **Frontend:** `/business/hr-system` (Company nav, "HR system", new `handover` backdrop). Connect card (key,
  live/sandbox, feature switches, what we read and never do); connection card (status, last sync, Sync now,
  Check connection, Replace key, Pause/Resume, Settings, Disconnect); four counters; tabs People (review queue,
  filters, search, side sheet to link / choose someone / invite / ignore / review again), Departments, Training,
  History. Polls every 3 s while a sync runs, then refreshes people, units and compliance. Managers see it
  read-only. Badges elsewhere: Person page "Synced from Breathe HR", "Leaver in …", leave; People page "On leave
  until …" (one call per page); Units page linked Breathe departments.
- **Entry chunk 127 KB → 133.6 KB**: the two new backdrops (`folio`, `handover`) and the footer/hash-scroll code
  load on every page. The HR page is its own 30 KB chunk.

### Migrations the user must run (dev and e2e; adds a schema, tables and rows only)
`python manage.py migrate --database owner`: core **0003_integrations_schema** (creates schema `integrations` +
grants), integrations **0001_initial** and **0002_security** (RLS + composite keys), engagement
**0009_hr_system_templates** (inserts three notification wordings). Check first with `sqlmigrate`.
**Dev: applied by the user on 2026-11-16 (SQL reviewed first; `check` clean). e2e: still to run.**

### Setting the user must add
`CREDENTIAL_ENCRYPTION_KEY` in `backend/.env` (any random string, 32+ characters; keep it: changing it makes
saved HR keys unreadable and admins must re-enter them). Without it the page says HR connections aren't set
up yet. New dependency: `cryptography` (approved in the brief); run `pip install -r requirements.txt`.

## Polish and client answers (2026-11-16)

- Client questions 23–28 answered and closed (leave to admins and managers, hourly + Sync now, departments,
  managers, leavers flagged, training counts). Q29: **privacy and terms pages written** (`/privacy`, `/terms`,
  live values from settings: platform name, contact email, refund window, VAT); still need the client's legal
  review. Sign-up links to both.
- New console setting `general.contact_email` (validated as an email). Footer rebuilt as four real columns
  (Learn, Business, LearnHub, Legal); mail links only appear once the contact email is set. `#teams` and other
  hash links scroll to their target after the page loads.
- "Publish without review" restored in the studio submit (the M5 brief still lists it).

## Testing round (2026-11-16)

Full backend suite run and every failure fixed. All but two were stale tests after the team's rule changes
(publish now needs a cash/free price, error shape, seat counts, query budgets warming caches): tests updated,
new helper `priced_for_publish` in `core/tests/factories.py`. **Two real bugs fixed:** B2C subscription checkout
returned 500 (wrong gateway call signature; a new autospec test pins it), and invalid `pattern` regexes on three
console forms (browsers rejected them). E2E M1 and M5 passed; M4, M6 and demo not re-run (tests then paused).

## Step 2: M6 polish, code part (2026-11-15)

**Tests: pending (user decision).** Not done yet, by decision: query-budget tests, Lighthouse, `e2e_demo.js`,
the phone check, the reviewer pass and the hands-on keyboard/contrast checks (P3). Checked with `tsc -b`,
`vite build`, ruff and `manage.py check`.

- **P1 placeholders:** `ComingSoon` removed. Footer entries were plain text: now real links (catalogue, plans,
  verify, team plans, company workspace, "Book a demo" to the plans page's sales email, teach, help). "Privacy"
  removed: no policy page yet (client question 29). `/design` (sample data) is registered only in development.
- **P2 performance:** vendor chunks (`vendor-react`, `vendor-query`, `vendor-radix`) via Rolldown
  `codeSplitting`. Main entry **351 KB → 127 KB** minified (target < 300 KB). First-load JS about the same
  (+9 KB), but vendor code now caches across deploys. Thumbnails were already lazy; remaining `<img>` are logos.
- **P4 titles:** every route has `handle: { title }`; `SiteRoot` sets "Title · LearnHub" (layout effect, so pages
  that set their own still win); the course page uses the course name. Before, ~70 routes shared one title.
- **P4 wording:** the console token page showed "F02" and "the backend" to staff; reworded.
- **P4b mockup gaps:** header search has instant suggestions (mockup 37): categories and courses as you type,
  "Search for …", keyboard combobox (`useSearchSuggestions`). My learning (mockup 42) has a side column: counts,
  **Upcoming deadlines** (open company requirements, soonest first; there are no assignment due dates in the
  data model) and **My certificates** with download. No backend change.
- **P5 artwork:** the six B2C pages drew their own backdrop on top of the layout's (doubled shapes): removed.
  Route → artwork table completed in `frontend/README.md`.
- **P6:** `docs/demo-script.md` (5 personas, logins as "ask Zeeka").
- **P7:** `docs/deploy.md` (env vars by name, settings guard, migrations, webhooks, processes, `.htaccess`,
  smoke checks). `check --deploy` locally stops on the secret key and `FRONTEND_URL` only (dev values).

## Step 1: make the B2C work usable (2026-11-15, user's own repo `learnhub_demo`)

**Tests: pending (user decision, 2026-11-15: no tests or E2E until the user asks).** Checked only with
`manage.py check`, ruff on the changed files and `tsc -b`.

- **Routes:** already wired before this step (the PR1/PR2 notes below say "not router-wired"; that is out of
  date). `/wallet`, `/wallet/buy`, `/wallet/result`, `/subscription`, `/packages`, `/checkout/review`, console
  `token-pricing`, `wallets`, `packages`; user menu and console nav entries exist.
- **Checkout types:** the corporate schemas were already renamed `CorporateCheckoutIn/Out`. Regenerated
  `schema.d.ts` (it was also behind the team's backend: postponements, departures, token rate fields) and
  removed the `useCheckout` cast workaround. `sendHeartbeat` now defaults `flush_now` (the old types had been
  hand-edited to make it optional).
- **Player access for full-course unlocks (bug):** a full-course token unlock or a cash package created only a
  `ContentEntitlement`, so "Start learning" led to a player with no enrolment. User decision: enrol on full access.
  - `apps/commerce/unlock.py::enrol_on_course_access` creates (idempotently) a personal `Enrollment`
    (source `purchase`, or `admin_grant` for a staff grant; `source_ref` = the entitlement; expiry = the
    entitlement's). Called by `unlock_course` and `packages.fulfil_package`.
  - New `POST /api/v1/commerce/tokens/access/course/{course_id}/enrol` (`CourseAccessEnrolOut`) for access gained
    before this change; the course page calls it from "Start learning" (`useEnrolWithAccess`).
  - The Unlimited plan already enrolled through `plan/enroll`; single-lecture unlocks stay on the course page.
  - Known gap: revoking or refunding an entitlement does not yet end its enrolment.
- **Bug:** the course page's access badge keys (`package`, `token`, `admin`, `legacy`) never matched the
  resolver's sources, so it always said "You have access". Keys fixed.
- No migration.

## Site-wide dark-mode native-control fix (2026-11-12)

- Native form controls now inherit the active browser `color-scheme`; `select` option
  sheets have explicit surface/text colours, fixing white Windows/Chrome dropdowns with
  unreadable dark-mode text across every shared `NativeSelect` usage.
- Browser autofill, native popup scrollbars, the document/root canvas and the browser
  theme colour now follow light/dark mode without white flashes.
- Intentional white document surfaces (certificate previews and QR codes) are unchanged.
- Verification: TypeScript and the production build pass; focused lint is clean. A
  headless Chrome dark-mode capture confirmed the page canvas, loading state, header and
  footer remain dark. The live logged-in Chrome inspection was unavailable because its
  window was minimised; the compiled CSS contains the native option/autofill rules.

## B2C-FE PR1 — Learner wallet & monetization UI (2026-11-11, built, not yet router-wired)

Developer A (B2C), branch `feat/frontend-b2c-v2`. The learner-facing half of the B2C v2 frontend.
Owner decision (2026-11-11): build the learner surface first, admin console after.

**Shared baseline (integrator step, done first):** regenerated `frontend/src/api/schema.d.ts` from the
audited backend (`tools/dump_openapi.py` → `openapi-typescript`). The committed schema predated the
whole token backend; it now carries all 15 `/commerce/tokens/*` learner endpoints and the
`/console/pricing/token/*` + `/console/wallet/*` admin surface.

**New files**
- `frontend/src/features/b2c/api.ts` — typed query/mutation hooks for wallet, packs, rate, top-up
  limits, access resolver, unlock, cash packages, subscriptions. Every money/wallet call sends
  `X-Org-Id: ''` (personal). No amount is computed in the browser.
- `frontend/src/features/b2c/UnlockButton.tsx` — the single content gate. The server access resolver
  decides whether to show a purchase prompt at all, so a person with existing access (subscription,
  package, legacy, prior unlock) is never asked to pay again. Confirm-to-spend dialog; 409 treated as
  already-unlocked; insufficient balance routes to buy tokens. No optimistic unlock.
- `frontend/src/pages/b2c/WalletPage.tsx` — balance, expiring-soon (FEFO) warning, grants + ledger tabs.
- `frontend/src/pages/b2c/TokenBuyPage.tsx` — token packs + custom top-up (truthful "no rate configured"
  state when `/rate` is null; min/max from `/topup-limits`; token estimate is preview-only).
- `frontend/src/pages/b2c/TokenResultPage.tsx` — Stripe return for packs/top-ups. Polls the wallet
  balance against a pre-checkout baseline (sessionStorage); never grants from the URL; graceful timeout.
- `frontend/src/pages/b2c/SubscriptionPage.tsx` — unlimited personal plan: plans, checkout, active
  status (active/trialing/past_due), renewal/cancel state; manage/cancel via the Stripe billing portal.
- `frontend/src/pages/b2c/PackagesPage.tsx` — cash course bundles; success lands on My Learning (real
  server-granted enrolments).
- `docs/features/b2c-monetization-v2/frontend-b2c-route-manifest.md` — route/nav manifest for the integrator.

**Workaround (contained):** `frontend/src/features/commerce/api.ts` `useCheckout` now asserts the true
commerce checkout shape, because the B2B `apps/corporate/api.py` reuses the Ninja class names
`CheckoutIn`/`CheckoutOut` and corrupts the generated types. Runtime is unaffected. See NEEDS-USER item 0.

**Checks:** `tsc -b` clean, `oxlint` clean on the new files, `vite build` passes (main entry unchanged at
339 kB — the B2C pages aren't bundled until the integrator wires the router). No automated UI tests added
yet; no E2E yet; no browser screenshots yet.

## B2C-FE PR2 — CoursePage, catalogue exposure, admin console (2026-11-11, built, not router-wired)

Continues PR1 on the same branch.

**Backend (additive, typed):** `apps/catalog` now exposes the B2C token fields the learner UI needs.
`CourseDetail` gains `full_course_token_price`, `token_pricing_mode`, `in_subscription`; `LectureOut`
gains `id` (the unlock/access `target_id`), `token_price`, `is_free_preview`, `excluded_from_subscription`.
Populated in `apps/catalog/api.py::course_detail` (the curriculum selector already loads the rows; no
`.only()` to extend). Test added: `core/tests/test_m1_marketplace.py::…::test_course_detail_exposes_b2c_token_fields`.
`manage.py check` clean, `makemigrations --check` clean (no model/migration change). **The focused test
could not be run to green** — the shared Neon dev DB killed the connection mid-run ("terminating connection
due to administrator command" / deadlock), the documented shared-branch hazard; the change is verified by
`check`, the OpenAPI rebuild and `tsc`.

**Frontend added:**
- `pages/CoursePage.tsx` — resolver-gated: an already-entitled person (subscription/package/legacy/token)
  sees "Unlocked via …" and Start learning instead of any purchase prompt; a token full-course unlock path
  (`UnlockButton`) when `full_course_token_price` is set; per-lecture token badges in the curriculum; an
  "included in the Unlimited plan" cross-link.
- `features/b2c/console.ts` — admin hooks: price tiers, packs CRUD, rates, top-up policies, bonus campaigns,
  token audit, wallet detail/ledger/adjust, student search. Bodies typed straight from the schema.
- `pages/console/b2c/TokenPricingPage.tsx` — tabs: packs, exchange rate (handles `RATE_EFFECTIVE_FROM_PAST`),
  top-up limits, bonus campaigns (activation shown as blocked by F02), audit (paged).
- `pages/console/b2c/AdminWalletPage.tsx` — learner search → balance, grants, ledger, mandatory-reason adjust.

**Checks:** `tsc -b` clean, `oxlint` clean on all B2C files, `vite build` passes.

**Deferred (documented in NEEDS-USER 0b/0c):** player in-token-unlock (deliverable 7 — needs player-outline
exposure of lecture pk/token_price/lock-reason + the entitlement-vs-enrolment question); admin
per-course/-lecture price + distribution-preview UI (`__UNSET__` sentinels); per-material unlock (materials
not in the curriculum/player outline). **Deferred by boundary:** PlansPage team-subscription removal
(deliverable 10) — it is B2B company billing; left to B2B coordination per the owner's "don't touch B2B".

**Git writes (branch/commit) still not performed — awaiting owner authorization.**


## B2C-01 — Unified Content Access Engine (2026-11-10, landed)

Milestone brief: `docs/milestones/M9-b2c-token-unlock.md` (done section at the end).
The additive foundation for B2C content authorization. **No wallet spending, no Stripe
changes, no B2B logic changes.** New `platform.ContentEntitlement`, `platform.AccessAuditLog`
and `apps.platform.access.resolve()` wire into `learning._check_unlocked` for personal
enrolments. B2B assignments bypass the B2C resolver (`Enrollment.org_id IS NOT NULL`).

Migrations generated (NOT applied to Neon by this milestone):
- `platform 0004_accessauditlog_contententitlement` — the two new tables, all additive.
- `platform 0005_b2c_access_engine_rls_and_backfill` — user-scoped RLS on both tables
  plus idempotent `legacy_purchase` backfill (`ContentEntitlement` mirror for every
  non-expired personal `Enrollment`). Safe to re-run; the existing `Enrollment` row is
  never touched.

Unblocks: M-wallet / M10 (cash package fulfilment), M12 (course-outline bulk fast path,
Bunny/Azure/live-join gating), M16 (grandfathering completion).

## Where things stand (2026-11-08)
| Area | State |
|---|---|
| Backend | Complete for the demo: 191 tests in 42 files (counted 2026-11-08; the last full run was 103 at M3, the next is in the verification pass), ruff clean. All learner/business/studio/console APIs exist. |
| M0 foundation | Done: design system (`/design`), layouts, sign-in, workspace switcher, home, course page, My learning, HR compliance overview |
| M1 marketplace | Done |
| M2 learning | Done |
| M3 business | Done |
| M4 studio | Built (checkpoint, pushed). Its E2E, phone check and reviewer pass are moved to the final test round after M6 (user decision, 2026-11-07) |
| M5 console | Built: P1–P20 committed, every M5-gaps line ticked. Lean verification (section V); the full pass is deferred (below) |
| M6 polish | To do |
| Testing | **All browser testing happens after M6** (user decision): the E2E scripts for M4 to M6, the phone check, the reviewer and a full-site demo run. Backend tests are still written with each change |
| Deployment | To do: production migrate + seed, public webhooks (Stripe, Bunny), Azure CORS |

## M5 review fixes (2026-11-08, planner review; commit "M5 review fixes")
- **Stripe events added by the user (production endpoint `https://learnhub.abcsolutions.ai/api/v1/commerce/webhooks/stripe`):**
  `checkout.session.async_payment_failed` closes the pending order as failed and tells the buyer;
  `customer.subscription.paused / resumed / trial_will_end` tell the subscriber (access already follows the
  status); `pending_update_*` re-sync; `invoice_payment.paid` and `payout.paid` are stored and ignored on purpose.
  The handler also uses `invoice.payment_failed` and `charge.succeeded`: add them in Stripe. New wording:
  engagement **0008_payment_notices** (insert only), applied on dev and e2e; production runs it on deploy. Tested.
- **Forgot password (user request):** `/account/password/reset` (email → link, same answer for unknown addresses)
  and `/account/password/reset/key/:key` (link checked first; new password with show/hide, strength meter and
  confirm; expired or used links offer a new one). Uses allauth's headless reset endpoints; the email links to
  `FRONTEND_URL`. Backend test covers the whole flow, one-time links and unknown emails.
- **Bug (user): a fully watched video said parts were skipped.** The lecture was saved with length 0 (the video
  was attached before Bunny finished encoding it), and completion ignored lectures without a length. Completion
  now uses Bunny's length for the video when the lecture has none, and when Bunny reports a length, lectures
  still at 0 get it. Tested. Existing lectures already at 0 with a ready video keep showing 0 as their length
  (a one-off data fix on Neon needs the user's OK); they do complete now.
- **Bug (user): "Learning as" Personal / company did nothing.** Switching removed cached data but did not reload
  what was on screen. It now resets those queries (the page reloads for the new space) and confirms the switch.
- **Bug (user, 2026-11-08): "Lecture finished" but the lecture wasn't ticked.** With Redis on, watch time sits
  in Redis until the once-a-minute Celery flush, so the player's check 2.5 s after the end found nothing. The
  beat sent when a video ends (`heartbeat` with `ended: true`) is now written at once and returns
  `completed`; the player says "Lecture complete", or explains that skipped parts mean it isn't complete yet.
  The rule is unchanged (real watch time ≥ the lecture's minimum, 90% by default). Tests added.
- **Neon migrations and seeds (user said Claude Code runs them).** `showmigrations` was checked before each run;
  every pending migration was additive. **dev:** already migrated and seeded when checked (by the planner, 08:26 UTC);
  then identity **0003_instructor_invites** applied, and `seed_console_demo` re-run (added the instructor earnings
  and 25 certificates). **e2e:** the 11 pending migrations (engagement 0005, catalog 0005, identity 0002, the 9 M5
  ones) applied, then identity **0003_instructor_invites**; `seed_console_demo` ran. `seed_demo` on both: demo
  data already there, so it refused and changed nothing (never reset). e2e runs use `tools/harness/on_e2e.py`
  (loads `backend/.env.e2e` without printing it).
- **2-step sign-in QR code:** `GET /identity/mfa/totp-qr` draws the pending key's QR as SVG on the server with
  allauth's own `qrcode` (no new dependency); the set-up card shows it next to the key. Only signed-in users
  with a set-up in progress get one; the key is never in the response as text (tested).
- **Studio > course builder > Certificate tab (mockup 23):** pick the platform default, an approved platform
  template or an approved own design; design your own (style, colours, wording, what's shown, signatory) with
  the live preview. Own designs go to staff for approval (pending / not approved with the reason shown); editing
  an approved one sends it back for approval.
- **`seed_console_demo` earnings:** seeded paid orders get sale earnings and refunded items refund earnings,
  dated like the order, so commissions, balances and payouts match sales (adds rows only; tested).
- **Settings > default currency** now decides a new visitor's first currency (server: `?currency=` → saved
  preference → setting → GBP, active currencies only; the currency menu shows the same). Tested.
- **Pending instructor invitations (client question 22):** new table `identity.instructor_invites` (staff-only
  RLS). Console > Instructors > Invitations lists invitations not yet accepted or cancelled (expired ones too),
  with Resend (fresh 7 days, audited) and Cancel (every emailed link for it stops working, audited). Inviting the
  same email again reuses the pending row. Accepting closes it. Links sent before this change still work.
- Checks (lean, section V): ruff clean, `makemigrations --check` clean, `tsc -b` and `vite build` pass (main entry
  unchanged at 372 kB). Tests run: seed, MFA QR, default currency, console people (invites), API contract, RLS: all OK.
  The full suite is not run now (user, 2026-11-08): it belongs to the verification pass.

## M5 console (2026-11-08, built; verification pass pending)
Every control in mockups 26, 25, 45, 05, 22, 20, 13, 33, 30, 36, 18 and 02 is wired to the real API; no
`ComingSoon` page is left. Packages, one commit each: P1 contract/routes/nav/search, P2 `seed_console_demo`,
P3 dashboard, P4 approvals, P5 courses, P6 students and instructors, P7 sales, P8 subscriptions, P9 pricing,
P10 promotions, P11 commissions, P12 payouts (+ `/studio/payouts`), P13 certificates, P14 communications,
P15 moderation (+ learner Report), P16 companies, P17 reports, P18 settings (+ 2-step sign-in), P19 audit.
Built by four parallel helpers by area plus the coordinator; every helper's suites were re-run by the
coordinator before committing (B 36, D 31, A+C 69 tests: all OK).

**Checks run (lean, section V):** backend tests per area (above), ruff, `makemigrations --check` clean,
`tsc -b` and `vite build` pass. The main entry chunk grew 363 → 372 kB: the site-wide wrapper (`SiteRoot`:
banner, maintenance page, branding) and the 2-step sign-in hooks load on every page by design.

**Seeding:** `python manage.py seed_console_demo` after `seed_demo` (dev and e2e, after the migrations). Adds
only; every row has a fixed marker, a second run adds nothing (tested). Seeded learners have no password. Its
orders get instructor earnings through the real `record_sale` / `record_refund` path (review fix, below).

**Bugs found and fixed while integrating**
- Duplicate schema names across helpers (`ConsoleReportOut`, `ConsoleActivityOut`, `ConsoleCoursePriceIn`): renamed.
- Price rule "Apply" crashed (`select_for_update` over a nullable join): it now locks the rule row only.
- `/people/{user_id}` swallowed `/people/students` (405): account routes moved to `/people/accounts/…`.
- Maintenance mode and cached settings leaked between tests: the test base now clears the cache after each test.
- The seed duplicated rows on a re-run (shared random stream): each order now has its own stream.

**Known limits (not hidden in the UI)**
- The language setting sets `<html lang>` only (the UI is English).
- Subscription promotions are redeemed through Stripe coupons, so their per-person limit is not counted.
- `SchemaTransactionTestCase` does not restore the seeded `revenue_shares` rows; tests that change them reset them.

**Staff bell:** applications, course and template submissions, tickets and replies, reported content, learner
refunds, payout requests and due payouts, FX failures and red health tiles (once an hour per service).

**E2E:** `tools/harness/e2e_m5.js` (acceptance 1–17) and the fixture `tools/harness/e2e_staff.py` are written,
**not run**. Their labels come from the builders' reports; reconcile on the first red run. 2-step sign-in with a
real TOTP code is a manual step in that pass.

### Verification pass M4 + M5 (deferred by the user, run later)
Full backend suite, `e2e_m4.js`, `e2e_m5.js` (acceptance 1–17), M1–M3 E2E reruns, phone check on every console
route, light/dark screenshots vs mockups, reviewer agent.

## Migrations the user must run on Neon
- `python manage.py migrate --database owner`: engagement **0005** (M2): inserts the "work_marked" notification wording. Adds only.
- Same command, **on dev and on e2e**, for two new columns (2026-11-07). Both add a nullable column only; no existing data changes. The app's table grants already cover new columns:
  - catalog **0005** `lectures.prerequisite_key` (prerequisite lessons);
  - identity **0002** `instructor_profiles.platform_fee_bps` (each instructor's platform fee).
  Until they run, the studio, player and console pages that read these columns fail on Neon.
- **Done 2026-11-08 by Claude Code (user's answer): all of the above and the M5 set below ran on dev and e2e,
  plus identity 0003_instructor_invites (new table, staff-only RLS).** Nothing is pending.
- **M5 (dev and e2e, same command; adds tables, columns and rows only, checked with `sqlmigrate`):** catalog **0006_console**, learning **0004_console** and **0005_console_a_verify** (a new certificate-check function; the old one stays), commerce **0004_console**, payouts **0003_console**, engagement **0006_console** and **0007_console_templates** (inserts notification wording), payouts **0004_console_c_request_failed** (choices only, no SQL), platform **0003_console_settings** (inserts settings). The console fails on Neon until these run.

## Settings still needed
- **Production web server (LiteSpeed): app links opened directly return 404** (`/login`, email links such as
  `/account/password/reset/key/…`, any refresh). The site's `.htaccess` needs the single-page-app fallback below,
  added **after** any existing rules that send `/api` and `/_allauth` to Django (not shipped in the build, so it
  can't overwrite those rules):
  ```
  RewriteEngine On
  RewriteCond %{REQUEST_URI} !^/(api|_allauth|admin|static|media)(/|$)
  RewriteCond %{REQUEST_FILENAME} !-f
  RewriteCond %{REQUEST_FILENAME} !-d
  RewriteRule ^ /index.html [L]
  ```
- **Production: `FRONTEND_URL`** = the site's public https address (e.g. `https://learn.example.com`). Every link in emails (sign-up confirmation, notifications, reminders) and Stripe's return pages use it. Unset, it was `http://localhost:5173`; production now refuses to start without a public https value.
- Azure storage account → Resource sharing (CORS) → Blob service: allow the frontend origin, methods PUT/GET/HEAD, headers `*`. Without it, browser file uploads fail (assignment hand-ins, and later studio files).
- Google/Microsoft sign-in: app registrations (`MICROSOFT_LOGIN_*`, `GOOGLE_*`); the buttons appear automatically.

## Live service checks (all PASS; they never print secrets)
| Service | Check |
|---|---|
| Azure Blob (learnhubfilesdemo / lmsdemo-resources) | `python manage.py check_storage` |
| Stripe test sandbox "KBC sandbox" | `python manage.py stripe_setup` |
| Microsoft Graph email (MAIL_MODE console for now) | `python manage.py check_mail <address>` |
| Bunny Stream library 798627 | `python manage.py check_bunny` |

Local Stripe webhooks: `stripe listen --forward-to localhost:8000/api/v1/commerce/webhooks/stripe --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.expired,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,invoice.paid`

---

## Basic payouts with an admin-set fee (2026-11-07, user decision; closes NEEDS-USER 2)
The user asked for something simple and flexible for the demo:
- **Default fee for new instructors.** Staff set the platform's cut of a marketplace sale (for example 20%). `GET/PUT /console/platform-fee` stores it as the marketplace row of `payouts.revenue_shares` (`instructor_bps = 10000 - fee`), so there is one source of truth.
- **Kept on approval.** Approving an instructor (`POST /console/instructors/{id}/decision`) copies the default at that moment into `instructor_profiles.platform_fee_bps`. Changing the default later only affects instructors approved after the change (and anyone with no fee of their own).
- **Per-instructor fee.** `PUT /console/instructors/{id}/fee` with `{"fee_pct": 12.5}` sets a custom fee; `{"fee_pct": null}` returns them to the default. `GET /console/instructors` shows `platform_fee_pct` and `fee_is_custom`. Every change is audited.
- **Where it applies.** `payouts.services.record_sale` uses the instructor's own fee for marketplace sales. Sales through the instructor's own coupon (97%) and the subscription pool (25%) keep their channel rates. Each earning line stores the rate it was made at (`share_bps`), so changing a fee never rewrites past earnings.
- **Instructor view.** `GET /studio/revenue` returns `platform_fee_pct` and `fee_is_custom`. The Sales & earnings page says "You keep X% of each marketplace sale".
- The console screens for these settings are built in M5 (P4 Instructors, money settings). The API is ready and tested.
- Not built (out of scope by the user's choice): a payout request button, payout schedule settings, more than one payout method, and Stripe Connect onboarding. The monthly bundle, £25 minimum and 30-day hold stay as they are (client question 2).
- Tests: `apps/payouts/tests/test_payouts.py::test_instructor_fee_replaces_default_on_marketplace_only`, and the fee steps in `core/tests/test_api_console.py`.

## Prerequisite lessons (2026-11-07, user request; closes NEEDS-USER 3)
**What it does.** An instructor can make a lesson require another lesson first ("Require students to complete another lesson first" in mockup 12). The learner can't open the locked lesson until the earlier one is complete.

**Rules**
- Data: `catalog.lectures.prerequisite_key` (nullable UUID). It points to the other lesson's `lecture_key`, not its id, because keys stay the same across course versions (new drafts copy the field).
- When the instructor sets it (`PATCH /studio/lectures/{id}` with `prerequisite_key`, or `null` to remove it), `services._check_prerequisite` rejects:
  - the lesson itself;
  - a lesson from another course or version;
  - a lesson that comes later in the course order (module position, then lesson position).
  The error code is `bad_prerequisite`.
- Lessons can be moved or deleted after the prerequisite is set. If the prerequisite is then missing or comes after the lesson, the **publish checklist** shows "Lesson 'X' needs a prerequisite that comes before it." and blocks submitting.
- Learner side (`apps/learning/api.py::_check_unlocked`, run inside `_lecture`): the lesson content, heartbeat, mark complete, quiz start, assignment hand-in and upload, file downloads and new notes all answer **403 `locked`, "Finish “X” first."** until the prerequisite has a completed progress row. If the prerequisite is missing from the live version, nothing is locked (fail-open, so learners are never stuck).
- The player outline (`GET /learning/enrollments/{id}`) gives each lesson `locked`, `prerequisite_key` and `prerequisite_title`, using the same rule with no extra queries.

**UI**
- Studio, Lesson settings card: a "Prerequisite lesson" switch. When it's on, a list of the lessons before this one (numbered `1.2 Title`), with the previous lesson chosen by default. A broken prerequisite is shown as "Missing lesson" with an error.
- Player: a lock icon and "Finish “X” first" in the course outline. Opening a locked lesson shows a locked screen with a button to go to the prerequisite. The page never asks the server for a locked lesson. "Resume" skips locked lessons.

**Tests:** `core/tests/test_api_studio.py::PrerequisiteTest`, covering the studio rules, the checklist after a reorder, the 403 lock, unlocking after completion, and the outline flags.

## M4 change log (everything changed since M3, for the planner's review)
Checkpoint commit `bff6820`, then the payouts and prerequisite work above.
- **Studio screens:** teach/apply; dashboard; my courses; the course builder:
  - Details: outcomes, requirements, rich-text description;
  - Curriculum: the mockup-12 inline editor;
  - Pricing, Coupons and Publish (checklist, submit, versions).
  Also: students, marking (files, rubric scores, essay prompts), Q&A, reviews and announcements, revenue, payouts. New artwork: `storyboard` and `coins`.
- **Studio API (all typed, in `studio_schemas.py`):**
  - dashboard;
  - instructor status on `/identity/me`;
  - submission file download;
  - draft status on course rows;
  - video details, parts, key moments, thumbnail, subtitles and fetch-by-link;
  - the editor tree carries the video's file name and size, and `prerequisite_key`.
- **Bunny:**
  - connect timeout and one retry; network errors return 503 (they used to be 500s);
  - status poll fallback when webhooks can't reach a laptop;
  - the publish checklist refreshes unfinished videos;
  - reapplying after rejection resets the application to pending.
- **Stripe:** the thank-you page asks Stripe for the Checkout Session when the webhook hasn't arrived (rate-limited, same checks as the webhook). The page no longer waits for ever: it shows a slow state and a retry button.
- **Learner:**
  - video parts and key moments listed under the video, and clicking one seeks the player;
  - notes capture the current second, which can be edited (`PATCH /learning/notes/{id}`), and clicking the time seeks the video;
  - prerequisite locks.
- **Fixes:**
  - feedback showed `<p>` tags: the learner views now render rich text safely (`RichOrText`);
  - `core.html.plain` stored `&amp;`: it now unescapes. Old dev rows are left as they are;
  - learner answers were rendered as HTML on the marking screen (XSS risk): now plain text;
  - the Swagger docs page lacked CSRF;
  - sign-up with an existing email now shows a safe hint (no account probing);
  - the contract test reads files as UTF-8.
- **Payouts:** basic fee settings (see above).
- **Migrations to apply:** catalog 0005, identity 0002 (see the top of this file).

## Extra (agreed with the user, 2026-11-07): video parts, notes moments, thumbnails (built)
Built 2026-11-07, waiting for the user's manual test.
- API: `GET studio/media/{id}/details`, `PUT studio/media/{id}/parts`, `PUT studio/media/{id}/thumbnail`; learner lecture content has `parts` and `moments` (from Bunny, cached 10 min, refreshed on save); `PATCH learning/notes/{id}` (time, clear time, text). Tests in test_api_studio / test_api_learner.
- Bunny thumbnails: the API can't pick a frame by second, so the picker offers Bunny's 5 frames or an https image link (file upload would stream through Django). The pull zone blocks requests without a referrer: `<img>` tags send one; **the production domain must be in Bunny's allowed referrers**.
- Webhook fallbacks for laptops: the order poll asks Stripe for the Checkout Session, the video status poll asks Bunny (both rate-limited, same checks as the webhooks).
1. **Instructor, in the builder's video sheet (both saved to Bunny through its API, so they show in Bunny's own player):**
   - **Parts = Bunny chapters:** name + start time (pick from the preview or type `mm:ss`); each part runs to the next one's start.
   - **Key moments = Bunny moments:** a label at a single second (e.g. "Key formula", "Common mistake").
2. **Learner: the video's parts and key moments** in Bunny's player, and also listed under the video in our style (parts as a list, moments as chips); clicking one seeks the player there (player.js `setCurrentTime`, no reload).
3. **Learner notes moments** (our style, nothing drawn in the iframe): a new note gets the current second automatically; the time can be edited by hand (`mm:ss`) before or after saving; notes are listed under the video and clicking the time seeks the video instantly. Private to the learner (notes are already private rows; needs a note-update endpoint for the time).
4. **Thumbnail picker** in the video sheet: the frame at a given second, or an uploaded image, saved to Bunny.
Keep Bunny's player (no custom player, no hls.js).

## Curriculum redesign to mockup 12 (2026-11-07, user request)
- The drawer is replaced by an inline editor: course content tree on the right (modules, drag + menu reorder, Add module, Bulk upload, tips), lesson editor in the centre (type list, video source upload / external link, file row, processed versions, subtitles, parts/moments/thumbnail), Lesson settings card (free preview, duration hh:mm:ss, completion %, required, Cancel / Save lesson). `?lesson=<id>` in the URL; phones show the list first.
- API (typed, tested): `POST studio/media/videos/fetch` (Bunny fetches a direct file link; found again by a marker title, since Bunny's fetch returns no id), `POST/DELETE studio/media/{id}/captions` (.srt/.vtt up to 1 MB: **the one upload that passes through Django, approved by the user**, forwarded to Bunny, never stored), details add `resolutions` and `captions`, the editor tree's video adds `filename` and `size_bytes`.
- Prerequisite lesson: built later the same day (section above). No autosave claim.
- Also fixed today: learner feedback showed `<p>` tags; `core.html.plain` stored `&amp;` (now stores the text); learner answers were rendered as HTML on the marking screen (stored-XSS risk, now plain text); course description uses the rich-text editor.

## M3 business (done)
- **Screens (all `/business/*` placeholders replaced):**
  - training matrix: KPI strip, URL filters (`unit`, `role`, `status`, `req`, `q`), sticky header/column, keyset "Load more", legend; cell → side sheet with the person's requirement: Extend, Exempt / Revoke, Record completion, Void, Send reminder, history timeline; phone = list of people by worst status;
  - requirements: compliance ring, targets as chips, sheet form (Course, Schedule, Reminders, Who it applies to), archive with confirmation; read-only for managers;
  - reports: by requirement, by location, audit trail (admins), CSV export with unit filter;
  - people (KPIs, filters, keyset) and person page (Profile / Training tabs, role and unit edits, remove with confirmation);
  - locations & teams: tree with per-node actions, managers picker, job roles;
  - invitations (single or bulk) and the public `/invite/:token` page (expired/used, wrong account, sign up → confirm email → back to the invite → accept → company workspace);
  - course library (assigned/completed, progress sheet) and 3-step assign with an exact count;
  - billing (plan, seats, portal, buy seats via the M1 team-plan flow) and company settings with live branding preview.
- **Runtime branding:** company colours tint the sidebar's active item and the header (CSS variables on the layout root and the phone drawer only; tokens untouched; text colour picked for contrast). Logo shown when it is an https link.
- **Layout:** `lib/page-art.ts` lets any workspace route pick its artwork (`handle: { art }`); the header search is real (business → `/business/people?q=`) and hidden where an area has none. New artwork: `chartgrid` (reports), `orgchart` (people, invites), `floorplan` (units).
- **API (all additive, typed, tested; no migrations):**
  - every `/api/v1/org/` and `/api/v1/compliance/` endpoint is typed (both in `TYPED_PREFIXES`; `export.csv` in `NOT_JSON`);
  - person view: `units`, `job_roles`, `requirement_id` on records/exemptions, `void_reason`, revoked exemptions kept as history (`revoked_at`);
  - `org/invitations/{token}` returns `role`; units return `manager_ids`; dashboard returns `people_overdue`; `org/assign` accepts `dry_run`.
- **Bugs found and fixed:**
  - managers received the whole company's unit tree (now only their own units);
  - archived requirements' cells leaked into the matrix (status filter, phone worst status);
  - people and matrix lists were in UUID order (now alphabetical: keyset on name + id);
  - the header search box did nothing;
  - unit detail claimed "no training" for sites/teams (now per-unit summary);
  - removing a person flashed an error page; admins were offered "remove yourself";
  - role badges stayed stale after assigning managers; invite redirect used the invited role instead of the real one; a dead pending invite could be offered after email confirmation;
  - CSV download could be cancelled in Firefox/Safari; compliance actions waited for every list to refetch;
  - unit pickers indented by company depth for managers; custom radio groups had no arrow-key support;
  - `/business/units` overflowed on phones (implicit grid column);
  - `serve.py` never started the Celery worker when `REDIS_URL` lives in `backend/.env` (requirement statuses never computed in E2E);
  - a killed test run left rows in the reused test database (the test base now truncates once at the start of each run).
- **Verified:**
  - backend: full suite 103 tests OK (32 min on Neon), ruff clean, `makemigrations --check` clean, query budgets now cover the person view and assignments;
  - `tsc -b` and `vite build` pass; main chunk 384 KB (115 KB gzip), unchanged;
  - `tools/harness/e2e_m3.js`: 21 steps covering acceptance 1–10 (admin, manager and learner, invite sign-up with real email confirmation, CSV header, audit, billing, branding, phone); `e2e_m1.js` and `e2e_m2.js` re-run green;
  - phone overflow + light/dark screenshots on every business route and the invite page: `node tools/harness/phone_business.js shots/phone` (builds its own company, so no demo password is needed); screenshots checked against the specs and mockups 26/05/33.
- **Reviewer:** run on the whole M3 change; all 16 findings fixed (listed above).
- **Harness additions:** `e2e_org.py` (fresh company), `e2e_wsgi.py` records `email<TAB>token` in `invite.log` when the API enqueues an invite (the app never stores or logs the token), `e2e_verify_key.py` (allauth's HMAC confirmation key), `stop.py` (stops the harness processes), `phone_business.js`; `phone_check.js` can switch company (`E2E_DEMO_ORG`).
- **Type generation without a running server:** `tools/dump_openapi.py` writes `logs/openapi.json`; then `npx openapi-typescript ../logs/openapi.json -o src/api/schema.d.ts` in `frontend/`.
- **Lessons:** never run two Django test processes at once against Neon (shared `test_*` database: deadlocks, duplicate keys); Django 5.2 calls `_fixture_setup` at class level, so hook `setUpClass`.

## M2 learning (done)
- **Player** `/learn/:slug/lecture/:key`; `/learn/:slug` resumes; `/learn/:slug/qa/:id` and `/announcements/:id` are notification links.
  - Curriculum sidebar on desktop, drawer on phones; progress ring; prev/next.
  - Finishing the course shows a celebration dialog with the certificate.
- **Lecture kinds:**
  - video: Bunny iframe + player.js; resume, real watch time every 30 s and on leave; placeholder with manual complete when not uploaded;
  - reading, external link, download;
  - live session (countdown; join link from 15 min before);
  - quiz: 7 answer types, timer with auto-submit, drafts survive a reload, review after submitting;
  - assignment: text, https link, up to 5 files sent directly to Azure; rubric; feedback.
- **Tabs:** overview + files, notes (pinned to video time), Q&A, announcements, review.
- **Pages:**
  - certificates (PDF, verify link) and public `/verify/:code`;
  - achievements;
  - required training (per company);
  - notifications page and bell;
  - settings (profile, time zone, currency, password, notification preferences, companies);
  - support tickets.
- **Backend additions:**
  - typed responses for learning/engagement/identity;
  - reloadable quiz review;
  - `my/courses?slug=`;
  - `my-review`, `my/badges`;
  - assignment file uploads (`apps/learning/uploads.py` + purge job);
  - notifications for certificate issued and work marked;
  - badges for personal completions;
  - name sanitising;
  - free enrolment goes straight to the player;
  - order items carry the course slug.
- **Bugs fixed:**
  - the workspace bell was a fake dot;
  - the review-reply link 404'd;
  - badges could get the wrong name;
  - the file purge would have crashed on hand-ins;
  - the quiz result was lost after submit;
  - a stale-cache redirect after enrolling;
  - a self-vote error;
  - an 800 KB icon bundle.
- **Verified:** `tools/harness/e2e_m2.js` (18 steps, every lecture kind, desktop + phone), M1 E2E re-run, phone overflow check, light/dark screenshots.

## M1 marketplace (done)
- **Built:**
  - catalogue filters (sidebar + phone drawer), chips, sort, grid/list, infinite load;
  - course page buy modes;
  - cart with coupon + currency;
  - Stripe checkout + thank-you polling;
  - plans (personal trial, team seats, billing portal);
  - wishlist;
  - purchase history with refunds.
- **Verified:** `tools/harness/e2e_m1.js`.

## STANDING RULES (from the user; apply to every milestone)
1. **Artwork on every page** (no flat backgrounds): see `frontend/README.md` for the variant per area.
2. **Motion**:
   - View Transitions;
   - skeleton cross-fade;
   - stagger;
   - living numbers;
   - micro-interactions;
   - subtle (150-300 ms), reduced motion respected.
3. **Design**: the approved mockups, refined; light and dark mode.
4. **Security and data**:
   - secrets only in `.env`;
   - the app never uses `lms_owner`;
   - no `--fake`;
   - Neon only gains tables, columns and rows; anything touching existing data → ask the user.

## Working rules learned (bugs these prevent)
- Duplicate Ninja schema class names silently corrupt the OpenAPI types → the contract test.
- React Query mutation callbacks don't fire if the component unmounts → derive views from server state, not local flags set in `onSuccess`.
- Never decide a redirect from cached data while it's refetching.
- Grid children need `min-w-0`; tables with `sr-only` need a `relative` wrapper (phone overflow).
- Celery must run (with Redis) for badges and emails; tests run tasks eagerly.
- Import icons one by one (the whole lucide set is ~800 KB).

## Next
1. M5 console, starting fresh. It includes the console screens for the platform fee (default and per instructor).
2. M6 polish (check the main bundle size: ~520 KB minified / 160 KB gzipped).
3. **Final test round after M6** (user decision):
   - the full backend suite. The stopped run on 2026-11-07 had two unidentified errors, around tests #30 and #97: find them;
   - the E2E scripts for M4, M5, M6 and the demo, plus every earlier one;
   - the phone check on every route, in light and dark;
   - the reviewer over the whole branch;
   - a click-through of the whole demo.
4. Deployment.
5. **M17 HR system (Breathe HR)**, after the final test round (user decision, 2026-11-14).
   Brief: `docs/milestones/M17-hr-system.md`. Needs `CREDENTIAL_ENCRYPTION_KEY`, the
   `cryptography` pin and four additive migrations first (see `NEEDS-USER.md`).

## B2C-03 — PR 2 done (2026-11-11)

Admin monetization console endpoints + token-pricing contract wired in (PR 2 of 3).
Django-Ninja routes under `/api/v1/console/pricing/token/*`, mounted alongside the
existing cash pricing console via `apps/platform/console/__init__.py`. All endpoints
require `StaffSessionAuth` + `staff(request)`; mutations forward `actor`, `reason`,
and `request` to `apps.commerce.pricing_service`, which continues to own all state.

New files:
- `backend/apps/platform/console/token_pricing.py` — the whole token-pricing surface
  plus `Console…`-prefixed request/response schemas.
- `backend/apps/platform/tests/test_console_token_pricing.py` — 14 endpoint tests.

Modified:
- `backend/apps/platform/console/__init__.py` — registers the new module.
- `backend/apps/catalog/services.py` — `create_draft` now runs
  `pricing_service.migrate_token_pricing_on_republish` after `_copy_content`,
  wrapped in try/except so republish semantics never change on failure.

Endpoints: course list/detail/PATCH, `distribute-tokens` (server-authoritative,
Hamilton allocation; client-side amounts are ignored), per-lecture/per-material
PATCH, bulk course PATCH, token pack CRUD + soft delete, token rate list + create
(past `effective_from` → 400 `RATE_EFFECTIVE_FROM_PAST`), per-currency top-up policy
upsert, bonus campaign list/create/update (activation stays blocked → 409
`F02_BLOCKED`), audit page scoped to token-pricing targets.

UNSET vs null: PATCH bodies default each optional field to the string sentinel
`"__UNSET__"`. The endpoint reads `payload.dict(exclude_unset=True)`; missing →
UNSET (service leaves the column alone), explicit `null` → clears the column,
value → sets the column. `price_tier_id` is resolved to a `PriceTier` row (404 on
unknown id) before forwarding.

Contract test (`core/tests/test_api_contract.py`) still passes — the `Console`
schema-name prefix was already enforced for the console surface; every new schema
starts with `Console…` and every typed response declares its shape.

No new models or migrations. All BLOCKED items from PR 1 (C05, F02, T03, default
top-up bounds) remain BLOCKED.

## B2C-03 — PR 1 done (2026-11-10)

Admin monetization & token pricing — foundation layer (PR 1 of 3). Models, migrations,
service, and tests only. No API routes or UI yet (PR 2 / PR 3).

New tables (all additive):
- `commerce.token_packs`, `commerce.token_rates`, `commerce.topup_policies`,
  `commerce.bonus_campaigns`, `commerce.price_snapshots`.
- Partial unique index `uq_trate_one_open` — at most one open-ended `TokenRate` at a time.
- Partial unique index `uq_topup_active_cur` — at most one active `TopUpPolicy` per currency.

New columns (nullable / defaulted — existing rows unaffected):
- `catalog.courses`: `cash_price_tier_id`, `full_course_token_price`, `token_pricing_mode`.
- `catalog.lectures`: `token_price`, `is_free_preview`.
- `catalog.lecture_resources`: `token_price`, `is_free_preview`.

Service: `apps.commerce.pricing_service` (see M13 brief for signatures).
Audit reuses the existing `platform.audit_logs` partitioned table via
`apps.platform.services.audit()`.

Migrations the user must run (owner connection, Neon):
- `commerce.0005_tokenrate_pricesnapshot_topuppolicy_bonuscampaign_and_more`
- `commerce.0006_token_pricing_constraints`
- `catalog.0007_course_cash_price_tier_and_more`

BLOCKED items (still open — PR 2 cannot close):
- **C05** default auto-weights for token distribution.
- **T03** default grant expiry duration.
- **F02** bonus-campaign activation funding model.
- Default TopUp bounds per currency.
