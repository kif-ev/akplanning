from django.apps import apps
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from AKModel.metaviews import status_manager
from AKModel.metaviews.admin import EventSlugMixin, AdminViewMixin
from AKModel.metaviews.status import TemplateStatusWidget, StatusView


@status_manager.register(name="event_overview")
class EventOverviewWidget(TemplateStatusWidget):
    required_context_type = "event"
    title = _("Overview")
    template_name = "admin/AKModel/status/event_overview.html"

    def render_status(self, context: {}) -> str:
        return "success" if not context["event"].plan_hidden else "primary"


@status_manager.register(name="event_categories")
class EventCategoriesWidget(TemplateStatusWidget):
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
        self.category_count = context['event'].akcategory_set.count()
        return f"{super().render_title(context)} ({self.category_count})"

    def render_status(self, context: {}) -> str:
        return "danger" if self.category_count == 0 else "primary"


@status_manager.register(name="event_rooms")
class EventRoomsWidget(TemplateStatusWidget):
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
        self.room_count = context['event'].room_set.count()
        return f"{super().render_title(context)} ({self.room_count})"

    def render_status(self, context: {}) -> str:
        return "danger" if self.room_count == 0 else "primary"

    def render_actions(self, context: {}) -> list[dict]:
        actions = super().render_actions(context)
        actions.append(
            {
                "text": _("Import Rooms from CSV"),
                "url": reverse_lazy("admin:room-import", kwargs={"event_slug": context["event"].slug}),
            }
        )
        return actions


@status_manager.register(name="event_aks")
class EventAKsWidget(TemplateStatusWidget):
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
                    "text": format_html('{} <span class="badge bg-secondary">{}</span>',
                                        _("Constraint Violations"),
                                        context["event"].constraintviolation_set.count()),
                    "url": reverse_lazy("admin:constraint-violations", kwargs={"slug": context["event"].slug}),
                },
                {
                    "text": _("AKs requiring special attention"),
                    "url": reverse_lazy("admin:special-attention", kwargs={"slug": context["event"].slug}),
                },
                {
                    "text": _("Enter Interest"),
                    "url": reverse_lazy("admin:enter-interest",
                            kwargs={"event_slug": context["event"].slug, "pk": context["event"].ak_set.all().first().pk}),
                },
            ])
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
        return actions


@status_manager.register(name="event_requirements")
class EventRequirementsWidget(TemplateStatusWidget):
    required_context_type = "event"
    title = _("Requirements")
    template_name = "admin/AKModel/status/event_requirements.html"

    def render_title(self, context: {}) -> str:
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
    title = _("Event Status")
    provided_context_type = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_url"] = reverse_lazy("dashboard:dashboard_event", kwargs={'slug': context["event"].slug})
        return context
