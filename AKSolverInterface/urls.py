from django.urls import path

from .views import AKJSONExportView, AKScheduleJSONImportView, SchedulingWizardChecksView, \
    SchedulingWizardLookupView, SchedulingWizardRequirementsView, \
    SchedulingWizardResultsView, SchedulingWizardSlotsView


def get_admin_urls_solver_interface(admin_site):
    # Steps of the automatic scheduling workflow (in the order of the steps, see SchedulingWizardMixin)
    return [
        path(
                "<slug:event_slug>/scheduling-workflow/",
                admin_site.admin_view(SchedulingWizardChecksView.as_view()),
                name="scheduling_wizard_checks",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/requirements/",
                admin_site.admin_view(SchedulingWizardRequirementsView.as_view()),
                name="scheduling_wizard_requirements",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/slots/",
                admin_site.admin_view(SchedulingWizardSlotsView.as_view()),
                name="scheduling_wizard_slots",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/export/",
                admin_site.admin_view(AKJSONExportView.as_view()),
                name="scheduling_wizard_export",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/lookup/",
                admin_site.admin_view(SchedulingWizardLookupView.as_view()),
                name="scheduling_wizard_lookup",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/import/",
                admin_site.admin_view(AKScheduleJSONImportView.as_view()),
                name="scheduling_wizard_import",
        ),
        path(
                "<slug:event_slug>/scheduling-workflow/results/",
                admin_site.admin_view(SchedulingWizardResultsView.as_view()),
                name="scheduling_wizard_results",
        ),
    ]
