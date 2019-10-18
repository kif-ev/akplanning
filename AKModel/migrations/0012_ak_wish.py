# Generated by Django 2.2.6 on 2019-10-18 09:00

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0011_remove_null_event_slug_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ak',
            name='owners',
            field=models.ManyToManyField(blank=True, help_text='Those organizing the AK', to='AKModel.AKOwner',
                                         verbose_name='Owners'),
        ),
    ]
