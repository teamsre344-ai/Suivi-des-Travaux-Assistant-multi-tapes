from django import forms
from .models import Project

# ---------- Passwordless ----------
class PasswordlessLoginForm(forms.Form):
    email = forms.EmailField(
        label="Adresse e-mail",
        widget=forms.EmailInput(attrs={
            "autocomplete": "email",
            "placeholder": "prenom.nom@lgisolutions.com",
            "class": "tw-input w-full",
        })
    )

# Keep old import sites happy if anything still imports LoginForm
LoginForm = PasswordlessLoginForm


# ---------- Project form ----------
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'project_number','environment','client_name','product','work_type',
            'database_name','db_server','app_server','fuse_validation','certificate_validation',
            'status','sre_name','sre_phone',
        ]
        widgets = {
            'environment': forms.Select(attrs={'class':'tw-input'}),
            'product': forms.Select(attrs={'class':'tw-input'}),
            'work_type': forms.Select(attrs={'class':'tw-input'}),
            'status': forms.Select(attrs={'class':'tw-input'}),
        }


# ---------- Checklist JSON upload ----------
class ChecklistJSONUploadForm(forms.Form):
    json_file = forms.FileField(help_text="Fichier .json contenant les items de checklist")

    def clean_json_file(self):
        f = self.cleaned_data['json_file']
        if not f.name.lower().endswith(".json"):
            raise forms.ValidationError("Veuillez téléverser un fichier .json")
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Fichier trop volumineux (max 2 Mo)")
        return f


# ---------- Notes / Images (multi-upload, safe for Django) ----------
class MultiFileInput(forms.ClearableFileInput):
    # This avoids the “doesn't support uploading multiple files” error
    allow_multiple_selected = True

class ChecklistItemUpdateForm(forms.Form):
    text = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'w-full border rounded p-2'})
    )
    images = forms.FileField(
        label="Images",
        required=False,
        widget=MultiFileInput(attrs={'multiple': True, 'accept': 'image/*'})
    )
