from django.contrib import admin
from .models import Technician, Project, ChecklistItem, TimelineEntry

@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ('id','user','role','is_manager')
    search_fields = ('user__username','user__email','user__first_name','user__last_name')

class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0

class TimelineInline(admin.TabularInline):
    model = TimelineEntry
    extra = 0

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_number','client_name','product','environment','status','technician','created_at')
    list_filter = ('status','environment','product')
    search_fields = ('project_number','client_name','database_name')
    inlines = [ChecklistInline, TimelineInline]

@admin.register(ChecklistItem)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('project','label','completed','order')

@admin.register(TimelineEntry)
class TimelineAdmin(admin.ModelAdmin):
    list_display = ('project','environment','event_label','event_time')
