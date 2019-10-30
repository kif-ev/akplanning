from django.db.models import Q
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views import View
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from AKModel.availability.models import Availability
from AKModel.availability.serializers import AvailabilitySerializer
from AKModel.models import AK, Room, AKSlot
from AKScheduling.serializers import AKSerializer, RoomSerializer, AKSlotSerializer


class AKViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSerializer
    queryset = AK.objects.all()
    filter_fields = [f.name for f in AK._meta.get_fields()]
    search_fields = [f.name for f in AK._meta.get_fields()]
    ordering_fields = [f.name for f in AK._meta.get_fields()]


class RoomViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = RoomSerializer
    queryset = Room.objects.all()
    filter_fields = [f.name for f in Room._meta.get_fields()]
    search_fields = [f.name for f in Room._meta.get_fields()]
    ordering_fields = [f.name for f in Room._meta.get_fields()]


class AKSlotViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSlotSerializer
    queryset = AKSlot.objects.all()
    filter_fields = [f.name for f in AKSlot._meta.get_fields()]
    search_fields = [f.name for f in AKSlot._meta.get_fields()]
    ordering_fields = [f.name for f in AKSlot._meta.get_fields()]

    def get_queryset(self):
        queryset = AKSlot.objects.all()
        only_unscheduled = self.request.query_params.get('only_unscheduled', False)
        if only_unscheduled:
            queryset = queryset.filter(Q(room__isnull=True) | Q(start_time__isnull=True))
        return queryset

    @action(detail=True, methods=['post'])
    def check_constraints(self, request, pk=None):
        slot = self.get_object()
        ok, fail, reverse_fail = slot.check_constraints()
        return JsonResponse({'success': True, 'constraints': {'ok': ok, 'fail': fail, 'reverse_fail': reverse_fail}})


class AvailabilityViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    serializer_class = AvailabilitySerializer
    queryset = Availability.objects.all()
    filter_fields = [f.name for f in Availability._meta.get_fields()]
    search_fields = [f.name for f in Availability._meta.get_fields()]
    ordering_fields = [f.name for f in Availability._meta.get_fields()]


class AvailabilityApi(View):
    def get(self, request, *args, **kwargs):
        para = request.GET
        objs = Availability.objects.filter(start__range=[para['start'], para['end']])
        if 'room' in para:
            objs = objs.filter(room__id=para['room'], )
        qq = []
        for obj in objs:
            qq.append({'availability_id': obj.id,
                       'resource_id': obj.room,
                       'start': obj.start.astimezone().isoformat(),
                       'end': (obj.end).astimezone().isoformat(),
                       })
        objs = AKSlot.objects.select_related('ak').filter(start__range=[para['start'], para['end']])
        if 'room' in para:
            objs = objs.filter(room__id=para['room'], )
        for obj in objs:
            qq.append({'slot_id': obj.id,
                       'resource_id': obj.room_id,
                       'start': obj.start.astimezone().isoformat(),
                       'end': obj.end.astimezone().isoformat(),
                       })
        return JsonResponse({'events': qq, })

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm('AKModel.add_availability'):
            raise PermissionDenied
        para = request.POST
        room = Room.objects.get(id=para['room'])
        startdt = parse_datetime(para['start'])
        enddt = parse_datetime(para['end'])
        if 'event' in para:
            obj = Availability.objects.get(id=para['event'])
        else:
            obj = Availability.objects.create(room=room, status=1, start_time=startdt, end_time=enddt)
        obj.start_time = startdt
        obj.end_time = enddt
        obj.room = room

        obj.save()
        return JsonResponse({'success': 'true', 'id': obj.id})
