from django.contrib import messages
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView

from AKModel.models import AK, AKCategory, AKTag, Event
from AKModel.views import FilterByEventSlugMixin, EventSlugMixin
from AKSubmission.forms import AKForm


class SubmissionOverviewView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/submission_overview.html"
    ordering = ['category']


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


class AKSubmissionView(EventSlugMixin, CreateView):
    model = AK
    template_name = 'AKSubmission/submit_new.html'
    form_class = AKForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully created"))
        return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.pk})

    def form_valid(self, form):
        instance = form.save(commit=False)

        # Set event
        instance.event = Event.get_by_slug(self.kwargs["event_slug"])

        # Generate short name if not given
        # TODO

        # Generate wiki link
        # TODO

        # Generate slot(s)
        # TODO

        return super().form_valid(form)
