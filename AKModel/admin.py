# Register your models here.

from django.contrib import admin

from AKModel.models import Event, AKOwner

admin.site.register(Event)
admin.site.register(AKOwner)
