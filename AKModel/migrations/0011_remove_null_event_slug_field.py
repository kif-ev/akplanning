# Generated by Django 2.2.6 on 2019-10-16 18:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0010_populate_event_slug_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.SlugField(help_text='Short name of letters/numbers/dots/dashes/underscores used in URLs.',
                                   max_length=32, unique=True, verbose_name='Short Form'),
        ),

    ]
