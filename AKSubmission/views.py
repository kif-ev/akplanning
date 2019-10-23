from django.contrib import messages
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView

from AKModel.models import AK, AKCategory, AKTag, AKOwner
from AKModel.models import Event
from AKModel.views import EventSlugMixin
from AKModel.views import FilterByEventSlugMixin

from AKSubmission.forms import AKForm, AKWishForm, AKOwnerForm

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


class AKSubmissionView(EventSlugMixin, CreateView):
    model = AK
    template_name = 'AKSubmission/submit_new.html'
    form_class = AKForm

    def get_initial(self):
        initials = super(AKSubmissionView, self).get_initial()
        initials['owners'] = [AKOwner.get_by_slug(self.kwargs['owner_slug'])]
        return initials

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


class AKWishSubmissionView(AKSubmissionView):
    template_name = 'AKSubmission/submit_new_wish.html'
    form_class = AKWishForm


class AKOwnerSelectCreateView(EventSlugMixin, CreateView):
    model = AKOwner
    template_name = 'AKSubmission/akowner_create_select.html'
    form_class = AKOwnerForm

    def get_success_url(self):
        return reverse_lazy('submit:submit_ak',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'owner_slug': self.object.slug})

    def form_valid(self, form):
        instance = form.save(commit=False)

        # Set event
        instance.event = Event.get_by_slug(self.kwargs["event_slug"])

        return super().form_valid(form)
