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
