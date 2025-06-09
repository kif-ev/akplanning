from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from math import floor

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from AKModel.availability.models import Availability
from AKModel.metaviews import status_manager
from AKModel.metaviews.admin import EventSlugMixin, FilterByEventSlugMixin
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.models import AK, AKCategory, AKOrgaMessage, AKOwner, AKSlot, AKTrack, AKType
from AKSubmission.api import ak_interest_indication_active
from AKSubmission.forms import AKDurationForm, AKForm, AKOrgaMessageForm, AKOwnerForm, AKSubmissionForm, AKWishForm


class SubmissionErrorNotConfiguredView(EventSlugMixin, TemplateView):
    """
    View to show when submission is not correctly configured yet for this event
    and hence the submission component cannot be used already.
    """
    template_name = "AKSubmission/submission_not_configured.html"


class AKOverviewView(FilterByEventSlugMixin, ListView):
    """
    View: Show a tabbed list of AKs belonging to this event split by categories

    Wishes show up in between of the other AKs in the category they belong to.
    In contrast to :class:`SubmissionOverviewView` that inherits from this view,
    on this view there is no form to add new AKs or edit owners.

    Since the inherited version of this view will have a slightly different behaviour,
    this view contains multiple methods that can be overriden for this adaption.
    """
    model = AKCategory
    context_object_name = "categories"
    template_name = "AKSubmission/ak_overview.html"
    wishes_as_category = False

    def filter_aks(self, context, category):  # pylint: disable=unused-argument
        """
        Filter which AKs to display based on the given context and category

        In the default case, all AKs of that category are returned (including wishes)

        :param context: context of the view
        :param category: category to filter the AK list for
        :return: filtered list of AKs for the given category
        :rtype: QuerySet[AK]
        """
        # Use prefetching and relation selection/joining to reduce the amount of necessary queries
        return category.ak_set.select_related('event').prefetch_related('owners').prefetch_related('types').all()

    def get_active_category_name(self, context):
        """
        Get the category name to display by default/before further user interaction

        In the default case, simply the first category (the one with the lowest ID for this event) is used

        :param context: context of the view
        :return: name of the default category
        :rtype: str
        """
        return context["categories_with_aks"][0][0].name

    def get_table_title(self, context):  # pylint: disable=unused-argument
        """
        Specify the title above the AK list/table in this view

        :param context: context of the view
        :return: title to use
        :rtype: str
        """
        return _("All AKs")

    def get(self, request, *args, **kwargs):
        """
        Handle GET request

        Overriden to allow checking for correct configuration and
        redirect to error page if necessary (see :class:`SubmissionErrorNotConfiguredView`)
        """
        self._load_event()
        self.object_list = self.get_queryset()  # pylint: disable=attribute-defined-outside-init

        # No categories yet? Redirect to configuration error page
        if self.object_list.count() == 0:
            return redirect(reverse_lazy("submit:error_not_configured", kwargs={'event_slug': self.event.slug}))

        context = self.get_context_data()
        return self.render_to_response(context)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # ==========================================================
        # Sort AKs into different lists (by their category)
        # ==========================================================
        ak_wishes = []
        categories_with_aks = []

        # Loop over categories, load AKs (while filtering them if necessary) and create a list of (category, aks)-tuples
        # Depending on the setting of self.wishes_as_category, wishes are either included
        # or added to a special "Wish"-Category that is created on-the-fly to provide consistent handling in the
        # template (without storing it in the database)
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
                    (AKCategory(name=_("Wishes"), pk=0, description=_("AKs one would like to have")), ak_wishes))

        context["categories_with_aks"] = categories_with_aks
        context["active_category"] = self.get_active_category_name(context)
        context['table_title'] = self.get_table_title(context)

        context['show_types'] = self.event.aktype_set.count() > 0

        # ==========================================================
        # Display interest indication button?
        # ==========================================================
        current_timestamp = datetime.now().astimezone(self.event.timezone)
        context['interest_indication_active'] = ak_interest_indication_active(self.event, current_timestamp)

        return context


class SubmissionOverviewView(AKOverviewView):
    """
    View: List of AKs and possibility to add AKs or adapt owner information

    Main/start view of the component.

    This view inherits from :class:`AKOverviewView`, but treats wishes as separate category if requested in the settings
    and handles the change actions mentioned above.
    """
    model = AKCategory
    context_object_name = "categories"
    template_name = "AKSubmission/submission_overview.html"

    # this mainly steers the different handling of wishes
    # since the code for that is already included in the parent class
    wishes_as_category = settings.WISHES_AS_CATEGORY

    def get_table_title(self, context):
        """
        Specify the title above the AK list/table in this view

        :param context: context of the view
        :return: title to use
        :rtype: str
        """
        return _("Currently planned AKs")

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # Get list of existing owners for event (for AK submission start)
        context["existingOwners"] = AKOwner.objects.filter(event=self.event)

        return context


