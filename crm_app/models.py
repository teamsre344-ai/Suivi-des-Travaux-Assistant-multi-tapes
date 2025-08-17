from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

# Postgres helpers (arrays + GIN)
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex


# ---------------------------------------------------------------------
# User profile (Technician) – also used for “My profile” in the navbar
# ---------------------------------------------------------------------
class Technician(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=50, default='Technicien')
    is_manager = models.BooleanField(default=False)

    # Lightweight profile fields (defaults so migrations won’t prompt)
    title = models.CharField(max_length=60, blank=True, default='')       # ex. SRE, Chef d’équipe
    location = models.CharField(max_length=120, blank=True, default='')   # ex. Montréal, QC
    avatar_url = models.URLField(blank=True, default='')                  # optionnel
    preferences = models.JSONField(default=dict, blank=True)              # UI / produit / etc.

    def __str__(self):
        display = f"{self.user.first_name} {self.user.last_name}".strip()
        return display or self.user.username

    @property
    def initials(self):
        fn = (self.user.first_name or "").strip()[:1]
        ln = (self.user.last_name or "").strip()[:1]
        base = (fn + ln) or (self.user.username[:2])
        return base.upper()


# ---------------------------------------------------------------------
# ProjectRuleSet – reusable rule profiles (keyed by name)
# ---------------------------------------------------------------------
class ProjectRuleSet(models.Model):
    """
    Reusable “rules” profile for projects.
    PRIMARY KEY = name (requested key).
    """
    name = models.CharField(max_length=200, primary_key=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rulesets')
    description = models.TextField(blank=True)

    default_environment = models.CharField(max_length=10, blank=True)
    default_product = models.CharField(max_length=50, blank=True)
    default_work_type = models.CharField(max_length=50, blank=True)

    required_approvals = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    tags = ArrayField(models.CharField(max_length=30), default=list, blank=True)

    prechecks = models.JSONField(default=dict, blank=True)
    default_checklist = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner'], name='idx_rules_owner'),
            models.Index(fields=['default_environment', 'default_product'], name='idx_rules_env_prod'),
            GinIndex(fields=['tags'], name='idx_rules_tags_gin'),
        ]
        constraints = [
            models.CheckConstraint(check=~models.Q(name=''), name='chk_rules_name_not_empty'),
        ]

    def __str__(self):
        return self.name

    def checklist_items(self):
        return (self.default_checklist or {}).get('items', [])


