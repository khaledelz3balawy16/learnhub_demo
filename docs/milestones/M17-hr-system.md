# M17 — HR system integration (Breathe HR)

**Goal.** A company admin connects their Breathe HR account on one new page,
`/business/hr-system`. LearnHub then keeps the company's people, departments, training
records and approved leave in step with Breathe. Nothing is copied by hand, and nothing
is faked: the connector talks to the real Breathe API (sandbox key for the demo).

**Origin.** `E:\Kent\LMS_v2`, branch `origin/Breathe-HR`. We port the *capabilities*,
not its portal. LearnHub already has the company side (`apps/org`, `apps/compliance`,
`/business/*`), so this must read as one product.

**When.** After M6 and the final regression of `docs/goal.md` (numbered M17 because
M7 to M16 are the B2C monetization briefs). User decisions, 2026-11-14:
- a Breathe sandbox key is available (real connector);
- `cryptography` may be pinned (already installed through `django-allauth[mfa]`);
- scope = employees + departments + training records → compliance evidence + approved
  leave shown as "on leave".

**Mockups.** None. Follow `docs/design/README.md`: mockup 18 (settings sections),
05 (table + detail sheet), 33 (table with side summary).

---

## Mapping: what each LMS_v2 piece becomes here

| LMS_v2 (Breathe-HR) | LearnHub | Decision |
|---|---|---|
| `IntegrationTenant` | `org.Organization` | reuse, no new table |
| Employer `portal_role` hr / manager | `OrgMember.role` owner/admin (= HR) vs manager | reuse; no new role |
| B2B portal page (8 tabs) | existing `/business` pages | reuse; only **one new page** `/business/hr-system` |
| `IntegrationConnection` (+`secret_ciphertext`) | new `integrations.HrConnection` | port; key encrypted with Fernet; account id read from Breathe, not typed |
| `ExternalPersonLink` + approve-match | new `integrations.ExternalPerson` + match / invite / ignore | port; an email match is a *suggestion* an admin confirms |
| `DepartmentMapping` | new `integrations.ExternalDepartment` → `org.OrgUnit(kind=department, code=external id)` | port; reuse `org.services.create_unit` |
| `ManagerRelationship` | `org.UnitManager` via `set_unit_managers` (feature `managers`, add-only) | port, lighter |
| `ExternalTrainingRecord` | new `integrations.ExternalTrainingRecord` + `HrTrainingMap(title → compliance.Requirement)` → `compliance.CompletionRecord(source=IMPORT)` | port; the `IMPORT` source already exists, unused |
| `AvailabilityBlock` (approved leave) | new `integrations.ExternalLeave` → "On leave until …" badge | port the import only; **no** scheduling conflicts |
| `SchedulingConflict`, `ManagerSignatoryGrant` | — | not ported (apprenticeship-specific) |
| `CompanyTrainingRule` / `Allocation`, demo metrics, demo workspace | `compliance.Requirement + RequirementTarget(unit=department)` | **not ported**: our requirements already are department training rules; demo data is forbidden |
| `IntegrationSyncRun` + command + HMAC scheduler | new `integrations.HrSyncRun` run by Celery + hourly beat | port, Celery-native |
| `breathe.py` client (`requests`) | `apps/integrations/breathe.py` on **httpx** (already a dependency) | port: origin allow-list, Link-header pagination, rate limit, retries, no redirects |
| `IntegrationAuditLog` | `apps.platform.services.audit_request` | reuse |

---

## Work packages

### P1 Backend app `apps/integrations` (schema `integrations`, mounted at `/api/v1/integrations/`)
Files: `apps.py, models.py, schemas.py, breathe.py, normalizers.py, secrets.py, services.py,
selectors.py, tasks.py, api.py, admin.py, migrations/, tests/`. Layer: above compliance;
imports `org`, `compliance`, `engagement.notify`; nothing imports it.

Models (all `core.models.TenantModel`, `db_table = table("integrations", …)`):
- `HrConnection`: provider, external_account_id, account_name, base_url, secret_ciphertext,
  status (pending/active/attention/disabled), enabled_features (`departments`, `managers`,
  `training`, `leave`), last_verified_at, last_sync_at, last_error, created_by.
  Unique `(org)`, `(provider, external_account_id)`, `(org, id)`.
