from csp.decorators import csp_update
from django.apps import apps
from django.urls import include, path
from rest_framework.routers import DefaultRouter

import AKModel.views.api
from AKModel.views.manage import ExportSlidesView, PlanPublishView, PlanUnpublishView, DefaultSlotEditorView, \
    AKsByUserView, AKJSONImportView
from AKModel.views.ak import AKRequirementOverview, AKCSVExportView, AKJSONExportView, AKWikiExportView, \
     AKMessageDeleteView
from AKModel.views.event_wizard import NewEventWizardStartView, NewEventWizardPrepareImportView, \
    NewEventWizardImportView, NewEventWizardActivateView, NewEventWizardFinishView, NewEventWizardSettingsView
from AKModel.views.room import RoomBatchCreationView
from AKModel.views.status import EventStatusView

# Register basic API views/endpoints
api_router = DefaultRouter()
api_router.register('akowner', AKModel.views.api.AKOwnerViewSet, basename='AKOwner')
api_router.register('akcategory', AKModel.views.api.AKCategoryViewSet, basename='AKCategory')
api_router.register('aktrack', AKModel.views.api.AKTrackViewSet, basename='AKTrack')
api_router.register('ak', AKModel.views.api.AKViewSet, basename='AK')
api_router.register('room', AKModel.views.api.RoomViewSet, basename='Room')
api_router.register('akslot', AKModel.views.api.AKSlotViewSet, basename='AKSlot')

# TODO Can we move this functionality to the individual apps instead?
extra_paths = []
# If AKScheduling is active, register additional API endpoints
if apps.is_installed("AKScheduling"):
    from AKScheduling.api import ResourcesViewSet, RoomAvailabilitiesView, EventsView, EventsViewSet, \
        ConstraintViolationsViewSet, DefaultSlotsView

    api_router.register('scheduling-resources', ResourcesViewSet, basename='scheduling-resources')
    api_router.register('scheduling-event', EventsViewSet, basename='scheduling-event')
    api_router.register('scheduling-constraint-violations', ConstraintViolationsViewSet,
                        basename='scheduling-constraint-violations')

    extra_paths.append(path('api/scheduling-events/', EventsView.as_view(), name='scheduling-events'))
    extra_paths.append(path('api/scheduling-room-availabilities/', RoomAvailabilitiesView.as_view(),
             name='scheduling-room-availabilities')),
    extra_paths.append(path('api/scheduling-default-slots/', DefaultSlotsView.as_view(),
             name='scheduling-default-slots'))

#If AKSubmission is active, register an additional API endpoint for increasing the interest counter
if apps.is_installed("AKSubmission"):
    from AKSubmission.api import increment_interest_counter
    extra_paths.append(path('api/ak/<pk>/indicate-interest/', increment_interest_counter, name='submission-ak-indicate-interest'))

event_specific_paths = [
    path('api/', include(api_router.urls), name='api'),
]
event_specific_paths.extend(extra_paths)

app_name = 'model'

# Included all these extra view paths at a path starting with the event slug
urlpatterns = [
    path(
        '<slug:event_slug>/',
        include(event_specific_paths)
    ),
    path('user/', AKModel.views.manage.UserView.as_view(), name="user"),
]


def get_admin_urls_event_wizard(admin_site):
    """
    Defines all additional URLs for the event creation wizard
    """
    return [
        path('add/wizard/start/', admin_site.admin_view(NewEventWizardStartView.as_view()),
             name="new_event_wizard_start"),
        path('add/wizard/settings/', csp_update(FONT_SRC=["maxcdn.bootstrapcdn.com"], SCRIPT_SRC=["cdnjs.cloudflare.com"], STYLE_SRC=["cdnjs.cloudflare.com"])(admin_site.admin_view(NewEventWizardSettingsView.as_view())),
             name="new_event_wizard_settings"),
        path('add/wizard/created/<slug:event_slug>/', admin_site.admin_view(NewEventWizardPrepareImportView.as_view()),
             name="new_event_wizard_prepare_import"),
        path('add/wizard/import/<slug:event_slug>/from/<slug:import_slug>/',
             admin_site.admin_view(NewEventWizardImportView.as_view()),
             name="new_event_wizard_import"),
        path('add/wizard/activate/<slug:slug>/',
             admin_site.admin_view(NewEventWizardActivateView.as_view()),
             name="new_event_wizard_activate"),
        path('add/wizard/finish/<slug:slug>/',
             admin_site.admin_view(NewEventWizardFinishView.as_view()),
             name="new_event_wizard_finish"),
    ]


def get_admin_urls_event(admin_site):
    """
    Defines all additional event-related view URLs that will be included in the event admin interface
    """
    return [
        path('<slug:event_slug>/status/', admin_site.admin_view(EventStatusView.as_view()), name="event_status"),
        path('<slug:event_slug>/requirements/', admin_site.admin_view(AKRequirementOverview.as_view()),
             name="event_requirement_overview"),
        path('<slug:event_slug>/aks/owner/<pk>/', admin_site.admin_view(AKsByUserView.as_view()),
             name="aks_by_owner"),
        path('<slug:event_slug>/ak-csv-export/', admin_site.admin_view(AKCSVExportView.as_view()),
             name="ak_csv_export"),
        path('<slug:event_slug>/ak-json-export/', admin_site.admin_view(AKJSONExportView.as_view()),
             name="ak_json_export"),
        path('<slug:event_slug>/ak-json-import/', admin_site.admin_view(AKJSONImportView.as_view()),
             name="ak_json_import"),
        path('<slug:slug>/ak-wiki-export/', admin_site.admin_view(AKWikiExportView.as_view()),
             name="ak_wiki_export"),
        path('<slug:event_slug>/delete-orga-messages/', admin_site.admin_view(AKMessageDeleteView.as_view()),
             name="ak_delete_orga_messages"),
        path('<slug:event_slug>/ak-slide-export/', admin_site.admin_view(ExportSlidesView.as_view()), name="ak_slide_export"),
        path('plan/publish/', admin_site.admin_view(PlanPublishView.as_view()), name="plan-publish"),
        path('plan/unpublish/', admin_site.admin_view(PlanUnpublishView.as_view()), name="plan-unpublish"),
        path('<slug:event_slug>/defaultSlots/', admin_site.admin_view(DefaultSlotEditorView.as_view()),
             name="default-slots-editor"),
        path('<slug:event_slug>/importRooms/', admin_site.admin_view(RoomBatchCreationView.as_view()),
             name="room-import"),
    ]
