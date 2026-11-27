"""HARNESS ONLY: print the current maintenance-mode / guest-browsing settings, and turn
maintenance mode off if a previous crashed run left it stuck on (it would 503 every
non-staff request for every script, including other agents' concurrent runs)."""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()

from apps.platform.services import get_setting, set_setting  # noqa: E402
from apps.identity.models import User  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

with tenant_context(staff=True):
    maint = get_setting("access.maintenance_mode")
    guest = get_setting("access.guest_browsing")
    print("maintenance_mode:", maint)
    print("guest_browsing:", guest)
    if "--fix" in sys.argv and maint:
        staff = User.objects.filter(is_staff=True).first()
        set_setting(key="access.maintenance_mode", value=False, by=staff)
        print("maintenance_mode was ON: turned it back off")
