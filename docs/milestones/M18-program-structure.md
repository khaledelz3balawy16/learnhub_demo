# M18: Program structure, cohorts and groups

**Plan:** `docs/features/programs-v1/plan.md` (decisions D1–D28; approved 2026-11-16).
**Goal:** a provider staff member builds a program (Module → Week → Component), opens a
cohort with dated weeks (UK bank holidays, weekends and closures skipped) and learner
groups, and places learners. A placed learner sees the program in the player, grouped by
module and week, with real dates.

**Testing (user decision, 2026-11-16):** small, targeted tests only, plus static checks
(ruff, `makemigrations --check`, `tsc -b`, `vite build`). The full suite, E2E scripts and
the phone check are deferred to a later round. Record them as "long tests pending".

**Mockups:** none. Use the closest ones:
- builder: 21 (course builder) and 12 (lesson editor);
- console lists: 45 (course management);
- cohort detail: 05 (table + detail sheet) and 33 (table with side summary);
- roles: 18 (settings sections);
- player: 43.

---

## Rules for this milestone
- **Additive only.** New tables and nullable or defaulted columns. Nothing is renamed or dropped.
- **Content lives once, on the program** (D4). Cohorts and groups hold only schedule data.
  There are no per-group copies.
- **No hard-coded business rules.** Calendar division, minimum working days per week and
  similar values are settings with defaults.
- **Provider, not KBC.** All wording says "provider" or the provider's name from settings.
- **Week order stays global.** `Section.position` stays one ordered list across the whole
  version, so the player, progress and every existing reader keep working unchanged.
  Program weeks are renumbered as (module position, week position) in one SQL statement
  after every module or week change.

## Backend

### B1. Catalog: programs and modules
- `Course.kind`: `short` (default) or `program`. It can only be set at creation.
- New `Module(OwnedContent)`:
  - `version` FK, `module_key` (UUID, stable across versions), `title`, `description`, `position`;
  - unique (version, position) is deferred so reorders are safe;
  - index (version, position).
- `Section.module` FK, nullable. It is required for sections of program courses (enforced in services).
- Services:
  - `add_module`, `update_module`, `delete_module` (only when empty), `reorder_modules`;
  - `add_section(module=…)`, `move_section(to module)`, `reorder_sections` within a module;
  - `_renumber_weeks(version)`.
- `_copy_content` copies modules (same `module_key`) and keeps each week in its module.
- The publish checklist for programs requires every week to be inside a module, and every module to have at least one week.
- Studio: programs can be built by staff holding `programs.build`. Ownership is `platform` (D21).
  - Endpoints: `POST /studio/programs`, `GET/POST /studio/versions/{id}/modules`,
    `PATCH/DELETE /studio/modules/{id}`, `PUT /studio/versions/{id}/modules/order`,
    `PUT /studio/modules/{id}/sections/order`.
  - The editor tree returns modules with their weeks.
- Public course detail and learner curriculum return `kind` and `modules` (id, key, title, week ids).

### B2. Identity: permission-based staff roles (D20)
- `StaffRole` (name, description, `permissions` text[], `is_system`) and
  `StaffRoleAssignment` (user, role, unique).
- The permission registry is in code: `core/staff_perms.py`. It has codes plus labels:
  - `programs.build`
  - `cohorts.manage`
  - `groups.teach`
  - `roles.manage`
  - `reports.view`

  The later codes (`otj.approve`, `seats.approve_swap`) are added by their milestones.
- `require_perm(request, code)`:
  - superusers pass;
  - otherwise the user must be staff, and one of their roles must hold the code.
- An insert-only data migration seeds the default roles Admin (all), Curriculum designer,
  Cohort manager and Tutor, and assigns **Admin to every current staff user**, so nobody
  loses access.
- Console: `GET/POST/PATCH /console/roles`, and `PUT /console/roles/{id}/members`. Each one needs
  `roles.manage` and is written to the audit log. A system role's permissions can be edited,
  but the role cannot be deleted. The last Admin cannot be removed.

### B3. Delivery app (new schema `delivery`)
`delivery` sits between catalog and learning (catalog ← delivery ← learning).
- `Cohort`:
  - program (Course, kind=program), `name`, `start_date`, `end_date` (computed, stored);
  - `calendar` (GOV.UK division: `england-and-wales` / `scotland` / `northern-ireland`; default from the provider setting);
  - `status` (`planned`/`open`/`running`/`finished`/`cancelled`), `capacity` (optional), `created_by`.