class AKListByCategoryView(AKOverviewView):
    """
    View: List of only the AKs belonging to a certain category.

    This view inherits from :class:`AKOverviewView`, but produces only one list instead of a tabbed one.
    """

    def dispatch(self, request, *args, **kwargs):
        # Override dispatching
        # Needed to handle the checking whether the category exists
        # noinspection PyAttributeOutsideInit
        # pylint: disable=attribute-defined-outside-init
        self.category = get_object_or_404(AKCategory, pk=kwargs['category_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_active_category_name(self, context):
        """
        Get the category name to display by default/before further user interaction

        In this case, this will be the name of the category specified via pk

        :param context: context of the view
        :return: name of the category
        :rtype: str
        """
        return self.category.name


class AKListByTrackView(AKOverviewView):
    """
    View: List of only the AKs belonging to a certain track.

    This view inherits from :class:`AKOverviewView` and there will be one list per category
    -- but only AKs of a certain given track will be included in them.
    """

    def dispatch(self, request, *args, **kwargs):
        # Override dispatching
        # Needed to handle the checking whether the track exists

        self.track = get_object_or_404(AKTrack, pk=kwargs['track_pk'])  # pylint: disable=attribute-defined-outside-init
        return super().dispatch(request, *args, **kwargs)

    def filter_aks(self, context, category):
        """
        Filter which AKs to display based on the given context and category

        In this case, the list is further restricted by the track

        :param context: context of the view
        :param category: category to filter the AK list for
        :return: filtered list of AKs for the given category
        :rtype: QuerySet[AK]
        """
        return super().filter_aks(context, category).filter(track=self.track)

    def get_table_title(self, context):
        return f"{_('AKs with Track')} = {self.track.name}"


class AKListByTypeView(AKOverviewView):
    """
    View: List of only the AKs belonging to a certain type.

    This view inherits from :class:`AKOverviewView` and there will be one list per category
    -- but only AKs of a certain given type will be included in them.
    """

    def dispatch(self, request, *args, **kwargs):
        # Override dispatching
        # Needed to handle the checking whether the type exists

        self.type = get_object_or_404(AKType, slug=kwargs['type_slug'])  # pylint: disable=attribute-defined-outside-init
        return super().dispatch(request, *args, **kwargs)

    def filter_aks(self, context, category):
        """
        Filter which AKs to display based on the given context and category

        In this case, the list is further restricted by the type

        :param context: context of the view
        :param category: category to filter the AK list for
        :return: filtered list of AKs for the given category
        :rtype: QuerySet[AK]
        """
        return super().filter_aks(context, category).filter(types=self.type)

    def get_table_title(self, context):
        return f"{_('AKs with Type')} = {self.type.name}"


class AKDetailView(EventSlugMixin, DetailView):
    """
    View: AK Details
    """
    model = AK
    context_object_name = "ak"
    template_name = "AKSubmission/ak_detail.html"

    def get_queryset(self):
        # Get information about the AK and do some query optimization
        return super().get_queryset().select_related('event').prefetch_related('owners', 'akslot_set')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["availabilities"] = Availability.objects.filter(ak=context["ak"])

        current_timestamp = datetime.now().astimezone(self.event.timezone)

        # Is this AK taking place now or soon (used for top page visualization)
        context["featured_slot_type"] = "NONE"
        if apps.is_installed("AKPlan"):
            in_two_hours = current_timestamp + timedelta(hours=2)
            slots = context["ak"].akslot_set.filter(start__isnull=False, room__isnull=False).select_related('room')
            for slot in slots:
                if slot.end > current_timestamp:
                    if slot.start <= current_timestamp:
                        context["featured_slot_type"] = "CURRENT"
                        remaining = slot.end - current_timestamp
                    elif slot.start <= in_two_hours:
                        context["featured_slot_type"] = "UPCOMING"
                        remaining = slot.start - current_timestamp
                    else:
                        continue

                    context["featured_slot"] = slot
                    context["featured_slot_remaining"] = floor(remaining.days * 24 * 60 + remaining.seconds / 60)
                    break

        # Display interest indication button?
        context['interest_indication_active'] = ak_interest_indication_active(self.event, current_timestamp)

        return context


class AKHistoryView(EventSlugMixin, DetailView):
    """
    View: Show history of a given AK
    """
    model = AK
    context_object_name = "ak"
    template_name = "AKSubmission/ak_history.html"


class EventInactiveRedirectMixin:
    """
    Mixin that will cause a redirect when actions are performed on an inactive event.
    Will add a message explaining why the action was not performed to the user
    and then redirect to start page of the submission component
    """

    def get_error_message(self):
        """
        Error message to display after redirect (can be adjusted by this method)

        :return: error message
        :rtype: str
        """
        return _("Event inactive. Cannot create or update.")

    def get(self, request, *args, **kwargs):
        """
        Override GET request handling
        Will either perform the redirect including the message creation or continue with the planned dispatching
        """
        s = super().get(request, *args, **kwargs)
        if not self.event.active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview', kwargs={'event_slug': self.event.slug}))
        return s


class AKAndAKWishSubmissionView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    """
    View: Submission form for AKs and Wishes

    Base view, will be used by :class:`AKSubmissionView` and :class:`AKWishSubmissionView`
    """
    model = AK
    template_name = 'AKSubmission/submit_new.html'
    form_class = AKSubmissionForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully created"))
        return self.object.detail_url

    def form_valid(self, form):
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))

        # Try to save AK and get redirect URL
        super_form_valid = super().form_valid(form)

        # Generate slot(s) (but not for wishes)
        if "durations" in form.cleaned_data:
            for duration in form.cleaned_data["durations"]:
                new_slot = AKSlot(ak=self.object, duration=duration, event=self.object.event)
                new_slot.save()

        return super_form_valid


