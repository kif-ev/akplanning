# Generated by Django 2.2.6 on 2019-10-25 12:38

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0021_base_url'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='akowner',
            name='email',
        ),
    ]
