# M20: Live sessions, recordings and workshops

Plan: `docs/features/programs-v1/plan.md` (D3, D14, D17, D18, D19, D24). Builds on M18 (cohorts, groups,
calendar) and M19 (OTJ ledger, CPD). Testing: small targeted tests only (user decision, 2026-11-16).
The product is sold to many providers: every rule is a setting with a default, and each install connects
its own Microsoft tenant (D19). **Nothing here needs Teams to work:** without a tenant, staff paste a link,
mark attendance and upload the recording themselves (manual fallback, in full).

## Backend

### B1 Models (delivery, additive)
- `LiveSession`: group, `lecture_key` (a program component of kind `live_session`), `starts_at` (UTC),
  `duration_min`, `provider` (`manual`/`teams`), `join_url`, `teams_meeting_id`, `teams_organizer`,
  `status` (`scheduled`/`cancelled`), `attendance_synced_at`, `recording_status`
  (`none`/`pending`/`ready`/`failed`), `recording` (FK `catalog.MediaAsset`, nullable), `transcript` (text),
  `recording_attempts`. Unique (group, lecture_key). The organiser/host URL is never stored or sent.
- `SessionAttendance`: session, enrolment, `minutes`, `first_join`, `last_leave`, `source`
  (`graph`/`manual`), `marked_by`. Unique (session, enrolment).
- `Workshop` (D24): program, optional cohort, `title`, `description`, `starts_at`, `duration_min`,
  `capacity` (nullable = no limit), `provider`, `join_url`, Teams fields, `expected_otj_min`, `cpd_min`,
  `status` (`scheduled`/`cancelled`), recording fields as on `LiveSession`, `created_by`.
- `WorkshopBooking`: workshop, enrolment, `status` (`booked`/`cancelled`), `attended_min` (nullable),
  `source`, `marked_by`. Unique (workshop, enrolment).
- RLS: sessions and workshops `reference` (like cohorts and groups). Attendance and bookings are learner
  rows: org and user copied from the enrolment by trigger, RLS `mixed`.

### B2 Planning a group's sessions
- `plan_sessions(group)`: one session per live component in the program's published version. The date is the
  group's weekday inside that component's week (from the cohort schedule). If that day is not a working day,
  the next working day in the same week; if none, the session is skipped and reported. Times: the group's
  start and end time in the provider time zone (setting `general.time_zone`), stored in UTC.
- Idempotent: re-planning moves future sessions that have no attendance; it never touches past or attended
  sessions and never deletes. A component removed from the program cancels its future session.
- Staff can move one session (date, time, length), paste a link or cancel it.

### B3 Microsoft Teams (Graph, app-only)
- Generalise `catalog/teams.py`: `create_meeting(subject, starts, ends)`, `update_meeting`,
  `attendance(meeting_id)` (attendance reports → email, minutes, first join, last leave),
  `recordings(meeting_id)` and `transcript(meeting_id)`. Same token cache and error codes. The existing
  lecture call keeps working.
- "Connected" = the Graph settings and `TEAMS_MEETING_ORGANIZER` are set in `.env`. `GET console/meetings/status`
  says whether Teams is connected (no secrets).
- Planning with Teams connected creates or updates a meeting per session (on commit, Celery, idempotent).

### B4 Attendance → OTJ
- Pull from Teams (task + "Fetch from Teams" button): match attendee emails to the group's learners; unknown
  people are ignored. Manual marking: present (full length), minutes, or absent.
- Present when minutes ≥ setting `learning.live_present_min` (default 3). Present learners get an
  `OtjEntry` (`live_session`, `source_ref` = session id, minutes capped at the session length,
  `auto_approved`); re-marking updates it, absent removes it. Workshops do the same with source `workshop`,
  using the attended minutes (capped) or `expected_otj_min` when marked present without minutes.
- Workshop CPD: attended workshops add `cpd_min` to the learner's CPD (D24), shown in the record.

### B5 Recordings (D18)
- Celery beat task every 30 minutes: Teams sessions and workshops that ended more than
  `learning.recording_pull_after_min` (default 30) ago with no recording: list recordings via Graph, ask
  Bunny to fetch the file (server-side, auth header passed, nothing streamed through Django), create the
  `MediaAsset`, store the transcript text. Idempotent, at most 5 attempts, then `failed`.
- Manual: staff upload a recording through the existing Bunny TUS flow (`MediaAsset` for the session).
- Learners in the group see the recording (signed embed via `media.playback`) once it is ready.
  Recorded-mode learners (the program's master recording) arrive with M21 buying modes.

### B6 Endpoints (typed, audited writes)
- Console (`groups.teach` for own groups, `cohorts.manage` for all):
  - `GET cohorts/{id}/groups/{gid}/sessions`, `POST .../sessions/plan`, `PATCH sessions/{id}`,
    `POST sessions/{id}/teams` (create or refresh the meeting), `GET/PUT sessions/{id}/attendance`,
    `POST sessions/{id}/attendance/sync`, `POST sessions/{id}/recording` (start upload).
  - Workshops (`cohorts.manage` writes; tutors read): list (keyset), create, update, cancel,
    `GET/PUT workshops/{id}/attendance`, Teams and recording as for sessions.
  - `GET meetings/status`.
- Learner (`/learning/`): `GET enrollments/{id}/sessions` (own group: date, status, join link only from
  `learning.live_join_early_min` (default 15) minutes before start until the end, recording playback when
  ready, own attendance), `GET enrollments/{id}/workshops`, `POST/DELETE enrollments/{id}/workshops/{wid}/booking`
  (capacity under a row lock; no booking after start).

## Frontend
- F1 Console cohort page, group sheet: a **Sessions** list with "Plan sessions", per-session edit, Teams
  meeting status, attendance sheet (present/absent/minutes, "Fetch from Teams") and recording upload/status.
- F2 Console **Workshops** page (programs area, nav item): list, create/edit dialog, bookings and attendance.
- F3 Learner **Sessions** page `/learn/:slug/sessions`: upcoming and past sessions for my group (join button
  when open, recording when ready, my attendance) and workshops (book, cancel, join, recording). Linked from
  the player and My record. The player's live component shows my group's date and join button.
- F4 `docs/teams-setup.md`: the Azure app registration guide (permissions, application access policy,
  recording access). A line in `docs/user-actions.md`.

## Done when
Small tests for planning, attendance→OTJ, booking capacity, join gate, scope (tutor own groups only) and the
Graph client with a fake transport pass; ruff, `makemigrations --check`, `tsc -b`, `vite build` pass;
reviewer findings fixed; build-status records the migrations.