- `ExternalPerson`: connection, external_employee_id, email, display_name, job_title,
  department_external_id/name, manager_external_id, employment_status, start_date,
  contracted_hours, working_pattern, member FK `org.OrgMember` null, invite FK `org.Invite`
  null, mapping_status (pending/matched/invited/ignored), last_seen_at, source_updated_at.
  Unique `(connection, external_employee_id)`; index `(org, display_name, id)` for keyset.
- `ExternalDepartment`: connection, external_department_id, name, unit FK `org.OrgUnit` null,
  status (pending/linked/ignored), last_seen_at.
- `ExternalTrainingRecord`: connection, external_training_id, external_employee_id, person FK
  null, title, category, completion_date, status, certificate_ref, applied_record FK
  `compliance.CompletionRecord` null, applied_at.
- `HrTrainingMap`: connection, title_key, title, requirement FK `compliance.Requirement`
  PROTECT. Unique `(connection, title_key)`.
- `ExternalLeave`: connection, person FK null, external_employee_id, source_ref, starts_on,
  ends_on, leave_type, status (approved only). Unique `(connection, source_ref)`; index
  `(org, person, ends_on)`.
- `HrSyncRun`: connection, status (queued/running/completed/failed), resources, dry_run,
  idempotency_key, counts, error_code, error_message, triggered_by, started_at, finished_at.
  Unique `(connection, idempotency_key)`.

Migrations (additive only, never `--fake`; use the next free numbers when the build starts):
- `core/migrations/0003_integrations_schema.py`: `CREATE SCHEMA IF NOT EXISTS integrations`
  + the grant block of `core/migrations/0001_foundation.py` for `lms_app`.
- `integrations/0001_initial.py` (makemigrations; depends on core 0003, org 0002, compliance 0002).
- `integrations/0002_security.py`: pattern of `apps/org/migrations/0002_security.py`:
  `rls.company_only` on every table + `rls.composite_fk` for connection/member/unit/person/
  requirement links. Plain FKs for `invite_id` and `applied_record_id` (those parents lack
  `UNIQUE(org_id,id)`; say so in the docstring).
- `engagement/0009_hr_system_templates.py`: insert-only; codes `hr_sync_failed`,
  `hr_people_to_review`, `hr_connection_attention` (pattern of
  `0004_course_assigned_template.py`); all `url="/business/hr-system"`.

Settings: `DOMAIN_APPS += "apps.integrations"`; `CELERY_BEAT_SCHEDULE["hr-sync-hourly"]`;
`HR_INTEGRATION = {"CREDENTIAL_KEY": env, "ALLOWED_HOSTS": [api.breathehr.com,
api.sandbox.breathehr.info]}`; `requirements.txt` pin `cryptography==50.0.2`.

Test plumbing: `integrations` in `core/tests/base.py::TRUNCATE_SCHEMAS` and
`core/tests/test_rls.py::DOMAIN_SCHEMAS`; `/api/v1/integrations/` in
`test_api_contract.py::TYPED_PREFIXES`; two routes in `test_query_budgets.py`.

### P2 Breathe client, secrets, normalizers
- `breathe.py`: port of LMS_v2 `backend/integrations/breathe.py` on
  `httpx.Client(follow_redirects=False, timeout=30)`; module-level `transport = None` hook
  (pattern of `core/storage.py`) so tests and the harness inject `httpx.MockTransport`. Keep
  `validated_base_url`, rate limit, 429/5xx retries with capped `Retry-After`, Link pagination
  with a visited guard, `account()`, `list_resource()`. Resources: `account, employees,
  departments, employee_training_courses, leave_requests`.
- `secrets.py`: `encrypt/decrypt/is_configured` (Fernet key = urlsafe_b64(sha256(
  `CREDENTIAL_ENCRYPTION_KEY`))). Missing key → `ServiceError("not_configured", …, status=503)`.
  The plaintext key is never returned, logged or audited.
- `normalizers.py`: port `normalize_employee/department/training`; add `normalize_leave`
  (approved only).

### P3 Services (`services.py`; every error is a `ServiceError`)
- `connect`: validates the origin, reads `/v1/account`, 409 `account_in_use` if another org
  owns it, creates or re-activates the org's one connection.
- `validate`; `replace_key` (must resolve to the same account); `set_features`;
  `disconnect` (status disabled, ciphertext cleared, rows kept).
- `queue_sync`: 409 `already_running`; idempotent by key; `on_commit → hr_sync_run_task`.
- `process_sync`: runs in `tenant_context`; per resource `update_or_create`; then auto-link
  departments whose `code` matches an unarchived unit, `_place_in_department` for matched
  people, `apply_training_records`, leave upsert, `reconcile_members`, notifications. On
  failure: run `failed`, connection `attention`.
