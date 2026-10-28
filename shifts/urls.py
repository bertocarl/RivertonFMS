from django.urls import path

from . import views

app_name = "shifts"

urlpatterns = [
    path("", views.ShiftList.as_view(), name="list"),
    path("open/", views.shift_open, name="open"),
    path("<int:pk>/", views.shift_detail, name="detail"),
    path("<int:pk>/readings/", views.shift_readings, name="readings"),
    path("<int:pk>/dips/<str:phase>/", views.shift_dips, name="dips"),
    path("<int:pk>/verify/", views.shift_verify, name="verify"),
    path("<int:pk>/backup/", views.shift_backup, name="backup"),
    path("<int:pk>/close/", views.shift_close, name="close"),
    path("<int:pk>/reopen/", views.shift_reopen, name="reopen"),
]
