from django.db import migrations


def populate_ak_from_slot(apps, schema_editor):
    for obj in apps.get_model("AKModel", "AKPreference").objects.all():
        if not obj.ak:
            obj.ak = obj.slot.ak
        obj.save(update_fields=['ak'])


class Migration(migrations.Migration):

    dependencies = [
        ("AKModel", "0071_akpreference_ak"),
    ]

    operations = [
        migrations.RunPython(
            populate_ak_from_slot,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
