"""Links the existing sign-ins (sessions without a device) to Device rows -- one per user + browser/OS -- so
Identity -> Devices lists every phone/computer customers have used, not only app installs."""
from django.db import migrations


def forwards(apps, schema_editor):
    from apps.identity.infrastructure.repositories import device_label

    Session = apps.get_model("identity", "UserSession")
    Device = apps.get_model("identity", "Device")
    cache: dict = {}
    for s in Session.objects.filter(device__isnull=True).order_by("created_at").only("id", "user_id", "device_type", "device_name", "user_agent").iterator():
        key = (s.user_id, s.device_type, device_label(s.device_name, s.user_agent))
        if key not in cache:
            found = Device.objects.filter(user_id=key[0], device_type=key[1], device_name=key[2]).order_by("created_at").first()
            cache[key] = found.id if found else Device.objects.create(user_id=key[0], device_type=key[1], device_name=key[2]).id
        Session.objects.filter(pk=s.pk).update(device_id=cache[key])


class Migration(migrations.Migration):
    dependencies = [("identity", "0017_customer_role_for_roleless_users")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