# ---------------------------------------------------------------------
# Project – main entity with 3-phase workflow
# ---------------------------------------------------------------------
class Project(models.Model):
    ENVIRONMENT_CHOICES = [('test', 'Test'), ('prod', 'Production')]
    PRODUCT_CHOICES = [
        ('GRF', 'GRF'), ('GRM', 'GRM'), ('GFM', 'GFM'), ('Clinibase CI', 'Clinibase CI'),
        ('GRH', 'GRH'), ('eClinibase', 'eClinibase'), ('SIurge', 'SIurge'), ('Sicheld', 'Sicheld'),
        ('Med Echo', 'Med Echo'), ('I-CLSC', 'I-CLSC'), ('RadImage', 'RadImage'),
    ]
    WORK_TYPE_CHOICES = [
        ('Migration', 'Migration'),
        ('Mise a niveau', 'Mise à niveau'),
        ('Rehaussement', 'Rehaussement'),
        ('Demenagement', 'Déménagement'),
        ('Copie de BD', 'Copie de BD'),
        ('Installation poste de Support', 'Installation poste de Support'),
    ]
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminé'),
        ('on_hold', 'En pause'),
        ('cancelled', 'Annulé'),
    ]

    # Phases
    PHASE_CHOICES = [
        ('not_started', 'Non démarrée'),
        ('in_progress', 'En cours'),
        ('completed', 'Complétée'),
    ]

    # Keys
    title = models.CharField(max_length=200, unique=True)  # requested “project name” key
    project_number = models.CharField(max_length=50, unique=True)

    # Link to ruleset (keyed by ruleset.name)
    ruleset = models.ForeignKey(
        ProjectRuleSet, to_field='name',
        on_delete=models.SET_NULL, null=True, blank=True, related_name='projects'
    )

    # Business fields
    environment = models.CharField(max_length=10, choices=ENVIRONMENT_CHOICES)
    client_name = models.CharField(max_length=100)
    product = models.CharField(max_length=50, choices=PRODUCT_CHOICES)
    date = models.DateField(default=timezone.now)

    database_name = models.CharField(max_length=100)
    db_server = models.CharField(max_length=100)
    app_server = models.CharField(max_length=100)

    fuse_validation = models.CharField(max_length=10, default='NOK')
    certificate_validation = models.CharField(max_length=10, default='NOK')

    work_type = models.CharField(max_length=50, choices=WORK_TYPE_CHOICES, default='Migration')

    technician = models.ForeignKey(
        'Technician', on_delete=models.SET_NULL, null=True,
        related_name='projects', db_index=True
    )
    sre_name = models.CharField(max_length=100, blank=True)
    sre_phone = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Creator (fast “my work” filters)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_projects', db_index=True
    )

    # --- GEO (new, optional) ---
    site_city    = models.CharField(max_length=120, blank=True, default='')
    site_region  = models.CharField(max_length=120, blank=True, default='')   # ex: QC, ON…
    site_country = models.CharField(max_length=2,   blank=True, default='CA') # ISO2
    latitude     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Checklists / timeline
    checklist_data = models.JSONField(default=dict, blank=True)
    timeline_data = models.JSONField(default=dict, blank=True)

    error_impact = models.TextField(blank=True)
    error_solution = models.TextField(blank=True)
    rollback_planned = models.BooleanField(default=False)

    # --- 3 Phases ---
    preparation_phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='not_started')
    execution_phase   = models.CharField(max_length=20, choices=PHASE_CHOICES, default='not_started')
    validation_phase  = models.CharField(max_length=20, choices=PHASE_CHOICES, default='not_started')

    # Phase timestamps
    preparation_started_at = models.DateTimeField(null=True, blank=True)
    preparation_completed_at = models.DateTimeField(null=True, blank=True)
    execution_started_at = models.DateTimeField(null=True, blank=True)
    execution_completed_at = models.DateTimeField(null=True, blank=True)
    validation_started_at = models.DateTimeField(null=True, blank=True)
    validation_completed_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'technician', 'created_at'], name='idx_proj_status_tech_created'),
            models.Index(fields=['environment', 'product'], name='idx_proj_env_prod'),
            models.Index(fields=['client_name', 'product', 'status'], name='idx_proj_client_prod_status'),
            models.Index(fields=['client_name'], name='idx_proj_client'),
            models.Index(fields=['date'], name='idx_proj_date'),
            models.Index(fields=['created_by', '-created_at'], name='idx_proj_creator_recent'),
            models.Index(fields=['technician', '-created_at'], name='idx_proj_tech_recent'),
            models.Index(fields=['preparation_phase', 'execution_phase', 'validation_phase'], name='idx_proj_phases'),
            models.Index(fields=['site_country', 'site_region'], name='idx_proj_geo_region'),  # NEW
        ]

    # -------- Validation rules for sequence --------
    def clean(self):
        # Must complete preparation before execution in_progress/completed
        if self.execution_phase in ('in_progress', 'completed') and self.preparation_phase != 'completed':
            raise ValidationError("Vous devez compléter la phase de préparation avant l'exécution.")
        # Must complete execution before validation in_progress/completed
        if self.validation_phase in ('in_progress', 'completed') and self.execution_phase != 'completed':
            raise ValidationError("Vous devez compléter l'exécution avant la validation.")

    # -------- Internal helpers --------
    def _update_phase_timestamps(self, old_value, new_value, prefix):
        now = timezone.now()
        started_field = f"{prefix}_started_at"
        completed_field = f"{prefix}_completed_at"

        # Set start time when moving to in_progress
        if old_value != new_value and new_value == 'in_progress' and getattr(self, started_field) is None:
            setattr(self, started_field, now)

        # Set completed time when moving to completed
        if old_value != new_value and new_value == 'completed':
            if getattr(self, started_field) is None:
                setattr(self, started_field, now)
            if getattr(self, completed_field) is None:
                setattr(self, completed_field, now)

    def _derive_overall_status(self):
        # Don’t auto-override administrative states
        if self.status in ('on_hold', 'cancelled'):
            return

        phases = [self.preparation_phase, self.execution_phase, self.validation_phase]
        if all(p == 'completed' for p in phases):
            self.status = 'completed'
        elif any(p == 'in_progress' for p in phases) or any(p == 'completed' for p in phases):
            self.status = 'in_progress'
        else:
            self.status = 'pending'

    def save(self, *args, **kwargs):
        old = None
        if self.pk:
            try:
                old = Project.objects.only(
                    'preparation_phase', 'execution_phase', 'validation_phase'
                ).get(pk=self.pk)
            except Project.DoesNotExist:
                old = None

        # Validate sequence
        self.full_clean(exclude=None)

        # Update timestamps when phases change
        if old:
            self._update_phase_timestamps(old.preparation_phase, self.preparation_phase, 'preparation')
            self._update_phase_timestamps(old.execution_phase, self.execution_phase, 'execution')
            self._update_phase_timestamps(old.validation_phase, self.validation_phase, 'validation')

        # Derive overall status from phases
        self._derive_overall_status()

        super().save(*args, **kwargs)

    # -------- Convenience properties for UI --------
    @property
    def phases_completed_count(self) -> int:
        return sum(1 for p in [self.preparation_phase, self.execution_phase, self.validation_phase] if p == 'completed')

    @property
    def phases_completion_percentage(self) -> int:
        return int((self.phases_completed_count / 3) * 100)

    def __str__(self):
        return f"{self.environment.upper()} — {self.client_name} — {self.product} — {self.project_number}"

    @property
    def completion_percentage(self):
        items = (self.checklist_data or {}).get('items', [])
        if not items:
            return 0
        done = sum(1 for x in items if x.get('completed'))
        return int((done / len(items)) * 100)


