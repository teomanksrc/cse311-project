from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class PoUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "student_number", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("username", "first_name", "last_name", "student_number")
    fieldsets = UserAdmin.fieldsets + (("PO system", {"fields": ("role", "student_number")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("PO system", {"fields": ("role", "student_number")}),)
