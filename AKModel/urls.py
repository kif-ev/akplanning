from csp.decorators import csp_update
from django.apps import apps
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from AKModel import views
from AKModel.views import NewEventWizardStartView, NewEventWizardSettingsView, NewEventWizardPrepareImportView, \
    NewEventWizardImportView, NewEventWizardActivateView, NewEventWizardFinishView, EventStatusView, \
    AKRequirementOverview, AKCSVExportView, AKWikiExportView, AKMessageDeleteView, export_slides

api_router = DefaultRouter()
api_router.register('akowner', views.AKOwnerViewSet, basename='AKOwner')
api_router.register('akcategory', views.AKCategoryViewSet, basename='AKCategory')
api_router.register('aktrack', views.AKTrackViewSet, basename='AKTrack')
api_router.register('ak', views.AKViewSet, basename='AK')
api_router.register('room', views.RoomViewSet, basename='Room')
api_router.register('akslot', views.AKSlotViewSet, basename='AKSlot')

extra_paths = []
if apps.is_installed("AKScheduling"):
    from AKScheduling.api import ResourcesViewSet, RoomAvailabilitiesView, EventsView, EventsViewSet, \
        ConstraintViolationsViewSet

    api_router.register('scheduling-resources', ResourcesViewSet, basename='scheduling-resources')
    api_router.register('scheduling-event', EventsViewSet, basename='scheduling-event')
    api_router.register('scheduling-constraint-violations', ConstraintViolationsViewSet,
                        basename='scheduling-constraint-violations')

    extra_paths.append(path('api/scheduling-events/', EventsView.as_view(), name='scheduling-events'))
    extra_paths.append(path('api/scheduling-room-availabilities/', RoomAvailabilitiesView.as_view(),
             name='scheduling-room-availabilities'))
if apps.is_installed("AKSubmission"):
    from AKSubmission.api import increment_interest_counter

    extra_paths.append(path('api/ak/<pk>/indicate-interest/', increment_interest_counter, name='submission-ak-indicate-interest'))

event_specific_paths = [
    path('api/', include(api_router.urls), name='api'),
]
event_specific_paths.extend(extra_paths)

app_name = 'model'

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include(event_specific_paths)
    ),
    path('user/', views.UserView.as_view(), name="user"),
]


def get_admin_urls_event_wizard(admin_site):
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
    return [
        path('<slug:slug>/status/', admin_site.admin_view(EventStatusView.as_view()), name="event_status"),
        path('<slug:event_slug>/requirements/', admin_site.admin_view(AKRequirementOverview.as_view()),
             name="event_requirement_overview"),
        path('<slug:event_slug>/ak-csv-export/', admin_site.admin_view(AKCSVExportView.as_view()),
             name="ak_csv_export"),
        path('<slug:slug>/ak-wiki-export/', admin_site.admin_view(AKWikiExportView.as_view()),
             name="ak_wiki_export"),
        path('<slug:event_slug>/delete-orga-messages/', admin_site.admin_view(AKMessageDeleteView.as_view()),
             name="ak_delete_orga_messages"),
        path('<slug:event_slug>/ak-slide-export/', export_slides, name="ak_slide_export"),

    ]
