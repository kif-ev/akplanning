from django.urls import path, include

from . import views

app_name = "submit"

urlpatterns = [
    path(
        '<slug:event_slug>/',
        include([
            path('submission/', views.SubmissionOverviewView.as_view(), name='submission_overview'),
            path('submission/ak/<int:pk>', views.AKDetailView.as_view(), name='ak_detail'),
            path('submission/aks/', views.AKListView.as_view(), name='ak_list'),
            path('submission/aks/type/<int:type_pk>', views.AKListByTypeView.as_view(), name='ak_list_by_type'),
            path('submission/aks/tag/<int:tag_pk>', views.AKListByTagView.as_view(), name='ak_list_by_tag'),
        ])
    ),
]
