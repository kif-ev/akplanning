# Generated by Django 2.2.6 on 2019-10-24 19:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AKModel', '0019_slot_start_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ak',
            name='name',
            field=models.CharField(help_text='Name of the AK', max_length=256, verbose_name='Name'),
        ),
        migrations.AlterField(
            model_name='ak',
            name='short_name',
            field=models.CharField(blank=True, help_text='Name displayed in the schedule', max_length=64, verbose_name='Short Name'),
        ),
        migrations.AlterUniqueTogether(
            name='ak',
            unique_together={('short_name', 'event'), ('name', 'event')},
        ),
    ]
