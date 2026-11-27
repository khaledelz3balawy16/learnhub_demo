# Demo script (20–30 minutes)

A click path for the client meeting, one persona at a time. Everything shown is real data from the
seed commands (`seed_demo`, `seed_console_demo`, `seed_tokens`, `seed_b2c_subscription`,
`seed_corporate_demo`). Payments use Stripe **test** cards.

**Logins** (all seeded accounts share one password: **ask Zeeka**, never write it here):

| Persona | Account |
|---|---|
| Staff (platform admin) | `contact+be32cf86821a@example.com` |
| Instructor | `contact+357c4693de0b@example.com` (Daniel Reeve) |
| Company HR (admin) | `contact+306124cbddbf@example.com` (Brightwater Care Group) |
| Company manager | the first Brightwater manager printed by `seed_demo` |
| Learner | the learner printed by `seed_demo` |
| Corporate packages owner | `b2b.demo.owner@learnhub.example` |

Before the meeting: log in once as each persona (warms the caches), have a Stripe test card ready
(4242 4242 4242 4242, any future date, any CVC), and open the site in light mode. Switch to dark mode once
during the demo (top bar) to show it.

---

## 1. Visitor (3 min)

1. **Home** (`/`). *"A marketplace for anyone, and a compliance workspace for companies, in one product."*
2. Type **"dat"** in the header search. Suggestions appear as you type: a category and courses.
   Pick a course.
3. **Course page.** Point out the curriculum, the free preview (play it), reviews, price, and "unlock with
   tokens" / "included in the Unlimited plan" when shown. *"Visitors can try before they buy."*
4. **Plans** (`/plans`): personal and team plans.
5. Footer: every link goes to a real page.

## 2. Learner (7 min)

Log in as the learner.

1. **My learning** (`/learn`): continue card, courses with progress, and on the right the counts,
   **upcoming deadlines** from the learner's company, and **certificates** with download.
2. Open a course in the **player**: video, notes at a moment, next lecture, Q&A tab.
3. Take the **quiz** at the end. Show the result.
4. **Certificates** (`/learn/certificates`): download one; open **Verify a certificate** (`/verify`) and
   paste its code. *"Anyone can check a certificate is real."*
5. **Token wallet** (`/wallet`): balance and history. **Buy tokens**: pick a pack, pay with the test card,
   land on the result page and watch the balance arrive (credited by Stripe's webhook, never by the
   browser).
6. Back on a course with a token price: **Unlock with tokens**, confirm, **Start learning**: the player
   opens straight away.
7. **Unlimited plan** (`/subscription`) and **Course bundles** (`/packages`): mention, don't buy.

## 3. Company admin and manager (8 min)

Log in as Hana Cole (Brightwater Care Group).

1. **Company overview** (`/business`): compliance at a glance; numbers count up from real records.
2. **Training matrix**: people × required courses, colour-coded. Filter by a site. Open one person.
3. **Person page**: their required training, due dates, extend a deadline or record a completion
   (with a reason; it lands in the audit log).
4. **Requirements**: one rule (for example a yearly course for every Care team) assigns training
   automatically when people join a team.
5. **Locations & teams**, **Invitations**: invite someone by email.
6. **Assign training** from the **Course library**.
7. **Reports**: export a CSV. *"Ready for an inspection."*
8. **Company training** (corporate packages, as `b2b.demo.owner@learnhub.example` if preferred): seats
   bought, live training bookings, refunds and changes.
9. Log in as the **manager** for one minute: they see only their own team.

## 4. Instructor (4 min)

Log in as Daniel Reeve.

1. **Studio dashboard** (`/studio`): sales, students, ratings.
2. Open a course in the **course builder**: details, curriculum (drag to reorder, video parts), pricing,
   submit for review.
3. **Assignments** to grade, **Q&A and reviews** to answer.
4. **Sales and earnings**, **Payouts**: earnings after the platform fee, the payout request.

## 5. Staff (5 min)

Log in as admin.

1. **Console dashboard** (`/console`): platform totals and charts.
2. **Approvals**: approve the course Daniel submitted.
3. **Pricing**, **Commissions**, **Promotions**: all configurable, nothing hard-coded.
4. **Token pricing**: packs, exchange rate, course prices with automatic distribution across lectures.
   **Token wallets**: look up a learner, adjust with a reason.
5. **Companies**, **Certificates** (design and signatory), **Communications** (email wording,
   announcements), **Settings** (platform name, maintenance mode, guest browsing).
6. **Audit log**: every sensitive change, who and when.

## Close (1 min)

*"Everything you clicked is live: real payments in test mode, real video streaming, real emails. The
open business decisions are in our list for you"* (`docs/client-questions.md`).

---

Not in this script on purpose: anything listed as blocked in `docs/features/b2c-monetization-v2/decision-register.md`
(bonus-token campaigns, instructor payouts from token spend) and the planned M17 HR system.

An automated run of this path (`tools/harness/e2e_demo.js`) is part of the testing round the user will ask for.
