# Generated by Django 2.2.6 on 2019-10-16 18:41


from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('AKModel', '0008_akmodel_reuired_attributes'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='slug',
            field=models.SlugField(help_text='Short name of letters/numbers/dots/dashes/underscores used in URLs.',
                                   max_length=32, null=True, verbose_name='Short Form'),
        ),
    ]
