# Testing and validation

## Preparation checks completed

- Captured source at the recorded commit.
- Checked archive paths, symlinks, and file inclusion rules.
- Replaced detected credential literals, connection strings, and contact addresses with placeholders.
- Removed data exports, runtime environments, private keys, generated output, and internal assistant artifacts.
- Re-scanned the prepared text for the supported sensitive-value patterns.
- Parsed generated JSON documents and package manifests.

## Application validation

Dependencies were not installed. Application tests, servers, migrations, seeders, and database or external-service requests were not run. Runtime correctness after configuration and data removal remains to be verified by the project maintainer.

## Existing test sources

- `backend/apps/catalog/tests/test_catalog.py`
- `backend/apps/catalog/tests/test_token_pricing_columns.py`
- `backend/apps/commerce/tests/test_commerce.py`
- `backend/apps/commerce/tests/test_course_access_enrol.py`
- `backend/apps/commerce/tests/test_packages.py`
- `backend/apps/commerce/tests/test_program_buying.py`
- `backend/apps/commerce/tests/test_subscriptions.py`
- `backend/apps/commerce/tests/test_token_pricing.py`
- `backend/apps/commerce/tests/test_token_topups.py`
- `backend/apps/commerce/tests/test_unlock.py`
- `backend/apps/commerce/tests/test_wallet.py`
- `backend/apps/compliance/tests/test_compliance.py`
- `backend/apps/corporate/tests/test_cancellations.py`
- `backend/apps/corporate/tests/test_checkout.py`
- `backend/apps/corporate/tests/test_company_http.py`
- `backend/apps/corporate/tests/test_live_cohort.py`
- `backend/apps/corporate/tests/test_program_seats.py`
- `backend/apps/corporate/tests/test_programme.py`
- `backend/apps/corporate/tests/test_rls_isolation.py`
- `backend/apps/corporate/tests/test_seat_ledger.py`
- `backend/apps/corporate/tests/test_zoom_attendance.py`
- `backend/apps/delivery/tests/test_calendar.py`
- `backend/apps/delivery/tests/test_live.py`
- `backend/apps/delivery/tests/test_programs.py`
- `backend/apps/delivery/tests/test_records.py`
- `backend/apps/delivery/tests/test_seed_programs.py`
- `backend/apps/engagement/tests/test_engagement.py`
- `backend/apps/inclusion/tests/test_inclusion.py`
- `backend/apps/integrations/tests/test_api.py`
- `backend/apps/integrations/tests/test_breathe_client.py`
- `backend/apps/integrations/tests/test_fixtures.py`
- `backend/apps/integrations/tests/test_secrets.py`
- `backend/apps/integrations/tests/test_sync.py`
- `backend/apps/learning/tests/test_learning.py`
- `backend/apps/payouts/tests/test_payouts.py`
- `backend/apps/payouts/tests/test_token_earnings.py`
- `backend/apps/platform/tests/test_access_resolver.py`
- `backend/apps/platform/tests/test_console_token_pricing.py`
- `backend/apps/platform/tests/test_platform.py`
- `backend/core/test_runner.py`
- `backend/core/tests/test_api_business.py`
- `backend/core/tests/test_api_console.py`
- `backend/core/tests/test_api_contract.py`
- `backend/core/tests/test_api_learner.py`
- `backend/core/tests/test_api_studio.py`
- `backend/core/tests/test_console_access.py`
- `backend/core/tests/test_console_approvals.py`
- `backend/core/tests/test_console_audit.py`
- `backend/core/tests/test_console_certificates.py`
- `backend/core/tests/test_console_commissions.py`
- `backend/core/tests/test_console_comms.py`
- `backend/core/tests/test_console_companies.py`
- `backend/core/tests/test_console_courses.py`
- `backend/core/tests/test_console_dashboard.py`
- `backend/core/tests/test_console_moderation.py`
- `backend/core/tests/test_console_packages.py`
- `backend/core/tests/test_console_payouts.py`
- `backend/core/tests/test_console_people.py`
- `backend/core/tests/test_console_pricing.py`
- `backend/core/tests/test_console_promotions.py`
- `backend/core/tests/test_console_reports.py`
- `backend/core/tests/test_console_sales.py`
- `backend/core/tests/test_console_settings.py`
- `backend/core/tests/test_console_subscriptions.py`
- `backend/core/tests/test_default_currency.py`
- `backend/core/tests/test_html.py`
- `backend/core/tests/test_integrations.py`
- `backend/core/tests/test_m1_marketplace.py`
- `backend/core/tests/test_mfa_qr.py`
- `backend/core/tests/test_password_reset.py`
- `backend/core/tests/test_query_budgets.py`
- `backend/core/tests/test_resources.py`
- `backend/core/tests/test_rls.py`
- `backend/core/tests/test_rls_isolation.py`
- `backend/core/tests/test_seed_console_demo.py`
- `backend/core/tests/test_submission_files.py`
- `backend/core/tests/test_tenancy.py`
- `tools/harness/tester_accounts.py`
- `tools/harness/tester_shots.js`
