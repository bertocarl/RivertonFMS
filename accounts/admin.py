from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class StationUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Station access", {"fields": ("role", "phone")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Station access", {"fields": ("role", "phone")}),)
    list_display = ("username", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")
