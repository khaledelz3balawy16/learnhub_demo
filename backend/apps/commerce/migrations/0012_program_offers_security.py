"""M21 RLS (additive): program offers are reference data (read by all, staff write); an
instalment plan and its payments belong to the order's buyer (org_id + user_id copied
from the parent by trigger, mixed policy), like order items and payments."""

from django.db import migrations

from core import rls

S = "commerce"
INHERIT = [
    ("instalment_plans", "commerce.orders", "order_id"),
    ("instalment_payments", "commerce.instalment_plans", "plan_id"),
]


class Migration(migrations.Migration):
    dependencies = [("commerce", "0011_program_offers")]

    operations = [
        migrations.RunSQL(*rls.reference(S, "program_offers")),
        *(migrations.RunSQL(*rls.inherit_parent(S, t, parent, fk)) for t, parent, fk in INHERIT),
        *(migrations.RunSQL(*rls.mixed(S, t)) for t, _, _ in INHERIT),
    ]
