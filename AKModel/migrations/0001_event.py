# Generated by Django 2.2.6 on 2019-10-11 16:58

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Name or iteration of the event', max_length=64, unique=True, verbose_name='Name')),
                ('start', models.DateTimeField(help_text='Time the event begins', verbose_name='Start')),
                ('end', models.DateTimeField(help_text='Time the event ends', verbose_name='End')),
                ('place', models.CharField(help_text='City etc. where the event takes place', max_length=128, verbose_name='Place')),
                ('active', models.BooleanField(help_text='Marks currently active events', verbose_name='Active State')),
            ],
        ),
    ]
