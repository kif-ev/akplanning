from django.apps import apps
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from AKModel.metaviews import status_manager
from AKModel.metaviews.admin import EventSlugMixin
from AKModel.metaviews.status import TemplateStatusWidget, StatusView


@status_manager.register(name="event_overview")
class EventOverviewWidget(TemplateStatusWidget):
    """
    Status page widget: Event overview
    """
    required_context_type = "event"
    title = _("Overview")
    template_name = "admin/AKModel/status/event_overview.html"

    def render_status(self, context: {}) -> str:
        return "success" if not context["event"].plan_hidden else "primary"


@status_manager.register(name="event_categories")
class EventCategoriesWidget(TemplateStatusWidget):
    """
    Status page widget: Category information

    Show all categories of the event together with the number of AKs belonging to this category.
    Offers an action to add a new category.
    """
    required_context_type = "event"
    title = _("Categories")
    template_name = "admin/AKModel/status/event_categories.html"
    actions = [
        {
            "text": _("Add category"),
            "url": reverse_lazy("admin:AKModel_akcategory_add"),
         }
    ]

    def render_title(self, context: {}) -> str:
        # Store category count as instance variable for re-use in body
        self.category_count = context['event'].akcategory_set.count()  # pylint: disable=attribute-defined-outside-init
        return f"{super().render_title(context)} ({self.category_count})"

    def render_status(self, context: {}) -> str:
        return "danger" if self.category_count == 0 else "primary"


@status_manager.register(name="event_rooms")
class EventRoomsWidget(TemplateStatusWidget):
    """
    Status page widget: Category information

    Show all rooms of the event.
    Offers actions to add a single new room as well as for batch creation.
    """
    required_context_type = "event"
    title = _("Rooms")
    template_name = "admin/AKModel/status/event_rooms.html"
    actions = [
        {
            "text": _("Add Room"),
            "url": reverse_lazy("admin:AKModel_room_add"),
         }
    ]

    def render_title(self, context: {}) -> str:
        # Store room count as instance variable for re-use in body
        self.room_count = context['event'].room_set.count()  # pylint: disable=attribute-defined-outside-init
        return f"{super().render_title(context)} ({self.room_count})"

    def render_status(self, context: {}) -> str:
        return "danger" if self.room_count == 0 else "primary"

    def render_actions(self, context: {}) -> list[dict]:
        actions = super().render_actions(context)
        # Action has to be added here since it depends on the event for URL building
        import_room_url = reverse_lazy("admin:room-import", kwargs={"event_slug": context["event"].slug})
        for action in actions:
            if action["url"] == import_room_url:
                return actions

        actions.append(
            {
                "text": _("Import Rooms from CSV"),
                "url": import_room_url,
            }
        )
        return actions


@status_manager.register(name="event_aks")
class EventAKsWidget(TemplateStatusWidget):
    """
    Status page widget: AK information

    Show information about the AKs of this event.
    Offers a long list of AK-related actions and also scheduling actions of AKScheduling is active
    """
    required_context_type = "event"
    title = _("AKs")
    template_name = "admin/AKModel/status/event_aks.html"

    def get_context_data(self, context) -> dict:
        context["ak_count"] = context["event"].ak_set.count()
        context["unscheduled_slots_count"] = context["event"].akslot_set.filter(start=None).count
        return context

    def render_actions(self, context: {}) -> list[dict]:
        actions = [
            {
                "text": _("Scheduling"),
                "url": reverse_lazy("admin:schedule", kwargs={"event_slug": context["event"].slug}),
            },
        ]
        if apps.is_installed("AKScheduling"):
            actions.extend([
                {
                    "text": _("AKs requiring special attention"),
                    "url": reverse_lazy("admin:special-attention", kwargs={"slug": context["event"].slug}),
                },
            ])
            if context["event"].ak_set.count() > 0:
                actions.append({
                    "text": _("Enter Interest"),
                    "url": reverse_lazy("admin:enter-interest",
                                        kwargs={"event_slug": context["event"].slug,
                                                "pk": context["event"].ak_set.all().first().pk}
                                        ),
                })
        actions.extend([
                {
                    "text": _("Edit Default Slots"),
                    "url": reverse_lazy("admin:default-slots-editor", kwargs={"event_slug": context["event"].slug}),
                },
                {
                    "text": _("Manage ak tracks"),
                    "url": reverse_lazy("admin:tracks_manage", kwargs={"event_slug": context["event"].slug}),
                },
                {
                    "text": _("Clear schedule"),
                    "url": reverse_lazy("admin:clear_schedule", kwargs={"event_slug": context["event"].slug}),
                },
                {
                    "text": _("Export AKs as CSV"),
                    "url": reverse_lazy("admin:ak_csv_export", kwargs={"event_slug": context["event"].slug}),
                },
                {
                    "text": _("Export AKs for Wiki"),
                    "url": reverse_lazy("admin:ak_wiki_export", kwargs={"slug": context["event"].slug}),
                },
                {
                    "text": _("Export AK Slides"),
                    "url": reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": context["event"].slug}),
                },
            ]
        )
        if apps.is_installed("AKSolverInterface"):
            actions.extend([
                {
                    "text": _("Export AKs as JSON"),
                    "url": reverse_lazy("admin:ak_json_export", kwargs={"event_slug": context["event"].slug}),
                },
                {
                    "text": _("Import AK schedule from JSON"),
                    "url": reverse_lazy("admin:ak_schedule_json_import", kwargs={"event_slug": context["event"].slug}),
                },
            ])
        return actions


@status_manager.register(name="event_requirements")
class EventRequirementsWidget(TemplateStatusWidget):
    """
    Status page widget: Requirement information information

    Show information about the requirements of this event.
    Offers actions to add new requirements or to get a list of AKs having a given requirement.
    """
    required_context_type = "event"
    title = _("Requirements")
    template_name = "admin/AKModel/status/event_requirements.html"

    def render_title(self, context: {}) -> str:
        # Store requirements count as instance variable for re-use in body
        # pylint: disable=attribute-defined-outside-init
        self.requirements_count = context['event'].akrequirement_set.count()
        return f"{super().render_title(context)} ({self.requirements_count})"

    def render_actions(self, context: {}) -> list[dict]:
        return [
            {
                "text": _("Show AKs for requirements"),
                "url": reverse_lazy("admin:event_requirement_overview", kwargs={"event_slug": context["event"].slug}),
            },
            {
                "text": _("Add Requirement"),
                "url": reverse_lazy("admin:AKModel_akrequirement_add"),
            },
        ]


class EventStatusView(EventSlugMixin, StatusView):
    """
    View: Show a status dashboard for the given event
    """
    title = _("Event Status")
    provided_context_type = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_url"] = reverse_lazy("dashboard:dashboard_event", kwargs={'slug': context["event"].slug})
        return context
