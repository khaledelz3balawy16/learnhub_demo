"""HARNESS ONLY: top up a learner's personal token wallet directly (an admin adjustment
through the real wallet service), for demo/E2E steps that just need a balance to show.

    python e2e_grant_tokens.py <email> <amount>
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()
from apps.commerce import wallet  # noqa: E402
from apps.identity.models import User  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

email, amount = sys.argv[1], int(sys.argv[2])
staff = User.objects.filter(is_staff=True).first()
user = User.objects.get(email=email)
with tenant_context(staff=True):
    wallet.grant_tokens(user=user, source="admin", amount=amount, actor=staff, note="e2e harness top-up")
print("granted")
