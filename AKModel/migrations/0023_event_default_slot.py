# Generated by Django 2.2.6 on 2019-10-25 13:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0022_remove_akowner_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='default_slot',
            field=models.DecimalField(decimal_places=2, default=2,
                                      help_text='Default length in hours that is assumed for AKs in this event.',
                                      max_digits=4, verbose_name='Default Slot Length'),
        ),
    ]