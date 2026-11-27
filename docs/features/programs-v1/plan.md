# Programs v1: plan

Status: **draft for user approval** (2026-11-16). Nothing built yet.
Idea source: `E:\Kent\LMS_v2` (the old apprenticeship LMS). It inspires us but we don't copy it,
because much of its logic is broken (see "What we avoid" below).

LearnHub is a **product sold to training providers** (one install per provider). Wherever
the old LMS says "KBC", read **"the provider"**. Business rules are provider or program
**settings**, not constants. Staff roles are **permission-based**.

---

## 1. Decision register (user answers, 2026-11-16)

| # | Topic | Decision |
|---|---|---|
| D1 | Program vs course | `Course` gets `kind = short \| program`. Short courses are unchanged. |
| D2 | Hierarchy | Program → Cohort → Group (learners) · Program → Module → Week (= `Section`) → Component (= `Lecture`) |
| D3 | Groups | **Learner groups** inside a cohort. Each group has its own tutor and its own Teams timetable, and all groups study the same modules. |
| D4 | Content ownership | The **program owns content**. A cohort only schedules it (dates, sessions, tutors). There are no per-group copies. |
| D5 | B2C access | Both modes: **live cohort seat** (cash) or **self-paced recorded** (cheaper). |
| D6 | B2C tokens | Tokens unlock a **recorded module** only. Live seats are paid in cash through Stripe. |
| D7 | B2C instalments | Live programs can be paid in full or in **N monthly Stripe payments** (N is set per program). If a payment fails, access pauses after a grace period. |
| D8 | B2B signup | A company signs up, then **must build and pay** an order before its workspace opens. The order holds whole programs or chosen modules, with seats per line (minimum seats per module is a program setting, default 2). |
| D9 | B2B payment | **Card only (Stripe)**. The workspace unlocks on a paid webhook. |
| D10 | Module mode | The buyer chooses per line: **live in a cohort** or **recorded**. |
| D11 | Seat swaps | A swap is a **request**: company owner or line manager approves, then the provider approves. Swaps are free until a **cut-off** (a program setting: % progress or week N). After it, a reason is required. The old learner's progress stays on record. |
| D12 | KSB source | **Imported apprenticeship standards** (Skills England) plus custom KSBs for non-apprenticeship programs. |
| D13 | KSB achievement | **Automatic from completion**: a KSB is met when its mapped components are completed or passed. |
| D14 | OTJ | **One ledger**. Entries come automatically from components and live/workshop attendance (real minutes), and from learner logs, which a tutor approves. A program target (% or hours/week) gives on-track / behind / at-risk. |
| D15 | CPD | **Per component, rolled up** to week, module and program. Short courses keep course-level CPD. |
| D16 | Week dates | Weeks are **dated from the cohort start** by default, with an **optional per-module start date** override. UK bank holidays, weekends and closures marked by the provider are skipped. The holiday country is a provider setting. |
| D17 | Live tool | **Teams everywhere**, with meetings created by the app through Microsoft Graph. **Zoom is retired** for new sessions. |
| D18 | Recordings | A background job pulls the Teams recording and transcript to **Bunny** and attaches them to that group's session. Recorded-mode learners get the program's master recording. |
| D19 | Teams tenant | The user will create a new Azure app registration. We ship a setup guide, and each provider plugs in its own tenant. |
| D20 | Staff roles | **Permission-based roles**. Defaults: Admin, Curriculum designer, Tutor, Coach, IQA. The provider can reshape them. |
| D21 | Authoring | **Provider staff only** build programs. Marketplace instructors keep building short courses. |
| D22 | Line manager | **View** their team's progress, KSBs, OTJ and attendance, and **approve seat swaps** for their team. They sign nothing else. |
| D23 | Reviews | **No MCMs, progress reviews or EPA reviews.** Workshops are in scope. |
| D24 | Workshops | **Optional live Teams events** outside the timetable. They can be booked, have a capacity, and count towards OTJ and CPD when attended. They are recorded to Bunny. |
| D25 | Certificates | One **per module**, plus a **program** certificate (total CPD, KSBs met), using the existing templates. |
| D26 | Old B2B cohorts | **Merge** `corporate.LiveCohort/Session` into the new cohort model. The new tables are filled by insert-only data migrations. The old tables become read-only, and nothing is deleted. |
| D27 | Seed data | The **real structure** of PCP, MBA, MM and ME is read from LMS_v2 and seeded with 2 cohorts each, plus groups, learners, sessions and hours. |
| D28 | Phasing | Six phased milestones (M18–M23). Each one ends working and demoable. |

---

- **D29 (2026-11-16):** until M21/M22, published programs are not listed, sold or assigned; learners join only by staff placement. Programs need no price to publish.

## 2. What we avoid (lessons from LMS_v2)

