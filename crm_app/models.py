from django import forms
from django.conf import settings
from django.db import models
from django.utils import timezone
import os


# -----------------------------
# Technician (profile per user)
# -----------------------------
# In models.py - Add this to your Technician class


class Technician(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=500, default="Technicien")
    is_manager = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        u = self.user
        return (f"{u.first_name} {u.last_name}".strip()) or u.username

    @classmethod
    def get_planners_and_managers(cls):
        """Get all technicians who are planners or managers"""
        return (
            cls.objects.select_related("user")
            .filter(
                models.Q(role__icontains="conseiller en planification")
                | models.Q(is_manager=True)
            )
            .order_by("user__first_name", "user__last_name")
        )

    @classmethod
    def get_deployment_specialists(cls):
        """Get all deployment specialists (non-managers)"""
        return (
            cls.objects.select_related("user")
            .filter(
                models.Q(role__icontains="spécialiste")
                & models.Q(role__icontains="déploiement")
            )
            .order_by("user__first_name", "user__last_name")
        )


def coordination_board_path(instance, filename):
    """
    Upload path for 'Le Tableau de Coordination des Travaux' image.
    e.g. coordination_boards/2025/08/PRJ00346.png
    """
    base, ext = os.path.splitext(filename)
    num = instance.project_number or "unknown"
    return f"coordination_boards/{timezone.now():%Y/%m}/{num}{ext.lower()}"


# -----------------------------
# Project
# -----------------------------
class Project(models.Model):
    ENVIRONMENT_CHOICES = [("test", "Test"), ("prod", "Production")]

    # Keep legacy statuses AND add the operational ones + default 'assigned'
    STATUS_CHOICES = [
        # legacy (kept for dashboards)
        ("pending", "En attente"),
        ("in_progress", "En cours"),
        ("completed", "Terminé"),
        ("on_hold", "En pause"),
        ("cancelled", "Annulé"),
        # operational
        ("assigned", "Assigné"),
        ("waiting_on_client", "En attente du client"),
        ("waiting_on_internal", "En attente interne"),
        ("preparation", "Préparation"),
        ("production", "Production"),
    ]

    WORK_TYPE_CHOICES = [
        ("Migration", "Migration"),
        ("Mise a niveau", "Mise à niveau"),
        ("Rehaussement", "Rehaussement"),
        ("Demenagement", "Déménagement"),
        ("Copie de BD", "Copie de BD"),
        ("Installation poste de Support", "Installation poste de Support"),
    ]

    PHASE_CHOICES = [
        ("not_started", "Non démarrée"),
        ("in_progress", "En cours"),
        ("completed", "Complétée"),
    ]

    # ----- Informations de base -----
    title = models.CharField(max_length=200, blank=True)  # auto-filled on create
    project_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    environment = models.CharField(
        max_length=10, choices=ENVIRONMENT_CHOICES, default="test"
    )

    # Optional so Coordination minimal create can save
    client_name = models.CharField(max_length=100, blank=True)
    product = models.CharField(max_length=50, blank=True)

    work_type = models.CharField(
        max_length=50, choices=WORK_TYPE_CHOICES, default="Migration"
    )
    date = models.DateField(default=timezone.now)

    application_name = models.CharField(max_length=100, blank=True)
    database_name = models.CharField(max_length=100, blank=True)
    db_server = models.CharField(max_length=100, blank=True)
    app_server = models.CharField(max_length=100, blank=True)

    fuse_validation = models.CharField(max_length=10, default="NOK")
    certificate_validation = models.CharField(max_length=10, default="NOK")

    # who created vs who works
    technician = models.ForeignKey(
        "Technician", on_delete=models.SET_NULL, null=True, related_name="projects"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_projects",
        help_text="Personne à qui ce projet est assigné",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects",
    )

    sre_name = models.CharField(max_length=100, blank=True)
    sre_phone = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="assigned")

    # ----- Phases (kept) -----
    preparation_phase = models.CharField(
        max_length=20, choices=PHASE_CHOICES, default="not_started"
    )
    production_phase = models.CharField(
        max_length=20, choices=PHASE_CHOICES, default="not_started"
    )
    preparation_phase_started_at = models.DateTimeField(null=True, blank=True)
    preparation_phase_completed_at = models.DateTimeField(null=True, blank=True)
    production_phase_started_at = models.DateTimeField(null=True, blank=True)
    production_phase_completed_at = models.DateTimeField(null=True, blank=True)

    # ----- Coordination des déploiements -----
    # Planning board text (pasted by manager/counsellor)
    coordination_board = models.ImageField(
        upload_to=coordination_board_path, blank=True, null=True
    )

    travaux_a_faire = models.CharField(max_length=255, blank=True)
    responsable_travaux = models.CharField(max_length=255, blank=True)

    version_actuelle = models.CharField(max_length=50, blank=True)
    version_cible = models.CharField(max_length=50, blank=True)
    tables_m34 = models.CharField(max_length=100, blank=True)

    versions_matrix = models.TextField(
        blank=True, help_text="Collez ici le tableau des versions (Markdown/CSV/texte)."
    )

    contact_tech_client_to = models.TextField(blank=True)
    contact_tech_client_cc = models.TextField(blank=True)
    autres_ressources_client_cc = models.TextField(blank=True)

    courriel_confirmation_client = models.CharField(max_length=255, blank=True)
    note_importante = models.TextField(blank=True)
    taches_installations = models.TextField(blank=True)

    equipe_dev_ajouter = models.CharField(max_length=255, blank=True)
    equipe_integration_ajouter = models.CharField(max_length=255, blank=True)
    bi_a_valider = models.CharField(max_length=255, blank=True)
    autres_produits_verifier = models.CharField(max_length=255, blank=True)
    gestionnaire_projet = models.CharField(max_length=255, blank=True)

    # Legacy general start/end (kept for compatibility)
    start_at = models.DateTimeField(
        null=True, blank=True, help_text="Date et heure de début du projet"
    )
    end_at = models.DateTimeField(
        null=True, blank=True, help_text="Date et heure de fin du projet"
    )

    # Planning windows (entered by planners/managers)
    prep_date = models.DateField(null=True, blank=True)
    prep_start_time = models.TimeField(null=True, blank=True)
    prep_end_time = models.TimeField(null=True, blank=True)

    prod_date = models.DateField(null=True, blank=True)
    prod_start_time = models.TimeField(null=True, blank=True)
    prod_end_time = models.TimeField(null=True, blank=True)

    # Checklist JSON + timestamps
    checklist_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        base = self.title or f"{self.project_number} — {self.client_name}".strip()
        return base or self.project_number

    @property
    def completion_percentage(self) -> int:
        items = (self.checklist_data or {}).get("items", [])
        if not items:
            return 0
        done = sum(1 for x in items if x.get("completed"))
        return int((done / len(items)) * 100)

    @property
    def phases_completed(self) -> int:
        return sum(
            1
            for s in [
                self.preparation_phase,
                self.production_phase,
            ]
            if s == "completed"
        )


