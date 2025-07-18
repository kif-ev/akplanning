# Generated by Django 3.2.16 on 2022-10-15 10:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AKModel', '0052_history_upgrade'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='plan_published_at',
            field=models.DateTimeField(blank=True, help_text='Timestamp at which the plan was published', null=True, verbose_name='Plan published at'),
        ),
    ]
