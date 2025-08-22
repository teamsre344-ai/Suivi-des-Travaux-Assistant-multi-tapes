from django.contrib import admin
from .models import (
    Technician,
    Project,
    ChecklistItem,
    TimelineEntry,
    ChecklistItemNote,
    ChecklistItemImage,
    ChecklistTemplate,
)


# ---------- Technicians ----------
@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ("id", "user_full_name", "email", "role", "is_manager", "phone")
    list_filter = ("is_manager", "role")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
        "user__email",
        "role",
    )
    ordering = ("user__first_name", "user__last_name")

    @admin.display(description="Nom")
    def user_full_name(self, obj):
        u = obj.user
        return f"{u.first_name} {u.last_name}".strip() or u.username

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email


# ---------- Projects ----------
class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ("order", "label", "completed", "completed_at")
    readonly_fields = ("completed_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_number",
        "client_name",
        "product",
        "environment",
        "status",
        "assigned_to",
        "technician",
        "created_by",
        "created_at",
    )
    list_filter = ("environment", "status", "product", "work_type")
    search_fields = (
        "project_number",
        "client_name",
        "product",
        "technician__user__first_name",
        "technician__user__last_name",
        "created_by__first_name",
        "created_by__last_name",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChecklistItemInline]
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Assignation",
            {
                "fields": ("assigned_to", "technician", "created_by"),
            },
        ),
        (
            "Informations de base",
            {
                "fields": (
                    "project_number",
                    "environment",
                    "client_name",
                    "product",
                    "work_type",
                    "database_name",
                    "db_server",
                    "app_server",
                    "fuse_validation",
                    "certificate_validation",
                    "status",
                    "sre_name",
                    "sre_phone",
                    "title",
                    "date",
                )
            },
        ),
        (
            "Coordination des déploiements",
            {
                "fields": (
                    "travaux_a_faire",
                    "responsable_travaux",
                    "version_actuelle",
                    "version_cible",
                    "tables_m34",
                    "contact_tech_client_to",
                    "contact_tech_client_cc",
                    "autres_ressources_client_cc",
                    "courriel_confirmation_client",
                    "note_importante",
                    "taches_installations",
                    "equipe_dev_ajouter",
                    "equipe_integration_ajouter",
                    "bi_a_valider",
                    "autres_produits_verifier",
                    "gestionnaire_projet",
                )
            },
        ),
        (
            "Checklist / Métadonnées",
            {
                "fields": ("checklist_data", "created_at", "updated_at"),
            },
        ),
    )


# ---------- Timeline ----------
@admin.register(TimelineEntry)
class TimelineEntryAdmin(admin.ModelAdmin):
    list_display = ("project", "environment", "event_label", "event_time", "created_at")
    list_filter = ("environment",)
    search_fields = ("project__project_number", "project__client_name", "event_label")
    ordering = ("-event_time",)


# ---------- Checklist Pieces ----------
@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("project", "order", "label", "completed", "completed_at")
    list_filter = ("completed",)
    search_fields = ("project__project_number", "label")
    ordering = ("project", "order")


@admin.register(ChecklistItemNote)
class ChecklistItemNoteAdmin(admin.ModelAdmin):
    list_display = ("item", "author", "created_at")
    search_fields = ("item__project__project_number", "author__username", "text")
    ordering = ("-created_at",)


@admin.register(ChecklistItemImage)
class ChecklistItemImageAdmin(admin.ModelAdmin):
    list_display = ("item", "uploaded_at")
    search_fields = ("item__project__project_number",)
    ordering = ("-uploaded_at",)


# ---------- Checklist Templates ----------
@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "work_type", "owner", "created_at")
    search_fields = (
        "name",
        "work_type",
        "owner__username",
        "owner__first_name",
        "owner__last_name",
    )
    ordering = ("name",)
