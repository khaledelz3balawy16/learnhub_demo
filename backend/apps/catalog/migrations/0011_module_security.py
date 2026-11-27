"""M18: program modules get the same protection as sections: owner_org_id copied from the
version by trigger, readable like any content, written only by authoring services/staff."""

from django.db import migrations

from core import rls


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_course_kind_module_section_module_and_more")]

    operations = [
        migrations.RunSQL(*rls.inherit_owner("catalog", "modules", "catalog.course_versions", "version_id")),
        migrations.RunSQL(*rls.scoped_content("catalog", "modules")),
        migrations.RunSQL(*rls.scoped_content_authored("catalog", "modules")),
    ]
