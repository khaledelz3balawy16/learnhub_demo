"""Row-Level Security and cross-company integrity for the integrations schema (M17).

Every table is company_only(). Composite foreign keys (org_id, x_id) -> (org_id, id) make
the database itself refuse a link to another company's connection, member, unit, person
or requirement. Two links stay plain foreign keys because their parent tables have no
UNIQUE (org_id, id) to point at: external_people.invite_id (org.invites) and
external_training_records.applied_record_id (compliance.completion_records). Both are
only ever set by services that load the parent inside the same company's RLS context.
"""

from django.db import migrations

from core import rls

S = "integrations"
TABLES = (
    "hr_connections", "external_people", "external_departments", "hr_training_maps",
    "external_training_records", "external_leave", "hr_sync_runs",
)  # fmt: skip

POLICIES = [rls.company_only(S, t) for t in TABLES]


def _conn_fk(table: str, short: str):
    return rls.composite_fk(S, table, ("org_id", "connection_id"), S, "hr_connections", ("org_id", "id"),
                            f"fk_{short}_conn_same_org", "CASCADE")  # fmt: skip


COMPOSITE_FKS = [
    *(_conn_fk(t, s) for t, s in (
        ("external_people", "hrp"), ("external_departments", "hrd"), ("hr_training_maps", "hrm"),
        ("external_training_records", "hrt"), ("external_leave", "hrl"), ("hr_sync_runs", "hrr"),
    )),  # fmt: skip
    rls.composite_fk(S, "external_people", ("org_id", "member_id"), "org", "org_members", ("org_id", "id"),
                     "fk_hrp_member_same_org", "SET NULL (member_id)"),
    rls.composite_fk(S, "external_departments", ("org_id", "unit_id"), "org", "org_units", ("org_id", "id"),
                     "fk_hrd_unit_same_org", "SET NULL (unit_id)"),
    rls.composite_fk(S, "hr_training_maps", ("org_id", "requirement_id"), "compliance", "requirements",
                     ("org_id", "id"), "fk_hrm_req_same_org"),
    rls.composite_fk(S, "external_training_records", ("org_id", "person_id"), S, "external_people",
                     ("org_id", "id"), "fk_hrt_person_same_org", "SET NULL (person_id)"),
    rls.composite_fk(S, "external_leave", ("org_id", "person_id"), S, "external_people", ("org_id", "id"),
                     "fk_hrl_person_same_org", "CASCADE"),
]  # fmt: skip


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_initial")]

    operations = [migrations.RunSQL(fwd, rev) for fwd, rev in (*POLICIES, *COMPOSITE_FKS)]
