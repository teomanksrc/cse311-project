from django import forms

from curriculum.models import Assessment, LearningOutcome


class LearningOutcomeForm(forms.ModelForm):
    class Meta:
        model = LearningOutcome
        fields = ["code", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["name"]


class SyllabusUploadForm(forms.Form):
    """Either a .pdf/.txt file (max 2 MB) or pasted text."""

    MAX_FILE_BYTES = 2 * 1024 * 1024

    file = forms.FileField(required=False)
    text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 10}))

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file:
            if not file.name.lower().endswith((".pdf", ".txt")):
                raise forms.ValidationError("Only .pdf and .txt files are supported.")
            if file.size > self.MAX_FILE_BYTES:
                raise forms.ValidationError("The file is larger than 2 MB.")
        return file

    def clean(self):
        cleaned = super().clean()
        if not self.errors and not cleaned.get("file") and not cleaned.get("text", "").strip():
            raise forms.ValidationError("Upload a file or paste the syllabus text.")
        return cleaned
