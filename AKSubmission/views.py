from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, RedirectView

from AKModel.availability.models import Availability
from AKModel.models import AK, AKCategory, AKTag, AKOwner, AKSlot, AKTrack
from AKModel.views import EventSlugMixin
from AKModel.views import FilterByEventSlugMixin
from AKSubmission.forms import AKWishForm, AKOwnerForm, AKEditForm, AKSubmissionForm, AKDurationForm


class AKOverviewView(FilterByEventSlugMixin, ListView):
    model = AKCategory
    context_object_name = "categories"
    template_name = "AKSubmission/ak_overview.html"
    wishes_as_category = False

    def filter_aks(self, context, category):
        return category.ak_set.all()

    def get_active_category_name(self, context):
        return context["categories_with_aks"][0][0].name

    def get_table_title(self, context):
        return _("All AKs")

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # Sort AKs into different lists (by their category)
        ak_wishes = []
        categories_with_aks = []

        for category in context["categories"]:
            aks_for_category = []
            for ak in self.filter_aks(context, category):
                if self.wishes_as_category and ak.wish:
                    ak_wishes.append(ak)
                else:
                    aks_for_category.append(ak)
            categories_with_aks.append((category, aks_for_category))

        if self.wishes_as_category:
            categories_with_aks.append(
                ({"name": _("Wishes"), "pk": "wish", "description": _("AKs one would like to have")}, ak_wishes))

        context["categories_with_aks"] = categories_with_aks
        context["active_category"] = self.get_active_category_name(context)
        context['table_title'] = self.get_table_title(context)

        return context


class SubmissionOverviewView(AKOverviewView):
    model = AKCategory
    context_object_name = "categories"
    template_name = "AKSubmission/submission_overview.html"
    wishes_as_category = settings.WISHES_AS_CATEGORY

    def get_table_title(self, context):
        return _("Currently planned AKs")

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # Get list of existing owners for event (for AK submission start)
        context["existingOwners"] = AKOwner.objects.filter(event=self.event)

        return context


class AKListByCategoryView(AKOverviewView):
    def dispatch(self, request, *args, **kwargs):
        self.category = get_object_or_404(AKCategory, pk=kwargs['category_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_active_category_name(self, context):
        return self.category.name


class AKListByTagView(AKOverviewView):
    def dispatch(self, request, *args, **kwargs):
        self.tag = get_object_or_404(AKTag, pk=kwargs['tag_pk'])
        return super().dispatch(request, *args, **kwargs)

    def filter_aks(self, context, category):
        return self.tag.ak_set.filter(event=self.event, category=category)

    def get_table_title(self, context):
        return f"{_('AKs with Tag')} = {self.tag.name}"


class AKListByTrackView(AKOverviewView):
    def dispatch(self, request, *args, **kwargs):
        self.track = get_object_or_404(AKTrack, pk=kwargs['track_pk'])
        return super().dispatch(request, *args, **kwargs)

    def filter_aks(self, context, category):
        return category.ak_set.filter(track=self.track)

    def get_table_title(self, context):
        return f"{_('AKs with Track')} = {self.track.name}"


class AKDetailView(EventSlugMixin, DetailView):
    model = AK
    context_object_name = "ak"
    template_name = "AKSubmission/ak_detail.html"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["availabilities"] = Availability.objects.filter(ak=context["ak"])
        return context


class AKHistoryView(EventSlugMixin, DetailView):
    model = AK
    context_object_name = "ak"
    template_name = "AKSubmission/ak_history.html"


class AKListView(FilterByEventSlugMixin, ListView):
    model = AK
    context_object_name = "AKs"
    template_name = "AKSubmission/ak_overview.html"
    table_title = ""

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['categories'] = AKCategory.objects.filter(event=self.event)
        context['tracks'] = AKTrack.objects.filter(event=self.event)
        return context


class EventInactiveRedirectMixin:
    def get_error_message(self):
        return _("Event inactive. Cannot create or update.")

    def get(self, request, *args, **kwargs):
        s = super().get(request, *args, **kwargs)
        if not self.event.active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview', kwargs={'event_slug': self.event.slug}))
        return s


class AKAndAKWishSubmissionView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    model = AK
    template_name = 'AKSubmission/submit_new.html'
    form_class = AKSubmissionForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully created"))
        return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.pk})

    def form_valid(self, form):
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))

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
        initials['owners'] = [AKOwner.get_by_slug(self.event, self.kwargs['owner_slug'])]
        initials['event'] = self.event
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['owner'] = get_object_or_404(AKOwner, event=self.event, slug=self.kwargs['owner_slug'])
        return context


