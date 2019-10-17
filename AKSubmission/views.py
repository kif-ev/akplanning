from django.http import Http404
from django.views.generic import ListView, DetailView

from AKModel.models import AK, AKType, AKTag
from AKModel.views import FilterByEventSlugMixin

from django.utils.translation import gettext_lazy as _


class SubmissionOverviewView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/submission_overview.html"
    ordering = ["type"]


class AKDetailView(DetailView):
    model = AK
    context_object_name = "ak"
    template_name = "AKSubmission/ak_detail.html"


class AKListView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/ak_list.html"
    filter_condition_string = ""

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["types"] = AKType.objects.all()
        context["tags"] = AKTag.objects.all()
        context["filter_condition_string"] = self.filter_condition_string
        return context


class AKListByTypeView(AKListView):
    type = None

    def get_queryset(self):
        # Find type based on event slug
        try:
            self.type = AKType.objects.get(pk=self.kwargs['type_pk'])
            self.filter_condition_string = f"{_('Type')} = {self.type.name}"
        except AKType.DoesNotExist:
            raise Http404
        return super().get_queryset().filter(type=self.type)


class AKListByTagView(AKListView):
    tag = None

    def get_queryset(self):
        # Find type based on event slug
        try:
            self.tag = AKTag.objects.get(pk=self.kwargs['tag_pk'])
            self.filter_condition_string = f"{_('Tag')} = {self.tag.name}"
        except AKTag.DoesNotExist:
            raise Http404
        return super().get_queryset().filter(tags=self.tag)
