"""RLS for program seats (M22): a company sees only its own orders, seats, swaps and events;
the provider reads them in the console (staff). Composite foreign keys make the database
refuse a link between two companies' rows."""

from django.db import migrations

from core import rls

TABLES = (
    "program_seat_orders",
    "program_seat_lines",
    "program_seat_allocations",
    "seat_swap_requests",
    "program_seat_events",
)


class Migration(migrations.Migration):
    dependencies = [
        ("corporate", "0017_program_seats"),
    ]

    operations = [
        *[migrations.RunSQL(*rls.company_only("corporate", t)) for t in TABLES],
        migrations.RunSQL(*rls.composite_fk("corporate", "program_seat_lines", ("org_id", "order_id"),
                                            "corporate", "program_seat_orders", ("org_id", "id"), "fk_psl_order_org")),
        migrations.RunSQL(*rls.composite_fk("corporate", "program_seat_allocations", ("org_id", "line_id"),
                                            "corporate", "program_seat_lines", ("org_id", "id"), "fk_psa_line_org")),
        migrations.RunSQL(*rls.composite_fk("corporate", "program_seat_allocations", ("org_id", "member_id"),
                                            "org", "org_members", ("org_id", "id"), "fk_psa_member_org")),
        migrations.RunSQL(*rls.composite_fk("corporate", "program_seat_allocations", ("org_id", "enrollment_id"),
                                            "learning", "enrollments", ("org_id", "id"), "fk_psa_enrol_org")),
        migrations.RunSQL(*rls.composite_fk("corporate", "seat_swap_requests", ("org_id", "allocation_id"),
                                            "corporate", "program_seat_allocations", ("org_id", "id"), "fk_swap_alloc_org")),
        migrations.RunSQL(*rls.composite_fk("corporate", "seat_swap_requests", ("org_id", "to_member_id"),
                                            "org", "org_members", ("org_id", "id"), "fk_swap_member_org")),
    ]  # fmt: skip
