# Generated by Django 4.1.5 on 2023-03-21 23:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('AKModel', '0057_upgrades'),
        ('AKOnline', '0001_AKOnline'),
    ]

    operations = [
        migrations.RenameModel(
            'VirtualRoom',
            'VirtualRoomOld'
        ),

    ]