1. **Per-group module copies.** Content lives once, on the program (D4). A cohort or group holds only schedule data.
2. **Joins by text name.** Every link is a real foreign key. No IDs are stored inside JSON.
3. **Learner duplicated across tables.** One `Enrollment` per learner and program, with status as a field. Rows are never moved.
4. **Hard-coded rules** (150 minutes per live session, 180 seconds counts as present, gateway = end − 90 days, 8 hours per day, working hours). Each one becomes a program or provider setting with a sensible default.
5. **KSB stored twice** (JSON on the component and a table). We keep one mapping table and never rewrite learner history.
6. **Seven OTJ sources.** We keep one ledger, and every row has a source and a reference (unique on both, so nothing is double-counted).
7. **Undated weeks.** Every scheduled week has a start and end date (D16).
8. **In-process background threads.** Jobs run on Celery, with idempotent tasks and an audit trail.

---

## 3. Data model (all additive)

Neon may only gain tables and columns. Final app placement will be checked against `docs/STRUCTURE.md` in M18. The proposal:

### catalog (content, owned by the program)
- `Course` + `kind` (`short`/`program`, default `short`) and program settings:
  - `otj_target_mode` (`percent`/`hours_per_week`/`total_hours`) and `otj_target_value`;
  - `min_module_seats` (default 2);
  - `swap_cutoff_mode` (`progress_pct`/`week`) and `swap_cutoff_value`;
  - `instalments_max`;
  - `attendance_min_minutes` (minimum minutes to count as present);
  - `ksb_standard` (FK, nullable).
- **`Module`** (new): `version` FK, `module_key` (stable across versions, like `lecture_key`), `title`, `description`, `position`, `is_sellable`, `recorded_token_price`.
- `Section` + `module` FK (nullable; required when `kind=program`). In program UI it is labelled **"Week"**.
- `Lecture` + `expected_otj_min` and `cpd_min`. In program UI it is labelled **"Component"**. Live components point at a **session slot**; their dates come from the group timetable.
- **KSB**:
  - `KsbStandard` (code e.g. ST0272, title, version, source);
  - `KsbItem` (standard, `K1`/`S3`/`B2`, kind, text);
  - `ProgramKsb` (custom KSBs for a program);
  - `ComponentKsb` (lecture_key ↔ KSB item; the only mapping store).

### delivery (new app: schedule, owned by the provider)
- `Cohort`: program, name or intake, `start_date`, `end_date`, `calendar_country`, `status`, `capacity`. It replaces `LiveCohort` (D26).
- `CohortModule`: cohort, module_key, optional `start_date` override (D16). Week dates are calculated from it and cached in `CohortWeek` (cohort, section, starts_on, ends_on).
- `Group`: cohort, name, weekday, start and end time, capacity, tutor (staff user with the *teach group* permission).
- `Holiday` (country, date, name; GOV.UK feed) and `Closure` (provider-wide or per cohort; date range, reason).
- `LiveSession`: group, component (lecture_key), `starts_at`, `duration_min`, Teams meeting id and join URL (the organiser or host URL is never sent to learners), status.
- `SessionAttendance`: session, user, minutes, first join and last leave, source (`graph`/`manual`).
- `SessionRecording`: session → `MediaAsset` (Bunny) + transcript.
- `Workshop`: program and optional cohort, title, `starts_at`, capacity, Teams fields, `expected_otj_min`, `cpd_min`. Also `WorkshopBooking`.
- `MeetingProvider` connection: one row per install. It holds the Graph tenant, client id and organiser. **Secrets stay in `.env`.**

### learning (learner)
- `Enrollment` + `cohort`, `group`, `mode` (`live`/`recorded`), `scope` (`program`/`modules`), and `seat_allocation` FK (B2B). Also `EnrollmentModule` (which modules the scope covers).
- **`OtjEntry`** (the ledger):
  - user, enrollment, `source` (`component`/`live_session`/`workshop`/`manual`), `source_ref`, `minutes`, `occurred_on`;
  - `status` (`auto_approved`/`pending`/`approved`/`rejected`), `approved_by`, `note`;
  - unique on (`source`, `source_ref`, user).
- KSB status is **computed** in a selector from completion (D13). A cache table is added only if query budgets need it.
- `Certificate` + `module_key` (nullable) for module certificates.

### commerce / corporate (selling)
- `ProgramOffer`: program, optional module, `mode` (live/recorded), cash price tier, `token_price` (recorded module only, D6), `instalments_max`.
- B2C instalments: a Stripe subscription with a fixed number of cycles, linked to the order. The payment-failed webhook pauses access after the grace period.
- B2B:
  - `SeatPurchase` gains `SeatLine` (program, optional module, cohort, mode, seats ≥ minimum);
  - `SeatAllocation` points at a line;
  - **`SeatSwapRequest`** (line, from member, to member, reason, status `pending_company` → `pending_provider` → `approved`/`rejected`). Every step goes into `AllocationEvent`.