- `match_person`: sets the member, fills blank `employee_ref`/`job_title`, places them in the
  linked department unit (→ `structure_changed` → compliance assigns).
- `invite_person`: reuses `org.services.invite` with unit + job role; status invited.
- `ignore_person` / `reset_person`.
- `link_department` (`create=True` → `org.services.create_unit(parent=root,
  kind="department", code=external id)`); `unlink_department`.
- `map_training`; `apply_training_records` (→ `CompletionRecord(source=IMPORT,
  note="Breathe: …")`, then `compliance.engine.recompute`).
- `reconcile_members`: an invited person whose invite was accepted → matched; wired from
  `org.signals.structure_changed` in `apps.py`.
- `_place_in_department`: feature `departments` → `add_member_to_unit`; feature `managers` →
  `set_unit_managers` (add only, never removes manual managers).

### P4 Selectors (`selectors.py`)
`connection_for`, `overview` (one aggregate query for the counts; never the ciphertext),
`people` (keyset `(display_name, id)`; managers see matched people in `scope.members()` only;
one extra query for suggested matches by email), `runs`, `departments`, `training_titles`,
`training_records`, `leave_for_members(member_ids, today)` (current + upcoming),
`member_link(member_id)`.

### P5 Tasks (`tasks.py`)
`integrations.hr_sync_run(run_id)`, `integrations.hr_hourly` (beat; key
`hourly:<conn>:<YYYY-MM-DDTHH>`), `integrations.hr_reconcile(org_id, member_ids)`.

### P6 API (`api.py`; all `org_scope(request, OrgRole.MANAGER)`; writes need `scope.require_admin()` + `audit_request`)
`GET hr` → `HrOverviewOut` · `POST hr/connect` `HrConnectIn` · `POST hr/validate` ·
`POST hr/replace-key` · `PATCH hr/features` · `DELETE hr` · `POST hr/sync` → `HrQueueSyncOut` ·
`GET hr/runs`, `GET hr/runs/{id}` · `GET hr/people` (status, q, cursor) → `HrPersonPage` ·
`POST hr/people/{id}/match|invite|ignore|reset` · `GET hr/departments`,
`PUT hr/departments/{id}/unit` · `GET hr/training/titles`, `PUT hr/training/map`,
`GET hr/training/records` · `GET hr/leave?member_ids=` → `HrLeaveOut[]` ·
`GET hr/members/{member_id}` → `HrMemberLinkOut`. Every schema name starts with `Hr`.

### P7 Frontend
- Route `/business/hr-system` in `frontend/src/app/router.tsx`, `handle: { art: 'handover' }`;
  Company nav section → "HR system" (lucide `Plug`, imported on its own).
- New backdrop variant **`handover`** in `components/art/backdrops.tsx` (two card stacks
  exchanging records, dashed arrows, same style as the others); add a row to `frontend/README.md`.
- Hooks in `src/features/integrations/api.ts`. `useHrOverview` polls every 3 s while a run is
  active. Mutations invalidate `['integrations']` plus: match → `org/people`, `org/units`,
  `compliance`; invite → `org/invites`, `org/company`; link department → `org/units`,
  `org/people`, `compliance`; map training → `compliance`. Types come from `/sync-types` only.
- Page `src/pages/business/HrSystemPage.tsx`:
  - `PageHeader`; states: `ErrorState`, `Skeleton`, server-not-configured `EmptyState`,
    manager read-only `EmptyState`, and for admins a Connect card (password field with
    show/hide, Production/Sandbox select, feature `Switch`es, a plain note of what is read).
  - Connected: a connection card (status badge, account, last sync, "Sync now" with spinner,
    "Check connection", Replace key / Pause / Disconnect dialogs) + 4 KPI cards that count up.
  - `Tabs` synced to `?tab=`:
    - **People**: status chips, search, table, side sheet with Breathe details → suggested
      match "Link to <name>", choose someone (`usePeopleSearch`), invite form (role via
      `useAssignableRoles`, unit prefilled), ignore;
    - **Departments**: link to a unit (`useUnits`) or "Create department unit";
    - **Training**: title → requirement (`useRequirements`); records list;
    - **History**: sync runs, with `stagger`.
  - Light and dark, phone-safe tables (InvitesPage hidden-column pattern), labels and aria,
    British English.
