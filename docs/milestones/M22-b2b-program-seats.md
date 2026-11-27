# M22: B2B company signup, program seat orders, allocation, swaps and the line manager view

Plan: `docs/features/programs-v1/plan.md` §4 M22, decisions D8, D9, D10, D11 and D22.
Product rule: sold to many providers. Rules are settings (per program), staff powers are permissions.

## Why new tables (deviation from plan §3)
The plan says `SeatPurchase` gains a `SeatLine` and every swap step goes into `AllocationEvent`.
`SeatPurchase.offering` and `AllocationEvent.allocation` are NOT NULL. Making them nullable would alter
existing columns on Neon, which CLAUDE.md does not allow without asking. So program seats get their own
tables in `apps/corporate`, next to the course-seat ones. The old course-seat flow is unchanged.

## B1. Data (all additive)
- `org.Organization.onboarding_state`: `ordering` / `awaiting_payment` / `active`, `db_default='active'`.
  Existing companies stay active. A company made by the new signup starts at `ordering`.
- `delivery.ProgramSetting` gains:
  - `min_seats_per_line` (default 2);
  - `swap_cutoff_mode`: `none` / `progress_pct` / `week`;
  - `swap_cutoff_value` (default 0).
- `corporate.ProgramSeatOrder` (TenantModel): buyer, status `draft` / `pending` / `paid` / `expired`,
  currency, total_minor, stripe_session_id, payment_intent, paid_at.
- `corporate.ProgramSeatLine` (TenantModel): order, offer (commerce.ProgramOffer: program, module or
  whole, live or recorded), cohort (live lines only), seats, unit_minor, total_minor.
- `corporate.ProgramSeatAllocation` (TenantModel): line, member (OrgMember), user, enrollment,
  status `active` / `released` / `swapped`, allocated_by, released_at, released_by, note.
  One active allocation per (line, user).
- `corporate.SeatSwapRequest` (TenantModel): allocation, to_member, requested_by, reason,
  status `pending_company` → `pending_provider` → `approved` / `rejected` (or `cancelled`),
  after_cutoff, company_by/at, provider_by/at, decision_note, new_allocation.
  One open request per allocation.
- `corporate.ProgramSeatEvent` (TenantModel): the audit trail. line, allocation, swap, action, actor,
  target_user, previous_user, note.
- RLS: every new corporate table is `company_only` (FORCE). The provider reads them through the console
  (staff context).
- `EnrollmentModule.Source` gains `seat`.
- Staff permission `seats.approve_swap`.

## B2. Company signup and the workspace gate (D8, D9)
- `POST /org/signup` (signed in): company name and billing currency. It creates the company with the user
  as owner, at `ordering`. Refused if the user already has a company still being set up (they carry on with it).
- `MembershipOut` gains `onboarding_state`.
- `core.permissions.require_org_role` and `org_scope` refuse a company that isn't `active`
  (`403 workspace_locked`). Only the order and checkout endpoints pass `allow_setup=True`.
  It is one query, as before (the member row joins the company).

