from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.models import AK, AKCategory, AKTag
from AKModel.views import FilterByEventSlugMixin
from django.conf import settings


class SubmissionOverviewView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/submission_overview.html"
    ordering = ['category']

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # Sort AKs into different lists (by their category)
        categories = []
        aks_for_category = []
        ak_wishes = []
        current_category = None
        for ak in context["AKs"]:
            if ak.category != current_category:
                current_category = ak.category
                aks_for_category = []
                categories.append((current_category, aks_for_category))
            if settings.WISHES_AS_CATEGORY and ak.wish:
                ak_wishes.append(ak)
            else:
                aks_for_category.append(ak)

        if settings.WISHES_AS_CATEGORY:
            categories.append(({"name":_("Wishes"), "pk": "wish", "description": _("AKs one would like to have")}, ak_wishes))
        context["categories"] = categories

        return context


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
        context['categories'] = AKCategory.objects.all()
        context["tags"] = AKTag.objects.all()
        context["filter_condition_string"] = self.filter_condition_string
        return context


class AKListByCategoryView(AKListView):
    category = None

    def get_queryset(self):
        # Find category based on event slug
        try:
            self.category = AKCategory.objects.get(pk=self.kwargs['category_pk'])
            self.filter_condition_string = f"{_('Category')} = {self.category.name}"
        except AKCategory.DoesNotExist:
            raise Http404
        return super().get_queryset().filter(category=self.category)


class AKListByTagView(AKListView):
    tag = None

    def get_queryset(self):
        # Find category based on event slug
        try:
            self.tag = AKTag.objects.get(pk=self.kwargs['tag_pk'])
            self.filter_condition_string = f"{_('Tag')} = {self.tag.name}"
        except AKTag.DoesNotExist:
            raise Http404
        return super().get_queryset().filter(tags=self.tag)
