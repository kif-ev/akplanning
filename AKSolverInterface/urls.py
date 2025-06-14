from django.urls import path

from .views import AKJSONExportView, AKScheduleJSONImportView


def get_admin_urls_solver_interface(admin_site):
    return [
        path(
            "<slug:event_slug>/ak-json-export/",
            admin_site.admin_view(AKJSONExportView.as_view()),
            name="ak_json_export",
        ),
        path(
            "<slug:event_slug>/ak-schedule-json-import/",
            admin_site.admin_view(AKScheduleJSONImportView.as_view()),
            name="ak_schedule_json_import",
        ),
    ]
