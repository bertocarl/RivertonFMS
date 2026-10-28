from django.contrib import admin

from .models import Account, Expense, JournalEntry, JournalLine


class LineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "memo", "source")
    inlines = [LineInline]
    date_hierarchy = "date"


admin.site.register(Account)
admin.site.register(Expense)