- `CohortModule`: cohort, `module_key`, optional `starts_on` override (D16). Unique (cohort, module_key).
- `Group`:
  - cohort, `name`, `tutor` (user, nullable), `weekday` (0–6), `starts_at`/`ends_at` (time);
  - `capacity` (optional), `status` (`active`/`closed`). Unique (cohort, name).
- `Holiday` (division, date, title). Unique (division, date). It is filled by
  `manage.py sync_bank_holidays` (GOV.UK `bank-holidays.json`) and a monthly Celery beat.
  Data is never hard-coded.
- `Closure`: optional cohort (NULL = provider-wide), `starts_on`, `ends_on`, `reason`.
- These are all global tables (`BaseModel`, no `org_id`), like the old `LiveCohort`. The API
  layer controls access: the console needs `cohorts.manage`, and learners only read their own placement.
- **Calendar** (`delivery/calendar.py`) is a pure function:
  `build(program_modules, weeks_by_module, start, overrides, holidays, closures) -> [ModulePlan]`.
  - A teaching week is Monday–Friday. Week 1 starts on the cohort start date.
  - A week with **no working day** (every weekday is a holiday or closure) is skipped and listed as a break.
  - Bank holidays inside a week are shown on that week.
  - A module starts on its override date if one is set, otherwise the next teaching week after the previous module.
  - An override earlier than the previous module's end is allowed, with a warning (overlap).
  - The result is cached in Redis under a stamp of (cohort updated_at, live version id, holiday and closure max updated_at). A `CohortWeek` table is not needed.
- Learner placement: `Enrollment` gains `cohort` and `group` (nullable FKs). The console
  "add learners to group" action creates or updates the enrollment (`admin_grant`).
  - The group must belong to the cohort, and the cohort to the program.
  - Group capacity is enforced.
  - Removing a learner from a group clears the group only. Progress is never deleted.
- Console endpoints (`/console/programs/…`, `cohorts.manage`):
  - programs list, and cohorts CRUD with a schedule preview;
  - module overrides, groups CRUD, closures CRUD;
  - group members: list, add by email, remove.
- Learner: `GET /learning/enrollments/{id}` adds `kind`, `modules[]` (each with its weeks:
  dates, `is_break`, holidays), and `group` (name, weekday, time, tutor name) when placed.

### B4. Tests (small)
- Calendar:
  - plain run;
  - a bank holiday inside a week;
  - a fully closed week skipped;
  - a module override, and an overlap warning.
- Week renumbering after module reorder and week move.
- `require_perm`: superuser passes, staff without the role is refused, the role grants access.
- Group placement: wrong cohort refused, capacity enforced.

## Frontend

### F1. Console > Programs (`/console/programs`)
- A list of programs with module, week and cohort counts. "New program" creates it and
  opens the studio builder.
- Program detail tabs: **Cohorts** (list + "New cohort") and **Structure** (a read-only tree with an "Edit in studio" link).

### F2. Studio program builder (`/studio/courses/:id` when kind=program)
- Modules hold weeks, which hold components. Modules can be added, renamed and reordered.
  Weeks can be added inside a module and moved up or down within it.
  Components reuse today's lecture editor.
- The labels read "Module", "Week" and "Component".

### F3. Console > Cohort detail (`/console/cohorts/:id`)
- Summary: dates, status, number of groups and learners.
- **Schedule** tab: modules with dated weeks, breaks and bank holidays, plus an override date picker per module.
- **Groups** tab: each group with its tutor, timetable, capacity and members (add by email, remove).
- **Closures** tab.

### F4. Console > Roles (`/console/roles`)
- A list of roles, a permission checklist and members. Assign a role by staff email.

### F5. Learner
- The program course page shows the modules and their weeks.
- The player sidebar groups lectures by module, then by week, with week dates and "This week" highlighted.
- My learning shows the group name and the next week's dates.

Every page follows the artwork, motion, dark mode, phone and loading/empty/error rules in CLAUDE.md.

## Done when
1. A staff member with `programs.build` creates a 2-module program with 3 weeks in each module, and it publishes.
2. A staff member with `cohorts.manage` creates a cohort with 2 groups. Its schedule skips a closed week and shows a bank holiday.
3. A learner added to a group sees modules and dated weeks in the player.
4. Small tests, ruff, `makemigrations --check`, `tsc -b` and `vite build` all pass. The new migrations are listed for the user.
