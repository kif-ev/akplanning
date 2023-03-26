from rest_framework import mixins, viewsets, permissions

from AKModel.metaviews.admin import EventSlugMixin
from AKModel.models import AKOwner, AKCategory, AKTrack, AK, Room, AKSlot
from AKModel.serializers import AKOwnerSerializer, AKCategorySerializer, AKTrackSerializer, AKSerializer, \
    RoomSerializer, AKSlotSerializer


class AKOwnerViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKOwnerSerializer

    def get_queryset(self):
        return AKOwner.objects.filter(event=self.event)


class AKCategoryViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKCategorySerializer

    def get_queryset(self):
        return AKCategory.objects.filter(event=self.event)


class AKTrackViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKTrackSerializer

    def get_queryset(self):
        return AKTrack.objects.filter(event=self.event)


class AKViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin,
                viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSerializer

    def get_queryset(self):
        return AK.objects.filter(event=self.event)


class RoomViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = RoomSerializer

    def get_queryset(self):
        return Room.objects.filter(event=self.event)


class AKSlotViewSet(EventSlugMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                    mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = AKSlotSerializer

    def get_queryset(self):
        return AKSlot.objects.filter(event=self.event)