## B3. The order (D8, D10)
- `GET /corporate/program-seats/catalogue`: the programs on sale with their offers (price per seat in the
  company's currency), the intakes for live offers, and each program's minimum seats per line.
- `PUT /corporate/program-seats/draft`: replaces the lines of the company's one draft order. Each line is
  an offer, an intake (live only, which must be a placeable cohort of that program) and seats ≥ the
  minimum (max 500). Prices come from the server, never the browser.
- `POST /corporate/program-seats/draft/checkout`: card payment through Stripe (payment mode, metadata
  `kind=program_seats`), with the order marked `pending` and the company `awaiting_payment` if it was
  `ordering`. Owner or admin only.
- Webhook `checkout.session.completed` with `kind=program_seats`: order `paid`, and the company becomes
  `active`. It is idempotent and checks the amount and currency. `expired` sets the order back to `draft`
  and the company back to `ordering` (when not active yet).
- `GET /corporate/program-seats/orders`: the orders with lines, seats used and seats left.

## B4. Allocation
- `POST /corporate/program-seats/allocate` {line_id, member_id}: owner or admin, or a manager for people
  in their units.
  - Checks: the order is paid, a seat is free, the person is an active member, and they don't already have a
    company place on that program.
  - It creates (or reopens) the company enrolment (`source=organization`, `org_id`, `source_ref=allocation`).
    A module line sets scope `modules` plus an `EnrollmentModule` (source `seat`). A whole-program line sets
    scope `program`.
  - A live line places the learner in the intake's group with the most room. If every group is full, the
    learner keeps the seat in the cohort and cohort managers are told (same as B2C).
  - The capacity check counts every enrolment (SECURITY DEFINER count), never only the rows this company can see.
- `POST /corporate/program-seats/allocations/{id}/release`: owner or admin, only before the learner has
  started (no progress, never opened). After that, a seat moves only by a swap.

## B5. Seat swaps (D11)
- `POST /corporate/program-seats/allocations/{id}/swap` {to_member_id, reason}.
  - Raised by an owner or admin, or by a manager whose units cover the current seat holder.
  - The company step is approved at once when the requester may approve it: an owner or admin, or a manager
    whose units also cover the new person. Otherwise it waits at `pending_company`.
  - Cut-off (program setting): past it (progress % reached, or week N of the cohort reached), a reason of at
    least 10 characters is required, and the request is flagged.
- `POST /corporate/program-seats/swaps/{id}/decide` {approve, note}: the company step (owner, admin or a
  manager covering the new person).
- `POST /corporate/program-seats/swaps/{id}/cancel`: the requester or an admin, while it is still pending.
- Console: `GET /console/seat-swaps` (pending first) and `POST /console/seat-swaps/{id}/decide`.
  Permission `seats.approve_swap`. Approving does the swap in one transaction:
  - the old allocation becomes `swapped` and the old enrolment `revoked`, so its progress stays on record;
  - the new person gets the seat, the same scope and the same intake;
  - every step writes a `ProgramSeatEvent`.
- Notifications (one insert-only data migration for the wording):
  - a request waiting for the company goes to the company approvers;
  - one waiting for the provider goes to staff with `seats.approve_swap`;
  - the decision goes to the requester;
  - the new learner is told they have a place.

## B6. Line manager view (D22)
- `GET /corporate/program-seats/team?cursor=`: the seat holders the caller can see (all of them for owner
  and admin, the manager's units for a manager), keyset by allocation.
  - Each row: program, mode, intake and group, progress %, KSBs met out of mapped, the OTJ RAG with counted
    and expected hours, and attendance (sessions attended out of past sessions).
  - The queries per page are fixed (batched); a test pins them.
- A manager approves swaps for their team (B5). They sign nothing else.

## Frontend
- `/business/start` (signed in, outside the workspace): the signup wizard.
  1. Company: name and currency.
  2. Order: pick programs, modules, mode, intake and seats, with a running total.
  3. Pay: Stripe.
  The workspace guard sends a company that isn't active here. After paying it shows "waiting for payment"
  until the webhook lands, then opens the workspace. Links: the business landing page and the user menu.
- `/business/program-seats`: the orders, the lines with seats used and left, allocate (pick a person),
  release, request a swap, the swaps waiting for this person, and "Buy more seats" (the same order builder).
- `/business/team`: the line manager view (table on desktop, cards on a phone), with Ring and progress fills.
- `/console/seat-swaps`: the provider's queue, with approve and reject.
- Program settings (console › program › Settings): minimum seats and the swap cut-off.
- Artwork: the existing `seats` backdrop for seats and setup; `orgchart` for the team view.

## Tests (small, M22 only)
- Signup creates an `ordering` company, and the workspace endpoints refuse it with `workspace_locked`.
- Draft rules: minimum seats, live needs an intake, server prices, module lines.
- Checkout, then paid webhook: the order is paid and the company active. Amount mismatch is refused.
  Expiry goes back to the draft.
- Allocate: a live line places in a group, a module line limits scope, there is no seat left, and a
  manager is limited to their units.
- Swap: auto company approval vs `pending_company`, the cut-off needs a reason, provider approval moves
  the seat (old enrolment revoked, progress kept), and a rejection changes nothing.
- Team view rows, and a pinned query count.
- The contract test prefixes include `/corporate/program-seats` and `/console/seat-swaps`.

## Migrations (the user runs them on Neon)
- org `onboarding_state`;
- delivery ProgramSetting columns;
- corporate program seat tables, plus their RLS;
- learning EnrollmentModule source choice (state only);
- engagement notification wording (insert only).
