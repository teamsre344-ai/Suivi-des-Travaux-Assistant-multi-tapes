from django import forms
from django.contrib.auth import get_user_model
from .models import Project, Technician

User = get_user_model()


# ---------- Standard Login Form ----------
class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Adresse e-mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "prenom.nom@lgisolutions.com",
                "class": "form-control",
            }
        ),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": "form-control",
                "placeholder": "Saisissez votre mot de passe",
            }
        ),
    )


# ---------- NEW: Coordination & Déploiement (first step for planners/managers) ----------
class CoordinationDeploymentForm(forms.Form):
    project_number = forms.CharField(
        label="Numéro de projet",
        max_length=50,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "PRJXXXX"}
        ),
    )

    technician = forms.ModelChoiceField(
        label="Spécialiste déploiement assigné",
        queryset=Technician.get_deployment_specialists(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Sélectionnez le spécialiste qui exécutera le déploiement",
    )

    gestionnaire_projet = forms.ChoiceField(
        label="Gestionnaire de Projet",
        choices=[
            ("", "---------"),
            ("Patrick Savard", "Patrick Savard"),
            ("Jessyca Lantagne", "Jessyca Lantagne"),
            ("Mamdouh Mikhail", "Mamdouh Mikhail"),
            ("Dounia EIBaine", "Dounia EIBaine"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Sélectionnez le gestionnaire de projet",
    )

    coordination_board = forms.ImageField(
        label="Le Tableau de Coordination des Travaux (image)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/png,image/jpeg,image/webp"}
        ),
    )

    client_name = forms.ChoiceField(
        label="Nom du client",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        choices=[],
        help_text="Sélectionnez le nom du client existant",
    )

    product = forms.ChoiceField(
        label="Produit",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        choices=[],
        help_text="Sélectionnez le produit",
    )

    # Préparation
    prep_date = forms.DateField(
        label="Date de préparation",
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
        label="Date de production",
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
        client_names = (
            Project.objects.values_list("client_name", flat=True)
            .distinct()
            .order_by("client_name")
        )
        self.fields["client_name"].choices = [("", "---------")] + [
            (name, name) for name in client_names
        ]
        product_names = (
            Project.objects.values_list("product", flat=True)
            .distinct()
            .order_by("product")
        )
        self.fields["product"].choices = [("", "---------")] + [
            (name, name) for name in product_names
        ]


# ---------- Project form (existing) ----------
class ProjectForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        label="Assign to",
        queryset=User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        help_text="Choisir la personne qui travaillera sur ce projet",
    )

    prep_date = forms.DateField(
        label="Date de préparation",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    prod_date = forms.DateField(
        label="Date de production",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = Project
        fields = [
            # Assignation
            "assigned_to",
            # Base + Coordination (fusionnées)
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
            "travaux_a_faire",
            "responsable_travaux",
            "version_actuelle",
            "version_cible",
            "tables_m34",
            "versions_matrix",  # multiline paste area
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
            # NEW: planning board + planning windows (visible if you include them in template)
            "coordination_board",
            "prep_date",
            "prep_start_time",
            "prep_end_time",
            "prod_date",
            "prod_start_time",
            "prod_end_time",
        ]
        widgets = {
            "note_importante": forms.Textarea(attrs={"rows": 3}),
            "taches_installations": forms.Textarea(attrs={"rows": 3}),
            "contact_tech_client_to": forms.Textarea(attrs={"rows": 2}),
            "contact_tech_client_cc": forms.Textarea(attrs={"rows": 2}),
            "autres_ressources_client_cc": forms.Textarea(attrs={"rows": 2}),
            "versions_matrix": forms.Textarea(
                attrs={
                    "rows": 12,
                    "class": "form-control shadow-sm",
                    "placeholder": "Collez ici le tableau des versions (Markdown / CSV / texte).",
                }
            ),
            "gestionnaire_projet": forms.TextInput(
                attrs={
                    "class": "form-control shadow-sm",
                    "placeholder": "Nom du gestionnaire de projet",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get client names from the database
        client_names = (
            Project.objects.values_list("client_name", flat=True)
            .distinct()
            .order_by("client_name")
        )
        self.fields["client_name"] = forms.ChoiceField(
            choices=[("", "---------")] + [(name, name) for name in client_names],
            widget=forms.Select(attrs={"class": "form-select"}),
        )

        # Get product names from the database
        product_names = (
            Project.objects.values_list("product", flat=True)
            .distinct()
            .order_by("product")
        )
        self.fields["product"] = forms.ChoiceField(
            choices=[("", "---------")] + [(name, name) for name in product_names],
            widget=forms.Select(attrs={"class": "form-select"}),
        )

        # Apply Tailwind CSS classes consistently
        for name, field in self.fields.items():
            w = field.widget

            # Use the .tw-input class defined in base.html for a consistent look
            # We remove Bootstrap classes and add the Tailwind one.
            current_classes = w.attrs.get("class", "")
            current_classes = current_classes.replace("form-control", "").replace(
                "form-select", ""
            )
            w.attrs["class"] = f"tw-input w-full {current_classes}".strip()

            # Add placeholder if not already set, but avoid for certain input types
            if not isinstance(
                w,
                (
                    forms.CheckboxInput,
                    forms.RadioSelect,
                    forms.FileInput,
                    forms.ClearableFileInput,
                ),
            ):
                w.attrs.setdefault("placeholder", field.label)

    def clean(self):
        data = super().clean()
        start = data.get("start_at")
        end = data.get("end_at")
        if start and end and end < start:
            self.add_error(
                "end_at", "La date/heure de fin doit être postérieure au début."
            )
        return data


# ---------- Checklist JSON upload (used by views) ----------
class CoordinationCreateForm(forms.ModelForm):
    """
    Minimal planner/manager screen (legacy/alternate):
    - project_number
    - assign to Technician
    - upload 'tableau de coordination' image (preview in template)
    - planning windows (prep/prod) and status (limited choices)
    """

    technician = forms.ModelChoiceField(
        label="Technicien assigné",
        queryset=Technician.objects.select_related("user").order_by(
            "user__first_name", "user__last_name"
        ),
        help_text="Sélectionnez le spécialiste déploiement responsable.",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    coordination_board = forms.ImageField(
        label="Tableau de coordination des travaux (image)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/*"}
        ),
    )

    # Planning windows
    prep_date = forms.DateField(
        label="Date de préparation",
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

    prod_date = forms.DateField(
        label="Date de production",
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

    STATUS_LIMIT = [
        ("assigned", "Assigné"),
        ("preparation", "Préparation"),
        ("production", "Production"),
        ("waiting_on_client", "En attente du client"),
        ("waiting_on_internal", "En attente interne"),
    ]
    status = forms.ChoiceField(
        label="Statut",
        choices=STATUS_LIMIT,
        initial="assigned",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Project
        fields = [
            "project_number",
            "status",
            "coordination_board",
            "prep_date",
            "prep_start_time",
            "prep_end_time",
            "prod_date",
            "prod_start_time",
            "prod_end_time",
        ]
        widgets = {
            "project_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "No. de projet"}
            ),
        }

    def clean(self):
        data = super().clean()
        ps, pe = data.get("prep_start_time"), data.get("prep_end_time")
        if ps and pe and pe <= ps:
            self.add_error(
                "prep_end_time", "L'heure de fin doit être après l'heure de début."
            )
        ps, pe = data.get("prod_start_time"), data.get("prod_end_time")
        if ps and pe and pe <= ps:
            self.add_error(
                "prod_end_time", "L'heure de fin doit être après l'heure de début."
            )
        return data


class ChecklistJSONUploadForm(forms.Form):
    json_file = forms.FileField(
        help_text="Fichier .json contenant les items de checklist"
    )

    def clean_json_file(self):
        f = self.cleaned_data["json_file"]
        name = f.name.lower()
        if not name.endswith(".json"):
            raise forms.ValidationError("Veuillez téléverser un fichier .json")
        if f.size and f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Fichier trop volumineux (max 2 Mo)")
        return f


# ---------- Notes / Images for checklist items (used by views) ----------
class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ChecklistItemUpdateForm(forms.Form):
    text = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control w-100"}),
    )
    images = forms.FileField(
        label="Images",
        required=False,
        widget=MultiFileInput(
            attrs={"multiple": True, "accept": "image/*", "class": "form-control"}
        ),
    )
