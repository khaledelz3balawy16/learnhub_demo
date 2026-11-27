# Deployment checklist

Production today: **https://learnhub.abcsolutions.ai** (LiteSpeed host). The API is on the same
domain (`/api`, `/_allauth`). Deploy from the `learnhub_demo` repository (the user's own line since
2026-11-15), not the team's `learn_hub`. Hosting changes are a client question (#11).

Never put a value from this list in the repo, a doc or a chat. Names only.

## 1. Environment variables (backend, by name)

**Django:** `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY` (50+ random characters),
`DJANGO_ALLOWED_HOSTS`, `DJANGO_ADMIN_URL`, `DJANGO_SSL_REDIRECT` (default on), `DJANGO_DEBUG` (unset / off),
`FRONTEND_URL` (the public https address; email links use it), `NINJA_NUM_PROXIES` (number of proxies in front),
`LOG_LEVEL`, `SLOW_REQUEST_MS`.

**Database (Neon):** `DATABASE_URL` (pooled `-pooler` host, user `lms_app`), `DATABASE_URL_OWNER` (migrations
only), `DATABASE_URL_REPLICA` (optional reads).

**Redis / Celery:** `REDIS_URL` (cache, sessions, rate limits, Celery broker).

**Stripe:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (required when the secret key is set).

**Bunny Stream:** `BUNNY_STREAM_API_KEY`, `BUNNY_STREAM_READONLY_KEY`, `BUNNY_STREAM_TOKEN_KEY`,
`BUNNY_STREAM_LIBRARY_ID`, `BUNNY_STREAM_CDN_HOST`.

**Azure Blob:** `AZURE_STORAGE_ACCOUNT_NAME`, `AZURE_STORAGE_CONTAINER`, `AZURE_STORAGE_TENANT_ID`,
`AZURE_STORAGE_CLIENT_ID`, `AZURE_STORAGE_CLIENT_SECRET`.

**Email (Microsoft Graph):** `MAIL_MODE=graph`, `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`,
`MICROSOFT_CLIENT_SECRET`, `MICROSOFT_GRAPH_BASE_URL`, `MICROSOFT_GRAPH_SCOPE`, `MAIL_ALLOWED_DOMAINS`.
These are shared with Communication Centre: rotate them together.

**Sign-in:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MICROSOFT_LOGIN_CLIENT_ID`,
`MICROSOFT_LOGIN_CLIENT_SECRET`.

**Live sessions (Teams):** `TEAMS_MEETING_ORGANIZER`.

**Seeding only:** `DEMO_PASSWORD` (never set in production after seeding).

**Planned (M17 HR system):** `CREDENTIAL_ENCRYPTION_KEY`.

**Frontend build:** `VITE_API_BASE_URL` (leave empty when the API is on the same domain).

## 2. Settings check

`config/settings/prod.py` refuses to start (with a list of the problems) when: the secret key is short, allowed
hosts are empty, `REDIS_URL` is missing, the database is not the pooled host or not `lms_app`, Graph mail is
missing its three IDs, Stripe has no webhook secret, or `FRONTEND_URL` is not a public https address.

On the server, with the production environment loaded:

```
python manage.py check --deploy
```

(2026-11-15, run locally with dev values: it stops on the secret key and `FRONTEND_URL` only, as expected.)

## 3. Database

1. Show what will run: `python manage.py showmigrations` and `sqlmigrate` for each pending one. Stop and ask if
   anything is not additive (Neon may only gain tables, columns and rows).
2. `python manage.py migrate --database owner` (never `--fake`).
3. Seed only on a fresh database: `seed_demo`, then `seed_console_demo`, `seed_tokens`,
   `seed_b2c_subscription`, `seed_corporate_demo`, `seed_teams_live_demo` as needed.

## 4. Webhooks

| Service | URL | Events |
|---|---|---|
| Stripe | `https://learnhub.abcsolutions.ai/api/v1/commerce/webhooks/stripe` | `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`, `charge.succeeded`, `customer.subscription.*` (incl. paused, resumed, trial_will_end), `invoice.paid`, `invoice.payment_failed` (the handlers in `apps/commerce/webhooks.py`) |
| Bunny Stream | `https://learnhub.abcsolutions.ai/api/v1/platform/webhooks/bunny` | video status (encoded / failed) |

Token packs, top-ups and cash packages are credited **only** by the Stripe webhook (no reconcile by session).

## 5. Sign-in redirect URIs

Google and Microsoft must list the production callback for the new domain. Copy the exact callback URLs from
the values already registered for the current site (Google Cloud console, Microsoft Entra app registration);
sign-in runs through allauth's headless API at `/_allauth/`. Not verified from code here: confirm with one real
Google and one Microsoft sign-in after deploying.

## 6. Azure Blob CORS

Allow origin `https://learnhub.abcsolutions.ai`, methods `GET, PUT, HEAD`, headers `*`, so browser uploads with
signed URLs work.

## 7. Processes

- Web: gunicorn / the host's Python app runner, `config.wsgi`.
- Worker: `celery -A config worker` (emails, badges, Stripe follow-ups, compliance jobs).
- Scheduler: `celery -A config beat` (daily token expiry, reminders, renewals).
- Redis reachable from all three.

## 8. Static files and the single-page app

- Backend: `python manage.py collectstatic`.
- Frontend: `npx vite build`; upload `frontend/dist/`.
- LiteSpeed `.htaccess`: the single-page-app fallback from `docs/build-status.md` ("Settings still needed"),
  added after the rules that send `/api` and `/_allauth` to Django. Without it, direct links and refreshes 404.

## 9. After deploying

- Check `/api/docs` returns 404 (API docs are switched off when `DEBUG` is off); log in as staff and open the console.
- Buy a token pack with a Stripe test card and check the wallet credits (proves the webhook).
- Upload a short video in the studio and check it plays (proves Bunny + the webhook).
- Send yourself a password reset (proves Graph mail and `FRONTEND_URL`).
