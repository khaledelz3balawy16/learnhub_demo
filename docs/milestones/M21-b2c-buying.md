# M21: B2C buying (programs)

Plan: `docs/features/programs-v1/plan.md` (D5, D6, D7, D10, D29). Builds on M18 (cohorts, groups,
placement), M19 (records) and M20 (sessions). Testing: small targeted tests only (user decision,
2026-11-16). The product is sold to many providers: prices, instalment counts and the grace period are
data or settings, never code. **This milestone lifts D29 for B2C:** a published program with at least one
active offer is listed, priced and sold. B2B selling stays hidden until M22.

## Backend

### B1 Offers (commerce, additive, RLS `reference`)
- `ProgramOffer`: `program` (Course, kind `program`), `module_key` (NULL = the whole program), `mode`
  (`live`/`recorded`), `tier` (PriceTier, NULL = not sold for cash), `token_price` (recorded modules only,
  D6), `instalments_max` (1–24; above 1 only for live offers, D7), `is_active`.
- One offer per (program, mode) for the whole program, and per (program, module, mode) for a module.
  Check constraints: tokens only on a recorded module offer; every offer has a cash or a token price.
- Console (`programs.build`): list, create and edit a program's offers. Never deleted, switched off instead.

### B2 What a learner may buy
- Whole program, live: a seat in a chosen intake (cohort). Whole program, recorded: self-paced access.
- One module, live or recorded: access to that module only. A recorded module can also be unlocked with
  tokens (D6). Live seats are cash only.
- One personal enrolment per learner and program (unchanged). New `Enrollment.scope` (`program`/`modules`)
  and `EnrollmentModule` (enrolment, module_key, source, source_ref) record what is covered. Buying the
  whole program later turns `scope` into `program` (the module rows stay as history).
- "Already owned" is refused per case: recorded is owned by any enrolment covering it; live also needs a
  group. A recorded learner may buy a live seat later (upgrade).
- The player refuses lessons in modules the learner hasn't bought (403 `module_locked`) and the program
  view says which modules are owned.

### B3 Intakes and seats
- Intakes = the program's cohorts that are `planned` or `open` (and `running` ones still taking learners),
  with an active group. "Places left" = the sum of the active groups' spare places, also capped by the
  cohort's capacity. Learners can't see other people's enrolments under RLS, so the counts come from a
  SECURITY DEFINER function `learning.cohort_seat_counts(uuid[])` that returns numbers only.
- Checkout refuses a full intake. On payment the learner goes to the group with the most spare places
  (`placement.place`, which re-checks capacity under a lock). If a race filled every group meanwhile, the
  learner keeps the paid enrolment, joins the cohort without a group, and cohort managers get a notice to
  place them (client question #31 still decides waitlists).

### B4 Checkout and payment
- `POST /programs/checkout {offer_id, currency, cohort_id?, instalments}` → `{order_id, checkout_url}`.
  The price is computed on the server from the offer's tier (the same tier amounts and FX as courses). No
  coupons or promotions on programs in M21.
- Paid in full: a normal `Order` with one `OrderItem` (`offer`, `cohort`), Stripe Checkout in payment
  mode; the existing webhook, amount check, receipt and success page apply.
- Instalments (D7, live offers with `instalments_max` > 1): N monthly payments of ⌈price ÷ N⌉ (the total
  shown is N × that amount). `InstalmentPlan` (order, count, amount, paid count, status
  `pending`/`active`/`past_due`/`completed`/`cancelled`, Stripe ids, `grace_until`) and `InstalmentPayment`
  (one row per Stripe invoice, unique). Stripe Checkout in subscription mode with an inline monthly price.
  - The first paid invoice fulfils the order (enrol + seat). Every paid invoice is counted once (unique
    invoice id) and its amount must match. After the Nth payment the Stripe subscription is cancelled.
  - A failed payment marks the plan `past_due` and sets `grace_until` = now + setting
    `payments.instalment_grace_days` (default 7). The learner's access ends then (`access_expires_at`),
    unless a later payment clears it. Stripe giving up (subscription cancelled) ends the plan.
  - The player says "payment overdue" (403 `payment_overdue`) instead of "access ended" in that case.
- Refunds: a program paid in full follows the normal refund window. Instalment orders are refunded by staff
  in Stripe, not in the app (client question #34 keeps the policy open).
- `GET /orders/{id}` (the success page) also completes an instalment order from Stripe when the webhook is late.

### B5 Tokens for recorded modules (D6)
- `POST /programs/unlock-module {offer_id}`: spends the offer's tokens (the existing wallet, earliest-expiring
  grants first), enrols if needed and adds the module. Refused when the module is already covered.

### B6 Listing (D29 lifted for B2C)
- Catalogue list and search show published programs with an active offer; cards show the lowest cash price
  ("from"). Course flows (cart, packages, plans, lesson unlocks) still sell short courses only.
- Course detail for a program returns `offers` (with prices in the chosen currency), `intakes` and the
  viewer's `program_access` (scope, owned modules, live or not).

## Frontend
- Program page (`/courses/:slug`): a buy box for programs: choose live or recorded, whole program or a
  module, the intake (live), pay in full or monthly; price and total; "Unlock with N tokens" for recorded
  modules. An intakes section lists dates and places left. Enrolled learners see what they own and can buy more.
- Player: locked modules show a lock and a "Buy this module" link to the program page.
- Console → Programs → program: an Offers panel (`programs.build`) to add and edit offers.
- Account → Orders: instalment orders show "2 of 6 paid" and an overdue warning.
- Every state: loading, empty, error; light and dark; phone width.

## Tests (small)
- Offer constraints and console permissions; checkout refuses full intakes, owned access and bad counts.
- Full payment places the learner in the emptiest group; recorded gives self-paced access; module scope
  locks other modules in the player.
- Instalments: first invoice fulfils, repeats are ignored, a wrong amount is refused, a failure sets the
  grace period and a later payment clears it, the Nth payment completes and cancels.
- Token module unlock spends tokens once and refuses a second unlock.

## Migrations (the user runs them with `migrate --database owner`; all additive)
- commerce: `ProgramOffer`, `InstalmentPlan`, `InstalmentPayment`, `OrderItem.offer` / `OrderItem.cohort`, RLS.
- learning: `Enrollment.scope`, `EnrollmentModule`, RLS, `cohort_seat_counts`.
