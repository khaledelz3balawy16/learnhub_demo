"""HARNESS ONLY: print the id of a user's most recent subscription (any status). The B2C
subscription checkout's fake Stripe URL carries no session/subscription id (CheckoutReviewPage
redirects straight to the success path), so the E2E script needs another way to find the
"incomplete" row it must deliver a webhook for.

    python e2e_last_subscription.py <email>   -> prints the subscription id
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()

from apps.commerce.models import Subscription  # noqa: E402
from apps.identity.models import User  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

email = sys.argv[1]
with tenant_context(staff=True):
    user = User.objects.get(email=email)
    sub = Subscription.objects.filter(user=user, org__isnull=True).order_by("-created_at").first()
    if sub is None:
        raise SystemExit(f"no subscription found for {email}")
    print(sub.id)
