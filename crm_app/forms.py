from django import forms
from .models import Project

# ✅ Custom widget that supports multiple file selection
class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class LoginForm(forms.Form):
    identifier = forms.CharField(label='Nom d’utilisateur ou e-mail')
    password = forms.CharField(widget=forms.PasswordInput, label='Mot de passe')


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'project_number', 'environment', 'client_name', 'product', 'work_type',
            'database_name', 'db_server', 'app_server', 'fuse_validation', 'certificate_validation',
            'status', 'sre_name', 'sre_phone',
        ]
        widgets = {
            'environment': forms.Select(attrs={'class': 'tw-input'}),
            'product': forms.Select(attrs={'class': 'tw-input'}),
            'work_type': forms.Select(attrs={'class': 'tw-input'}),
            'status': forms.Select(attrs={'class': 'tw-input'}),
        }


class ChecklistJSONUploadForm(forms.Form):
    json_file = forms.FileField(help_text="Fichier .json contenant les items de checklist")

    def clean_json_file(self):
        f = self.cleaned_data['json_file']
        if not f.name.lower().endswith(".json"):
            raise forms.ValidationError("Veuillez téléverser un fichier .json")
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Fichier trop volumineux (max 2 Mo)")
        return f


class ChecklistItemUpdateForm(forms.Form):
    text = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(attrs={'rows': 2})
    )
    # ⬇️ Enable multi-image uploads
    images = forms.ImageField(
        label="Images",
        required=False,
        widget=MultipleImageInput(attrs={'multiple': True, 'accept': 'image/*'})
    )
