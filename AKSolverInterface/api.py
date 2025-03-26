from rest_framework import generics, permissions

from AKModel.models import Event
from AKSolverInterface.serializers import ExportEventSerializer


class ExportEventForSolverView(generics.RetrieveAPIView):
    """
    API View: Current event, formatted to be consumed by a solver.
    Read-only

    Follows the format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format
    """

    permission_classes = (permissions.DjangoModelPermissions,)
    serializer_class = ExportEventSerializer
    lookup_url_kwarg = "event_slug"
    lookup_field = "slug"
    queryset = Event.objects.filter(active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["event"] = self.get_object()
        return context
