from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView
from rest_framework import viewsets, mixins, serializers, permissions

from AKModel.availability.models import Availability
from AKModel.models import Room, AKSlot
from AKModel.views import EventSlugMixin


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'title']

    title = serializers.SerializerMethodField('transform_title')

    def transform_title(self, obj):
        if obj.capacity > 0:
            return f"{obj.title} [{obj.capacity}]"
        return obj.title


class ResourcesViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = ResourceSerializer

    def get_queryset(self):
        return Room.objects.filter(event=self.event)


class EventsView(LoginRequiredMixin, EventSlugMixin, ListView):
    model = AKSlot

    def get_queryset(self):
        return super().get_queryset().filter(event=self.event, room__isnull=False)

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(
            [{
                "slotID": slot.pk,
                "title": slot.ak.short_name,
                "description": slot.ak.name,
                "resourceId": slot.room.id,
                "start": timezone.localtime(slot.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(slot.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "backgroundColor": slot.ak.category.color,
                # TODO Mark conflicts here?
                "borderColor": slot.ak.category.color,
                "constraint": 'roomAvailable',
                'url': str(reverse('submit:ak_detail', kwargs={"event_slug": self.event.slug, "pk": slot.ak.pk})),
            } for slot in context["object_list"]],
            safe=False,
            **response_kwargs
        )


class RoomAvailabilitiesView(LoginRequiredMixin, EventSlugMixin, ListView):
    model = Availability
    context_object_name = "availabilities"

    def get_queryset(self):
        return super().get_queryset().filter(event=self.event, room__isnull=False)

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(
            [{
                "title": "",
                "resourceId": a.room.id,
                "start": timezone.localtime(a.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "end": timezone.localtime(a.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                "backgroundColor": "#28B62C",
                "display": 'background',
                "groupId": 'roomAvailable',
            } for a in context["availabilities"]],
            safe=False,
            **response_kwargs
        )


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AKSlot
        fields = ['id', 'start', 'end', 'roomId']

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    roomId = serializers.IntegerField(source='room.pk')

    def update(self, instance, validated_data):
        start = timezone.make_aware(timezone.make_naive(validated_data.get('start', instance.start)), instance.event.timezone)
        end = timezone.make_aware(timezone.make_naive(validated_data.get('end', instance.end)), instance.event.timezone)
        instance.start = start
        instance.room = get_object_or_404(Room, pk=validated_data.get('room')["pk"])
        diff = end - start
        instance.duration = round(diff.days * 24 + (diff.seconds / 3600), 2)
        instance.save()
        return instance


class EventsViewSet(EventSlugMixin, viewsets.ModelViewSet):
    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = EventSerializer

    def get_object(self):
        return get_object_or_404(AKSlot, pk=self.kwargs["pk"])

    def get_queryset(self):
        return AKSlot.objects.filter(event=self.event)
