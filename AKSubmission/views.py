from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from AKModel.models import AK, AKCategory, AKTag, AKOwner, AKSlot
from AKModel.models import Event
from AKModel.views import EventSlugMixin
from AKModel.views import FilterByEventSlugMixin
from AKSubmission.forms import AKWishForm, AKOwnerForm, AKEditForm, AKSubmissionForm


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
            categories.append(
                ({"name": _("Wishes"), "pk": "wish", "description": _("AKs one would like to have")}, ak_wishes))
        context["categories"] = categories

        # Get list of existing owners for event (for AK submission start)
        context["existingOwners"] = AKOwner.objects.filter(event=self.event)

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


class AKAndAKWishSubmissionView(EventSlugMixin, CreateView):
    model = AK
    template_name = 'AKSubmission/submit_new.html'
    form_class = AKSubmissionForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully created"))
        return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.pk})

    def form_valid(self, form):
        super_form_valid = super().form_valid(form)

        # Generate wiki link
        if form.cleaned_data["event"].base_url:
            self.object.link = form.cleaned_data["event"].base_url + form.cleaned_data["name"].replace(" ", "_")
        self.object.save()

        # Set tags (and generate them if necessary)
        for tag_name in form.cleaned_data["tag_names"]:
            tag, _ = AKTag.objects.get_or_create(name=tag_name)
            self.object.tags.add(tag)

        # Generate slot(s)
        for duration in form.cleaned_data["durations"]:
            new_slot = AKSlot(ak=self.object, duration=duration, event=self.object.event)
            new_slot.save()

        return super_form_valid


class AKSubmissionView(AKAndAKWishSubmissionView):
    def get_initial(self):
        initials = super(AKAndAKWishSubmissionView, self).get_initial()
        initials['owners'] = [AKOwner.get_by_slug(self.kwargs['owner_slug'])]
        initials['event'] = self.event
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['owner'] = get_object_or_404(AKOwner, slug=self.kwargs['owner_slug'])
        return context


class AKWishSubmissionView(AKAndAKWishSubmissionView):
    template_name = 'AKSubmission/submit_new_wish.html'
    form_class = AKWishForm

    def get_initial(self):
        initials = super(AKAndAKWishSubmissionView, self).get_initial()
        initials['event'] = self.event
        return initials


class AKEditView(EventSlugMixin, UpdateView):
    model = AK
    template_name = 'AKSubmission/ak_edit.html'
    form_class = AKEditForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully updated"))
        return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.pk})

    def form_valid(self, form):
        super_form_valid = super().form_valid(form)

        # Detach existing tags
        self.object.tags.clear()

        # Set tags (and generate them if necessary)
        for tag_name in form.cleaned_data["tag_names"]:
            tag, _ = AKTag.objects.get_or_create(name=tag_name)
            self.object.tags.add(tag)

        return super_form_valid


class AKOwnerCreateView(EventSlugMixin, CreateView):
    model = AKOwner
    template_name = 'AKSubmission/akowner_create_update.html'
    form_class = AKOwnerForm

    def get_success_url(self):
        return reverse_lazy('submit:submit_ak',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'owner_slug': self.object.slug})

    def form_valid(self, form):
        instance = form.save(commit=False)

        # Set event
        instance.event = Event.get_by_slug(self.kwargs["event_slug"])

        return super().form_valid(form)


class AKOwnerSelectDispatchView(EventSlugMixin, View):
    """
    This view only serves as redirect to prepopulate the owners field in submission create view
    """

    def post(self, request, *args, **kwargs):
        owner_id = request.POST["owner_id"]

        if owner_id == "-1":
            return HttpResponseRedirect(
                reverse_lazy('submit:akowner_create', kwargs={'event_slug': kwargs['event_slug']}))

        owner = get_object_or_404(AKOwner, pk=request.POST["owner_id"])
        return HttpResponseRedirect(
            reverse_lazy('submit:submit_ak', kwargs={'event_slug': kwargs['event_slug'], 'owner_slug': owner.slug}))


class AKOwnerEditView(EventSlugMixin, UpdateView):
    model = AKOwner
    template_name = "AKSubmission/akowner_create_update.html"
    form_class = AKOwnerForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("Person Info successfully updated"))
        return reverse_lazy('submit:submission_overview', kwargs={'event_slug': self.kwargs['event_slug']})


class AKOwnerEditDispatchView(EventSlugMixin, View):
    """
    This view only serves as redirect choose the correct edit view
    """

    def post(self, request, *args, **kwargs):
        owner_id = request.POST["owner_id"]

        if owner_id == "-1":
            messages.add_message(self.request, messages.WARNING, _("No user selected"))
            return HttpResponseRedirect(
                reverse_lazy('submit:submission_overview', kwargs={'event_slug': kwargs['event_slug']}))

        owner = get_object_or_404(AKOwner, pk=request.POST["owner_id"])
        return HttpResponseRedirect(
            reverse_lazy('submit:akowner_edit', kwargs={'event_slug': kwargs['event_slug'], 'slug': owner.slug}))
