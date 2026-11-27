"""M18: default provider staff roles (insert-only) and their RLS.

* Seeds Admin / Curriculum designer / Cohort manager / Tutor. The list is FROZEN here
  (not imported from core.staff_perms), so later code changes never change what a fresh
  database gets.
  A role that already exists by name is left exactly as the provider edited it.
* Gives the Admin role to every CURRENT staff user, so nobody loses access when the new
  program screens start checking permissions. Later staff get roles in the console.
* Both tables are reference data: any signed-in request may read them (permission checks
  run outside the console), only staff and jobs may write.
Seeding runs before RLS is switched on, so the migration never needs the staff key.
"""

from django.db import migrations

from core import rls

ALL = ["programs.build", "cohorts.manage", "groups.teach", "roles.manage", "reports.view"]
DEFAULT_ROLES = [
    ("Admin", "Everything, including staff roles.", ALL),
    ("Curriculum designer", "Builds programs and their content.", ["programs.build", "reports.view"]),
    ("Cohort manager", "Runs cohorts, groups and learner placement.", ["cohorts.manage", "reports.view"]),
    ("Tutor", "Teaches groups.", ["groups.teach"]),
]


def seed(apps, schema_editor):
    db = schema_editor.connection.alias
    StaffRole = apps.get_model("identity", "StaffRole")
    Assignment = apps.get_model("identity", "StaffRoleAssignment")
    User = apps.get_model("identity", "User")
    for name, description, perms in DEFAULT_ROLES:
        StaffRole.objects.using(db).get_or_create(
            name=name, defaults={"description": description, "permissions": perms, "is_system": True}
        )
    admin = StaffRole.objects.using(db).get(name="Admin")
    have = set(Assignment.objects.using(db).filter(role=admin).values_list("user_id", flat=True))
    Assignment.objects.using(db).bulk_create(
        Assignment(user_id=uid, role=admin)
        for uid in User.objects.using(db).filter(is_staff=True).values_list("id", flat=True)
        if uid not in have
    )


class Migration(migrations.Migration):
    dependencies = [("identity", "0005_staffrole_staffroleassignment")]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
        # The seeded assignments leave deferred foreign-key checks queued; Postgres refuses
        # ALTER TABLE on a table with queued checks, so run them now (a no-op when nothing was seeded).
        migrations.RunSQL("SET CONSTRAINTS ALL IMMEDIATE", migrations.RunSQL.noop),
        migrations.RunSQL(*rls.reference("identity", "staff_roles")),
        migrations.RunSQL(*rls.reference("identity", "staff_role_assignments")),
    ]