class AKSubmissionView(AKAndAKWishSubmissionView):
    """
    View: AK submission form

    Extends :class:`AKAndAKWishSubmissionView`
    """

    def get_initial(self):
        # Load initial values for the form
        # Used to directly add the first owner and the event this AK will belong to
        initials = super(AKAndAKWishSubmissionView, self).get_initial()
        initials['owners'] = [AKOwner.get_by_slug(self.event, self.kwargs['owner_slug'])]
        initials['event'] = self.event
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['owner'] = get_object_or_404(AKOwner, event=self.event, slug=self.kwargs['owner_slug'])
        return context


class AKWishSubmissionView(AKAndAKWishSubmissionView):
    """
    View: Wish submission form

    Extends :class:`AKAndAKWishSubmissionView`
    """
    template_name = 'AKSubmission/submit_new_wish.html'
    form_class = AKWishForm

    def get_initial(self):
        # Load initial values for the form
        # Used to directly select the event this AK will belong to
        initials = super(AKAndAKWishSubmissionView, self).get_initial()
        initials['event'] = self.event
        return initials


class AKEditView(EventSlugMixin, EventInactiveRedirectMixin, UpdateView):
    """
    View: Update an AK

    This allows to change most fields of an AK as specified in :class:`AKSubmission.forms.AKForm`,
    including the availabilities.
    It will also handle the change from AK to wish and vice versa (triggered by adding or removing owners)
    and automatically create or delete (unscheduled) slots
    """
    model = AK
    template_name = 'AKSubmission/ak_edit.html'
    form_class = AKForm

    def get_success_url(self):
        # Redirection after successfully saving to detail page of AK where also a success message is displayed
        messages.add_message(self.request, messages.SUCCESS, _("AK successfully updated"))
        return self.object.detail_url

    def form_valid(self, form):
        # Handle valid form submission

        # Only save when event is active, otherwise redirect
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))

        # Remember owner count before saving to know whether the AK changed its state between AK and wish
        previous_owner_count = self.object.owners.count()

        # Perform saving and redirect handling by calling default/parent implementation of form_valid
        redirect_response = super().form_valid(form)

        # Did this AK change from wish to AK or vice versa?
        new_owner_count = self.object.owners.count()
        # Now AK:
        if previous_owner_count == 0 and new_owner_count > 0 and self.object.akslot_set.count() == 0:
            # Create one slot with default length
            AKSlot.objects.create(ak=self.object, duration=self.object.event.default_slot, event=self.object.event)
        # Now wish:
        elif previous_owner_count > 0 and new_owner_count == 0:
            # Delete all unscheduled slots
            self.object.akslot_set.filter(start__isnull=True).delete()

        # Redirect to success url
        return redirect_response


