from django.views.generic import ListView

from AKModel.models import AK
from AKModel.views import FilterByEventSlugMixin


class SubmissionOverviewView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/submission_overview.html"
    ordering = ["type"]