# -----------------------------
# Checklist & Timeline models
# -----------------------------
class ChecklistItem(models.Model):
    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="checklist_items"
    )
    label = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def save(self, *args, **kwargs):
        if self.completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif not self.completed:
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.project.project_number}] {self.label}"


class TimelineEntry(models.Model):
    ENVIRONMENT_CHOICES = [("test", "Test"), ("prod", "Production")]

    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="timeline"
    )
    environment = models.CharField(max_length=10, choices=ENVIRONMENT_CHOICES)
    event_label = models.CharField(max_length=200)
    event_time = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_time"]

    def __str__(self):
        return (
            f"{self.project.project_number} - {self.environment} - {self.event_label}"
        )


def checklist_image_path(instance, filename):
    pid = instance.item.project_id or "unknown"
    iid = instance.item_id or "unknown"
    return f"checklists/project_{pid}/item_{iid}/{filename}"


class ChecklistItemNote(models.Model):
    item = models.ForeignKey(
        "ChecklistItem", on_delete=models.CASCADE, related_name="notes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ChecklistItemImage(models.Model):
    item = models.ForeignKey(
        "ChecklistItem", on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=checklist_image_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]


# -----------------------------
# Checklist template library
# -----------------------------
class ChecklistTemplate(models.Model):
    name = models.CharField(max_length=120, unique=True)
    work_type = models.CharField(max_length=50, blank=True)
    json_payload = models.JSONField(default=dict)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        hint = f" [{self.work_type}]" if self.work_type else ""
        return f"{self.name}{hint}"

    def items(self):
        return (self.json_payload or {}).get("items", [])


# -----------------------------
# Coordination create (Form)
# -----------------------------
class CoordinationCreateForm(forms.Form):
    project_number = forms.CharField(
        label="Numéro de projet",
        max_length=50,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "PRJ12345"}
        ),
    )

    # IMPORTANT: don't evaluate queryset at import time (causes AppRegistryNotReady)
    technician = forms.ModelChoiceField(
        label="Technicien",
        queryset=Technician.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    status = forms.ChoiceField(
        label="Statut",
        choices=Project.STATUS_CHOICES,
        initial="assigned",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    coordination_board = forms.ImageField(
        label="Image (tableau de coordination)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/*"}
        ),
    )

    # Préparation
    prep_date = forms.DateField(
        label="Date (préparation)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    prep_start_time = forms.TimeField(
        label="Heure début (préparation)",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
    )
    prep_end_time = forms.TimeField(
        label="Heure fin (préparation)",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
    )

    # Production
    prod_date = forms.DateField(
        label="Date (production)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    prod_start_time = forms.TimeField(
        label="Heure début (production)",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
    )
    prod_end_time = forms.TimeField(
        label="Heure fin (production)",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Now models are loaded; safe to populate queryset
        self.fields["technician"].queryset = Technician.objects.select_related(
            "user"
        ).order_by("user__first_name", "user__last_name")
