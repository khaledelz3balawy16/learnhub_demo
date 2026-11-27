# M19: KSBs, off-the-job hours and CPD

Plan: `docs/features/programs-v1/plan.md` (D12–D15, D25). Builds on M18 (programs, cohorts, groups, staff roles).
Testing: small targeted tests only (user decision, 2026-11-16). The product is sold to many providers: every
rule below is a program setting with a default, never a constant.

## Backend

### B1 KSB standards (catalog, reference data)
- `KsbStandard`: `code` (e.g. ST0272, unique with `version`), `title`, `version`, `level`, `source`
  (`imported`/`custom`), `imported_at`. Custom standards serve non-apprenticeship programs (D12).
- `KsbItem`: standard, `code` (K1, S3, B2), `kind` (`knowledge`/`skill`/`behaviour`), `text`, `position`;
  unique (standard, code).
- `ComponentKsb`: program (`Course`), `lecture_key`, KSB item; unique on all three. This is the **only**
  mapping store (lesson 5). It survives new program versions because it uses `lecture_key`.
- Import (`catalog/ksb_import.py`): parse the Skills England / IfATE standard JSON (`referenceNumber`, `title`,
  `version`, `level`, `knowledges[].detail`, `skills[].detail`, `behaviours[].detail`) and a plain shape
  (`code`, `title`, `version`, `items[{code, kind, text}]`). Fetch by code from the URL template in the
  setting `learning.ksb_feed_url` (allow-listed hosts only, no redirects, 15 s timeout). Upload of the same
  JSON is the fallback. Re-importing the same code and version adds missing items only (never rewrites).
- RLS: all three tables `rls.reference` (everyone reads, staff writes through the console).

### B2 Program settings (delivery)
- `ProgramSetting` (one per program, created on first save): `ksb_standard` (nullable FK),
  `otj_target_mode` (`none`/`hours_per_week`/`total_hours`, default `none`), `otj_target_value`,
  `otj_amber_pct` (default 80: below it a learner is "at risk"), `otj_daily_cap_min` (default 480, the most
  a learner may log for one day). RLS `reference`.

### B3 Components (catalog)
- `Lecture.expected_otj_min` and `Lecture.cpd_min` (default 0). Edited in the studio lesson editor for
  program components.

### B4 Ledger and certificates (learning)
- `OtjEntry` (MixedTenant, org and user copied from the enrolment by trigger, RLS `mixed`): enrolment,
  `source` (`component`/`live_session`/`workshop`/`manual`), `source_ref`, `minutes`, `occurred_on`,
  `status` (`auto_approved`/`pending`/`approved`/`rejected`), `note`, `decided_by`, `decided_at`,
  `decision_note`. Unique (enrolment, source, source_ref): nothing is double counted (lesson 6).
- Automatic entry when a program component with `expected_otj_min > 0` is completed (idempotent).
- Learner log: date (not in the future, not before enrolment), minutes (1 to the daily cap, counting the
  day's other manual entries), what they did. Status `pending`. Learners may withdraw a pending entry.
- Approval: a group's tutor (`groups.teach`) for learners in groups they tutor, or anyone with
  `cohorts.manage`. Approve or reject with a note; audited; the learner is notified.
- Target and RAG (selector): actual = auto + approved minutes. Expected so far: `hours_per_week` × teaching
  weeks elapsed in the learner's cohort schedule, or `total_hours` × the share of the cohort's teaching weeks
  elapsed. `on_track` when actual ≥ expected, `behind` when ≥ amber %, else `at_risk`. No target or no
  cohort: no RAG.
- KSB status (computed, D13): per item mapped in the program, `met` when every mapped component (in the live
  version) is complete, `in_progress` when some are, else `not_started`. Items with no mapping show as
  `not_mapped`.
- CPD (D15): completed components' `cpd_min`, rolled up by week, module and program.
- `ModuleCertificate` (MixedTenant, RLS `mixed`): enrolment, `module_key`, `module_title`, `cpd_min`,
  `verification_code`, `issued_at`; unique (enrolment, module_key). Issued when every required component of
  a module is complete. The program certificate (existing) carries the program's CPD hours.

### B5 Endpoints (typed, audited writes)
- Learner (`/learning/`): `GET enrollments/{id}/record` (target, RAG, totals, KSB matrix, CPD by module,
  module certificates), `GET enrollments/{id}/otj` (keyset), `POST enrollments/{id}/otj`,
  `DELETE enrollments/{id}/otj/{entry_id}` (own pending only).
- Console:
  - `GET/PUT programs/{id}/settings` (`programs.build` or `cohorts.manage` reads, `programs.build` writes);
  - `GET ksb-standards`, `POST ksb-standards/fetch` (by code), `POST ksb-standards/upload`,
    `POST ksb-standards` (custom), `POST ksb-standards/{id}/items` (custom only), `GET ksb-standards/{id}`;
  - `GET programs/{id}/ksb-map`, `PUT programs/{id}/ksb-map/{lecture_key}` (`programs.build`);
  - `GET otj-pending` (keyset; scoped as in B4), `POST otj/{id}/decide`;
  - `GET program-enrollments/{id}/record` (the learner's tutor or `cohorts.manage`).

## Frontend
- **F1 Console program page:** new tabs **KSBs** (choose, fetch by code, upload or create a standard; the
  mapping matrix: components down, KSBs across, checkboxes; coverage counts) and **Settings** (OTJ target,
  amber %, daily cap).
- **F2 Console "Hours to approve"** (`/console/otj`, Programs nav): pending learner logs, approve/reject with
  a note, empty and error states.
- **F3 Console cohort page:** a learner's record sheet from the group members list (hours with RAG, KSBs, CPD).
- **F4 Studio:** OTJ and CPD minutes on program components.
- **F5 Learner "My record"** (`/learn/:slug/record`): Hours (ring, target, log form, ledger), KSBs (met /
  in progress grid), CPD (by module), module certificates. Linked from the player overview and My learning.
- Company (line manager) views come with M22.

## Done when
A staff user imports or creates a standard, maps KSBs to components and sets an OTJ target; a learner
completes components (auto hours, CPD, KSBs met, a module certificate), logs hours, and their tutor approves
them in the queue. Small tests cover import, ledger idempotency, daily cap, approval scoping, RAG and KSB status.
