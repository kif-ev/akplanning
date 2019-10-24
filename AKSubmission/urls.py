from django.urls import path, include

from . import views

app_name = "submit"

urlpatterns = [
    path(
        '<slug:event_slug>/submission/',
        include([
            path('', views.SubmissionOverviewView.as_view(), name='submission_overview'),
            path('ak/<int:pk>', views.AKDetailView.as_view(), name='ak_detail'),
            path('ak/<int:pk>/edit/', views.AKEditView.as_view(), name='ak_edit'),
            path('aks/', views.AKListView.as_view(), name='ak_list'),
            path('aks/category/<int:category_pk>', views.AKListByCategoryView.as_view(), name='ak_list_by_category'),
            path('aks/tag/<int:tag_pk>', views.AKListByTagView.as_view(), name='ak_list_by_tag'),
            path('owner/', views.AKOwnerCreateView.as_view(), name='akowner_create'),
            path('new/', views.AKOwnerSelectDispatchView.as_view(), name='akowner_select'),
            path('owner/edit/', views.AKOwnerEditDispatchView.as_view(), name='akowner_edit_dispatch'),
            path('<slug:slug>/edit/', views.AKOwnerEditView.as_view(), name='akowner_edit'),
            path('<slug:owner_slug>/new/', views.AKSubmissionView.as_view(), name='submit_ak'),
            path('new_wish/', views.AKWishSubmissionView.as_view(), name='submit_ak_wish'),
        ])
    ),
]