class AKWishSubmissionView(AKAndAKWishSubmissionView):
    template_name = 'AKSubmission/submit_new_wish.html'
    form_class = AKWishForm

    def get_initial(self):
        initials = super(AKAndAKWishSubmissionView, self).get_initial()
        initials['event'] = self.event
        return initials


class AKEditView(EventSlugMixin, EventInactiveRedirectMixin, UpdateView):
    model = AK
    template_name = 'AKSubmission/ak_edit.html'
    form_class = AKEditForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully updated"))
        return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.pk})

    def form_valid(self, form):
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))

        super_form_valid = super().form_valid(form)

        # Detach existing tags
        self.object.tags.clear()

        # Set tags (and generate them if necessary)
        for tag_name in form.cleaned_data["tag_names"]:
            tag, _ = AKTag.objects.get_or_create(name=tag_name)
            self.object.tags.add(tag)

        return super_form_valid


class AKInterestView(RedirectView):
    permanent = False
    pattern_name = 'submit:ak_detail'

    def get_redirect_url(self, *args, **kwargs):
        ak = get_object_or_404(AK, pk=kwargs['pk'])
        if ak.event.active:
            ak.increment_interest()
        return super().get_redirect_url(*args, **kwargs)


class AKOwnerCreateView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    model = AKOwner
    template_name = 'AKSubmission/akowner_create_update.html'
    form_class = AKOwnerForm

    def get_success_url(self):
        return reverse_lazy('submit:submit_ak',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'owner_slug': self.object.slug})

    def get_initial(self):
        initials = super(AKOwnerCreateView, self).get_initial()
        initials['event'] = self.event
        return initials

    def form_valid(self, form):
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))
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


class AKOwnerEditView(FilterByEventSlugMixin, EventSlugMixin, UpdateView):
    model = AKOwner
    template_name = "AKSubmission/akowner_create_update.html"
    form_class = AKOwnerForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("Person Info successfully updated"))
        return reverse_lazy('submit:submission_overview', kwargs={'event_slug': self.kwargs['event_slug']})

    def form_valid(self, form):
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))
        return super().form_valid(form)


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


class AKSlotAddView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    model = AKSlot
    form_class = AKDurationForm
    template_name = "AKSubmission/akslot_add_update.html"

    def get_initial(self):
        initials = super(AKSlotAddView, self).get_initial()
        initials['event'] = self.event
        initials['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully added"))
        return reverse_lazy('submit:ak_detail',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.ak.pk})


class AKSlotEditView(EventSlugMixin, EventInactiveRedirectMixin, UpdateView):
    model = AKSlot
    form_class = AKDurationForm
    template_name = "AKSubmission/akslot_add_update.html"

    def get(self, request, *args, **kwargs):
        akslot = get_object_or_404(AKSlot, pk=kwargs["pk"])
        if akslot.start is not None:
            messages.add_message(self.request, messages.WARNING,
                                 _("You cannot edit a slot that has already been scheduled"))
            return redirect('submit:ak_detail', event_slug=self.kwargs['event_slug'], pk=akslot.ak.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = self.object.ak
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully updated"))
        return reverse_lazy('submit:ak_detail',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.ak.pk})


class AKSlotDeleteView(EventSlugMixin, EventInactiveRedirectMixin, DeleteView):
    model = AKSlot
    template_name = "AKSubmission/akslot_delete.html"

    def get(self, request, *args, **kwargs):
        akslot = get_object_or_404(AKSlot, pk=kwargs["pk"])
        if akslot.start is not None:
            messages.add_message(self.request, messages.WARNING,
                                 _("You cannot delete a slot that has already been scheduled"))
            return redirect('submit:ak_detail', event_slug=self.kwargs['event_slug'], pk=akslot.ak.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = self.object.ak
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully deleted"))
        return reverse_lazy('submit:ak_detail',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'pk': self.object.ak.pk})