# ---------------------------------------------------------------------
# Checklist & Timeline
# ---------------------------------------------------------------------
class ChecklistItem(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='checklist_items')
    label = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def save(self, *args, **kwargs):
        if self.completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif not self.completed:
            self.completed_at = None
        super().save(*args, **kwargs)


class TimelineEntry(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='timeline_entries')
    environment = models.CharField(max_length=10, choices=[('test', 'Test'), ('prod', 'Production')])
    event_label = models.CharField(max_length=200)
    event_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['environment', 'event_time']

    def __str__(self):
        return f"{self.project.project_number} - {self.environment} - {self.event_label}"
# --- NEW: Checklist templates, notes, and images ---

def checklist_image_path(instance, filename):
    # media/checklists/project_<id>/item_<id>/<filename>
    pid = instance.item.project_id or "unknown"
    iid = instance.item_id or "unknown"
    return f"checklists/project_{pid}/item_{iid}/{filename}"

class ChecklistTemplate(models.Model):
    """
    Lets users upload a JSON checklist once and reuse it by name and/or work_type.
    Example JSON payload:
      {"items": [{"label": "Step A"}, {"label": "Step B"}]}
    """
    name = models.CharField(max_length=120, unique=True)
    work_type = models.CharField(max_length=50, blank=True)  # optional hint
    json_payload = models.JSONField()
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        hint = f" [{self.work_type}]" if self.work_type else ""
        return f"{self.name}{hint}"

class ChecklistItemNote(models.Model):
    item = models.ForeignKey('ChecklistItem', on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class ChecklistItemImage(models.Model):
    item = models.ForeignKey('ChecklistItem', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=checklist_image_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
