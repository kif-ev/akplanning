# Generated by Django 4.1.5 on 2023-03-21 23:21

from django.db import migrations



class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('AKOnline', '0003_rework_virtual_2'),
    ]

    def copy_rooms(apps, schema_editor):
        VirtualRoomOld = apps.get_model('AKOnline', 'VirtualRoomOld')
        VirtualRoom = apps.get_model('AKOnline', 'VirtualRoom')
        for row in VirtualRoomOld.objects.all():
            v = VirtualRoom(room_id=row.pk, url=row.url)
            v.save()

    operations = [
        migrations.RunPython(
            copy_rooms,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        )
    ]
