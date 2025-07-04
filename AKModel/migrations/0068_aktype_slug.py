# Generated by Django 5.1.6 on 2025-05-11 15:21

from django.db import migrations, models


def create_slugs(apps, schema_editor):
    """
    Automatically generate slugs from existing type names
    """
    AKType = apps.get_model("AKModel", "AKType")
    for ak_type in AKType.objects.all():
        slug = ak_type.name.lower().split(" ")[0]
        ak_type.slug = slug[:30] if len(slug) > 30 else slug
        ak_type.save()


class Migration(migrations.Migration):

    dependencies = [
        ('AKModel', '0067_eventparticipant_requirements_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='aktype',
            name='slug',
            field=models.SlugField(max_length=30, null=True, verbose_name='Slug'),
        ),
        migrations.RunPython(create_slugs, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='aktype',
            unique_together={('event', 'name')},
        ),
        migrations.AlterField(
            model_name='aktype',
            name='slug',
            field=models.SlugField(max_length=30, verbose_name='Slug'),
        ),
        migrations.AlterUniqueTogether(
            name='aktype',
            unique_together={('event', 'name'), ('event', 'slug')},
        ),
    ]
