from django.urls import path, include

from . import views

app_name = "submit"

urlpatterns = [
    path(
        '<slug:event_slug>/submission/',
        include([
            path('', views.SubmissionOverviewView.as_view(), name='submission_overview'),
            path('ak/<int:pk>', views.AKDetailView.as_view(), name='ak_detail'),
            path('aks/', views.AKListView.as_view(), name='ak_list'),
            path('aks/type/<int:type_pk>', views.AKListByTypeView.as_view(), name='ak_list_by_type'),
            path('aks/tag/<int:tag_pk>', views.AKListByTagView.as_view(), name='ak_list_by_tag'),
        ])
    ),
]
