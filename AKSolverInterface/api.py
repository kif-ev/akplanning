from rest_framework import permissions, viewsets
from rest_framework.response import Response

from AKModel.models import Event
from AKSolverInterface.serializers import ExportEventSerializer


class ExportEventForSolverView(viewsets.GenericViewSet):
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
    # only allow exporting of active events
    queryset = Event.objects.filter(active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # pass event to serializer
        context["event"] = self.get_object()
        return context

    # rename view name to avoid 'List' suffix
    def get_view_name(self):
        return "JSON-Export for scheduling solver"

    # somewhat hacky solution: TODO: FIXME
    def list(self, request, *args, **kwargs):
        """Construct HTTP response showing serialized event export."""
        #   Below is the code of mixins.RetrieveModelMixin::retrieve
        #   which would usually be used to serve this detail API page.
        #   However, we do not specify the event to serve at the end of the URL
        #   but instead prepend the URL with it, i.e.
        #   `<slug>/api/<export_endpoint>` instead of the usual `api/<export_endpoint>/<slug>`.
        #   To make this work with the DefaultRouter, we serve this page as a list instead
        #   of a detail page. Hence, we use the method `list` instead of `retrieve`.
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