class AKOwnerCreateView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    """
    View: Create a new owner
    """
    model = AKOwner
    template_name = 'AKSubmission/akowner_create_update.html'
    form_class = AKOwnerForm

    def get_success_url(self):
        # The redirect url depends on the source this view was called from:

        # Called from an existing AK? Add the new owner as an owner of that AK, notify the user and redirect to detail
        # page of that AK
        if "add_to_existing_ak" in self.request.GET:
            ak_pk = self.request.GET['add_to_existing_ak']
            ak = get_object_or_404(AK, pk=ak_pk)
            ak.owners.add(self.object)
            messages.add_message(self.request, messages.SUCCESS,
                                 _("Added '{owner}' as new owner of '{ak.name}'").format(owner=self.object, ak=ak))
            return ak.detail_url

        # Called from the submission overview? Offer the user to create a new AK with the recently created owner
        # prefilled as owner of that AK in the creation form
        return reverse_lazy('submit:submit_ak',
                            kwargs={'event_slug': self.kwargs['event_slug'], 'owner_slug': self.object.slug})

    def get_initial(self):
        # Set the event in the (hidden) event field in the form based on the URL this view was called with
        initials = super().get_initial()
        initials['event'] = self.event
        return initials

    def form_valid(self, form):
        # Prevent changes if event is not active
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))
        return super().form_valid(form)


class AKOwnerDispatchView(ABC, EventSlugMixin, View):
    """
    Base view: Dispatch to correct view based upon

    Will be used by :class:`AKOwnerSelectDispatchView` and :class:`AKOwnerEditDispatchView` to handle button clicks for
    "New AK" and "Edit Person Info" in submission overview based upon the selection in the owner dropdown field
    """

    @abstractmethod
    def get_new_owner_redirect(self, event_slug):
        """
        Get redirect when user selected "I do not own AKs yet"

        :param event_slug: slug of the event, needed for constructing redirect
        :return: redirect to perform
        :rtype: HttpResponseRedirect
        """

    @abstractmethod
    def get_valid_owner_redirect(self, event_slug, owner):
        """
        Get redirect when user selected "I do not own AKs yet"

        :param event_slug: slug of the event, needed for constructing redirect
        :param owner: owner to perform the dispatching for
        :return: redirect to perform
        :rtype: HttpResponseRedirect
        """

    def post(self, request, *args, **kwargs):
        # This view is solely meant to handle POST requests
        # Perform dispatching based on the submitted owner_id

        # No owner_id? Redirect to submission overview view
        if "owner_id" not in request.POST:
            return redirect('submit:submission_overview', event_slug=kwargs['event_slug'])
        owner_id = request.POST["owner_id"]

        # Special owner_id "-1" (value of "I do not own AKs yet)? Redirect to owner creation view
        if owner_id == "-1":
            return self.get_new_owner_redirect(kwargs['event_slug'])

        # Normal owner_id given? Check vor validity and redirect to AK submission page with that owner prefilled
        # or display a 404 error page if no owner for the given id can be found. The latter should only happen when the
        # user manipulated the value before sending or when the owner was deleted in backend and the user did not
        # reload the dropdown between deletion and sending the dispatch request
        owner = get_object_or_404(AKOwner, pk=request.POST["owner_id"])
        return self.get_valid_owner_redirect(kwargs['event_slug'], owner)

    def get(self, request, *args, **kwargs):
        # This view should never be called with GET, perform a redirect to overview in that case
        return redirect('submit:submission_overview', event_slug=kwargs['event_slug'])


class AKOwnerSelectDispatchView(AKOwnerDispatchView):
    """
    View: Handle submission from the owner selection dropdown in submission overview for AK creation
    ("New AK" button)

    This view will perform redirects depending on the selection in the owner dropdown field.
    Based upon the abstract base view :class:`AKOwnerDispatchView`.
    """

    def get_new_owner_redirect(self, event_slug):
        return redirect('submit:akowner_create', event_slug=event_slug)

    def get_valid_owner_redirect(self, event_slug, owner):
        return redirect('submit:submit_ak', event_slug=event_slug, owner_slug=owner.slug)


class AKOwnerEditDispatchView(AKOwnerDispatchView):
    """
    View: Handle submission from the owner selection dropdown in submission overview for owner editing
    ("Edit Person Info" button)

    This view will perform redirects depending on the selection in the owner dropdown field.
    Based upon the abstract base view :class:`AKOwnerDispatchView`.
    """

    def get_new_owner_redirect(self, event_slug):
        messages.add_message(self.request, messages.WARNING, _("No user selected"))
        return redirect('submit:submission_overview', event_slug)

    def get_valid_owner_redirect(self, event_slug, owner):
        return redirect('submit:akowner_edit', event_slug=event_slug, slug=owner.slug)


