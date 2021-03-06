# Generated by Django 3.0.6 on 2020-09-28 21:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('AKModel', '0037_event_public'),
    ]

    operations = [
        migrations.CreateModel(
            name='AKOrgaMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(help_text='Message to the organizers. This is not publicly visible.', verbose_name='Message text')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('ak', models.ForeignKey(help_text='AK this message belongs to', on_delete=django.db.models.deletion.CASCADE, to='AKModel.AK', verbose_name='AK')),
            ],
            options={
                'verbose_name': 'AK Orga Message',
                'verbose_name_plural': 'AK Orga Messages',
                'ordering': ['-timestamp'],
            },
        ),
    ]