- Touches: `PersonPage.tsx` badges "Synced from Breathe · <id>" and "On leave until <date>";
  `PeoplePage.tsx` small "On leave" badge (one `useHrLeave(memberIds)` call per page);
  `UnitsPage.tsx` "Breathe" badge on linked units. Add the route to
  `tools/harness/phone_business.js`.

### P8 Tests and harness
- `apps/integrations/tests/`:
  - `test_breathe_client.py`: pagination, off-origin rejected, 3xx rejected, 429 retry with an
    injected sleep, bad origins;
  - `test_secrets.py`;
  - `test_sync.py`: create/update idempotent, dry run, auto-link, failure → attention +
    notification, hourly dedupe, training → `CompletionRecord` → compliant, leave upsert;
  - `test_api.py`: learner 403; manager read-only; admin flow connect → sync → people →
    match → invite → accept → matched; department create; training map; member link; the key
    never appears in any response body; another org sees nothing.
- Fixture `tests/test_fixtures.py::breathe_transport(...)` (`httpx.MockTransport`, two pages
  with a `Link` header).
- Harness (test doubles live only here): `tools/harness/fake_breathe.py` deterministic
  transport; `e2e_wsgi.py` and a new `e2e_celery.py` install it; document it in
  `tools/harness/README.md`.
- `tools/harness/e2e_m17.js`: not connected → connect → sync completes → people to review = N
  → suggested match → link → Person page badge → create department unit → Units badge →
  invite → accept → matched → map training → person shows the imported record, compliant →
  leave badge → History → a manager sees read-only. No console errors, no 5xx; light and dark
  screenshots.

### P9 Docs at the end
`docs/build-status.md` (built, bugs, migrations, env var), `frontend/README.md` (backdrop),
`docs/client-questions.md` if anything new, `tools/harness/README.md`, `docs/STRUCTURE.md`.

---

## Out of scope
Scheduling conflicts, manager signatory grants, LMS_v2 training rules/allocations, demo
metrics or a demo workspace, writing anything back to Breathe, removing members when Breathe
marks them as leavers (flag only), other HR providers (the model keeps a `provider` field).

## Acceptance (= the E2E outline)
1. An admin connects with the sandbox key; the account name comes from Breathe; the key is
   never shown again or returned by any endpoint.
2. "Sync now" completes; People shows the Breathe employees with "to review" counts.
3. A suggested email match links a person; their Person page shows "Synced from Breathe".
4. "Create department unit" makes a real `OrgUnit`; the Units page shows a "Breathe" badge;
   matched people in that department are placed in it and compliance assigns their training.
5. Inviting an unmatched person sends a real invite; accepting it turns them "matched".
6. Mapping a Breathe training title to a requirement imports a `CompletionRecord`; the person
   becomes compliant for it.
7. Approved leave shows "On leave until …" on People and the Person page.
8. A failed sync marks the connection "needs attention" and notifies admins.
9. A manager sees the page read-only; a learner gets 403; another org sees nothing.
10. Hourly sync does not run twice in the same hour.

## Needs from the user before the build
- `CREDENTIAL_ENCRYPTION_KEY` in `backend/.env` (and e2e/production): 32+ random characters.
  Losing it means every company reconnects.
- Approve the pin `cryptography==50.0.2`.
- Run the migrations on dev and e2e (all additive): core 0003, integrations 0001/0002,
  engagement 0009.
- Enter the Breathe sandbox key on `/business/hr-system` (never in code or chat). Confirm the
  Breathe endpoint paths against the current docs before the live check.

## Verification
1. `python tools/run_check.py mig-check -- python manage.py makemigrations --check --dry-run --cwd backend`;
   ask the user, then `migrate --database owner` on dev and e2e (show `sqlmigrate` first).
2. `python tools/run_check.py int-tests -- python manage.py test apps.integrations core.tests.test_api_contract core.tests.test_rls core.tests.test_query_budgets --keepdb --noinput --cwd backend`,
   then the full suite once in the background; `ruff check . ; ruff format --check .`.
3. `/sync-types`; `npx tsc -b`; `npx vite build` (new page is its own chunk; the main entry
   must not grow).
4. `node tools/harness/e2e_m17.js shots/m17`, the earlier E2E scripts, `phone_business.js`;
   compare the screenshots with mockups 18/05/33.
5. Live check with the sandbox key entered in the UI: connect, validate, one sync.
6. `reviewer` agent on the diff; fix the findings; `/status`.
