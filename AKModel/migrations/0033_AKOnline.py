# Generated by Django 3.0.6 on 2020-05-17 20:02

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0032_AK_history'),
    ]

    operations = [
        migrations.RenameField(
            model_name='room',
            old_name='building',
            new_name='location',
        ),
    ]
