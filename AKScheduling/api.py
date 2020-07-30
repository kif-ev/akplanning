from rest_framework import viewsets, permissions, mixins, serializers

from AKModel.models import Room
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