class AKOwnerEditView(FilterByEventSlugMixin, EventSlugMixin, EventInactiveRedirectMixin, UpdateView):
    """
    View: Edit an owner
    """
    model = AKOwner
    template_name = "AKSubmission/akowner_create_update.html"
    form_class = AKOwnerForm

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("Person Info successfully updated"))
        return reverse_lazy('submit:submission_overview', kwargs={'event_slug': self.kwargs['event_slug']})

    def form_valid(self, form):
        # Prevent updating if event is not active
        if not form.cleaned_data["event"].active:
            messages.add_message(self.request, messages.ERROR, self.get_error_message())
            return redirect(reverse_lazy('submit:submission_overview',
                                         kwargs={'event_slug': form.cleaned_data["event"].slug}))
        return super().form_valid(form)


class AKSlotAddView(EventSlugMixin, EventInactiveRedirectMixin, CreateView):
    """
    View: Add an additional slot to an AK
    The user has to select the duration of the slot in this view

    The view will only process the request when the event is active (as steered by :class:`EventInactiveRedirectMixin`)
    """
    model = AKSlot
    form_class = AKDurationForm
    template_name = "AKSubmission/akslot_add_update.html"

    def get_initial(self):
        initials = super().get_initial()
        initials['event'] = self.event
        initials['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        initials['duration'] = self.event.default_slot
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully added"))
        return self.object.ak.detail_url


class AKSlotEditView(EventSlugMixin, EventInactiveRedirectMixin, UpdateView):
    """
    View: Update the duration of an AK slot

    The view will only process the request when the event is active (as steered by :class:`EventInactiveRedirectMixin`)
    and only slots that are not scheduled yet may be changed
    """
    model = AKSlot
    form_class = AKDurationForm
    template_name = "AKSubmission/akslot_add_update.html"

    def get(self, request, *args, **kwargs):
        akslot = get_object_or_404(AKSlot, pk=kwargs["pk"])
        if akslot.start is not None:
            messages.add_message(self.request, messages.WARNING,
                                 _("You cannot edit a slot that has already been scheduled"))
            return HttpResponseRedirect(akslot.ak.detail_url)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = self.object.ak
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully updated"))
        return self.object.ak.detail_url


class AKSlotDeleteView(EventSlugMixin, EventInactiveRedirectMixin, DeleteView):
    """
    View: Delete an AK slot

    The view will only process the request when the event is active (as steered by :class:`EventInactiveRedirectMixin`)
    and only slots that are not scheduled yet may be deleted
    """
    model = AKSlot
    template_name = "AKSubmission/akslot_delete.html"

    def get(self, request, *args, **kwargs):
        akslot = get_object_or_404(AKSlot, pk=kwargs["pk"])
        if akslot.start is not None:
            messages.add_message(self.request, messages.WARNING,
                                 _("You cannot delete a slot that has already been scheduled"))
            return HttpResponseRedirect(akslot.ak.detail_url)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = self.object.ak
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("AK Slot successfully deleted"))
        return self.object.ak.detail_url


@status_manager.register(name="event_ak_messages")
class EventAKMessagesWidget(TemplateStatusWidget):
    """
    Status page widget: AK Messages

    A widget to display information about AK-related messages sent to organizers for the given event
    """
    required_context_type = "event"
    title = _("Messages")
    template_name = "admin/AKModel/render_ak_messages.html"

    def get_context_data(self, context) -> dict:
        context["ak_messages"] = AKOrgaMessage.objects.filter(ak__event=context["event"])
        return context

    def render_actions(self, context: {}) -> list[dict]:
        return [
            {
                "text": _("Delete all messages"),
                "url": reverse_lazy("admin:ak_delete_orga_messages", kwargs={"event_slug": context["event"].slug}),
            },
        ]


class AKAddOrgaMessageView(EventSlugMixin, CreateView):
    """
    View: Form to create a (confidential) message to the organizers as defined in
    :class:`AKSubmission.forms.AKOrgaMessageForm`
    """
    model = AKOrgaMessage
    form_class = AKOrgaMessageForm
    template_name = "AKSubmission/akmessage_add.html"

    def get_initial(self):
        initials = super().get_initial()
        initials['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        initials['event'] = initials['ak'].event
        return initials

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['ak'] = get_object_or_404(AK, pk=self.kwargs['pk'])
        return context

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, _("Message to organizers successfully saved"))
        return self.object.ak.detail_url