- `Organization` + `onboarding_state` (`ordering`/`awaiting_payment`/`active`). Workspace routes stay gated until it is `active`.

### identity / platform (roles)
- `StaffRole` (name, permissions[]), plus `StaffRoleAssignment`. The default roles are seeded by an insert-only data migration.
- Permission codes: `programs.build`, `cohorts.manage`, `groups.teach`, `otj.approve`, `seats.approve_swap`, `reports.view`, …
- The existing console guards are mapped onto them.

---

## 4. Milestones

Each milestone follows the CLAUDE.md definition of done: tests, ruff, migrations listed, types synced, build, E2E, phone check and mockup comparison.

### M18: Program structure, cohorts and groups
- Backend:
  - `Course.kind`, `Module`, `Section.module`;
  - the delivery app (Cohort, CohortModule, CohortWeek, Group, Holiday, Closure);
  - the week-date calculator (UK holidays, weekends and closures; per-module override);
  - permission-based staff roles.
- Studio: a program builder (Modules → Weeks → Components), with drag to reorder and labels switched for programs.
- Console: cohorts and groups (create, schedule preview with dated weeks, assign tutor).
- Learner: program page (modules, weeks, components, dates) and player navigation by module and week.
- Done when: a staff user builds a 2-module program, creates a cohort with 2 groups, and a learner sees dated weeks that skip a bank holiday.

### M19: KSBs, OTJ ledger and CPD
- Import a standard: Skills England API, with a JSON-file fallback.
- Map KSBs to components (a matrix view in the studio).
- `OtjEntry` ledger:
  - automatic entries on component completion;
  - learner "log hours" form, approved by a tutor in an approval queue;
  - target and RAG from the program setting.
- CPD roll-up. Module and program certificates.
- Learner: "My hours", "My KSBs" (a matrix showing met / in progress) and a CPD record.
- Tutor and company: per-learner KSB, OTJ and CPD views.

### M20: Teams live sessions, recordings and workshops
- Graph client (app-only):
  - create and update meetings for each group's sessions;
  - attendance reports become `SessionAttendance`, which feeds OTJ entries (real minutes);
  - recordings and transcripts are copied to Bunny as `SessionRecording` (a Celery task, idempotent, with retries).
- Manual fallback when no tenant is connected: paste a link, mark attendance, upload a recording.
- Workshops with booking, capacity, attendance, OTJ and CPD.
- `NEEDS-USER`: the Azure app registration guide (permissions, application access policy, recording access).

### M21: B2C buying
- `ProgramOffer`: whole program or module, live or recorded.
- Checkout:
  - a live seat goes to a cohort and a group with spare capacity;
  - recorded gets self-paced access;
  - tokens unlock recorded modules;
  - Stripe instalments, with a pause when a payment fails.
- Program landing page with intakes, modes and prices.

### M22: B2B company signup, order, seats and swaps
- Company signup wizard: account, then build the order (programs or modules, mode, intake, seats ≥ minimum), then Stripe card payment, then the workspace unlocks.
- Allocate employees to seats, which creates an enrollment in the group.
- Seat swap requests: owner or line manager, then the provider, with the cut-off rule enforced and an audit trail.
- Line manager view of their team (progress, KSBs, OTJ, attendance).

### M23: Merge old cohorts, seed real data and full E2E
- Insert-only data migration: `LiveCohort/Session` become `Cohort/Group/LiveSession`. The old B2B live flow is moved onto the new model, and the old tables become read-only.
- Seed PCP, MBA, MM and ME from the LMS_v2 structure (modules, weeks, components, KSB standards), with 2 cohorts each, groups, learners, sessions, attendance and hours.
- Full E2E covering B2C live, B2C recorded with tokens, B2B signup to swap, tutor approvals and Teams fallback. Earlier E2E scripts must still pass.

---

## 5. Open items (go to `docs/client-questions.md`, not decided by us)
- Prices for each program, module and mode, and the number of instalments.
- Refund and withdrawal policy for programs (cohort seats, instalments).
- What happens when every group in a cohort is full: a waitlist, or open a new group?
- Swap cut-off defaults (e.g. 20% progress, or week 4).
- Default OTJ target per program (20%? 6h/week?), and whether learner-logged hours are capped per day.
- Which countries a provider may pick for the holiday calendar besides England & Wales.

## 6. User actions needed
- Create the Azure app registration for Teams (the guide arrives with M20) and put the secrets in `backend/.env` yourself.
- Run the new migrations with `migrate --database owner` at each milestone. Every one is additive.
- Confirm that the M23 merge of the old cohort data (insert-only) is fine before it runs on Neon.
