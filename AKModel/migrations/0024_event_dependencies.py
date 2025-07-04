# Generated by Django 2.2.6 on 2019-10-25 13:44

import django.db.models.deletion
from django.db import migrations, models

from AKModel.models import AKCategory, Event, AKTrack


def migrate_data_forward(apps, schema_editor):
    for instance in AKCategory.objects.only('event').all():
        if not instance.event:
            instance.event = Event.objects.filter(active=True).last()
        instance.save()

    for instance in AKTrack.objects.only('event').all():
        if not instance.event:
            instance.event = Event.objects.filter(active=True).last()
        instance.save()


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0023_event_default_slot'),
    ]

    operations = [
        migrations.AddField(
            model_name='akcategory',
            name='event',
            field=models.ForeignKey(help_text='Associated event', null=True,
                                    on_delete=django.db.models.deletion.CASCADE, to='AKModel.Event',
                                    verbose_name='Event'),
        ),
        migrations.AddField(
            model_name='aktrack',
            name='event',
            field=models.ForeignKey(help_text='Associated event', null=True,
                                    on_delete=django.db.models.deletion.CASCADE, to='AKModel.Event',
                                    verbose_name='Event'),
        ),

        migrations.RunPython(
            migrate_data_forward,
            reverse_code=migrations.RunPython.noop,
        ),

        migrations.AlterField(
            model_name='akcategory',
            name='event',
            field=models.ForeignKey(help_text='Associated event',
                                    on_delete=django.db.models.deletion.CASCADE, to='AKModel.Event',
                                    verbose_name='Event'),
        ),
        migrations.AlterField(
            model_name='aktrack',
            name='event',
            field=models.ForeignKey(help_text='Associated event',
                                    on_delete=django.db.models.deletion.CASCADE, to='AKModel.Event',
                                    verbose_name='Event'),
        ),
    ]
