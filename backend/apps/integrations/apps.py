from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    label = "integrations"
    verbose_name = "HR system"

    def ready(self) -> None:
        # Listen to org instead of org importing us (dependencies point up): when an invited
        # Breathe employee accepts, their row turns from "invited" to "linked".
        from apps.org.signals import structure_changed

        from .tasks import hr_reconcile_task

        def on_structure_changed(sender, *, org_id, member_ids=None, **_):
            if member_ids:
                hr_reconcile_task.delay(str(org_id), [str(m) for m in member_ids])

        structure_changed.connect(on_structure_changed, dispatch_uid="integrations.structure_changed")
