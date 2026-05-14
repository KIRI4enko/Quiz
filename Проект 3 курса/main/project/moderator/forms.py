from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError

from quiz.models import Question, Choice, Team, GameSession, GameQuestion


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'time_limit']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 4}),
        }


class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ['text']
        widgets = {
            'text': forms.TextInput(attrs={'size': 50, 'placeholder': 'Текст варианта'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text'].required = False


class BaseChoiceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        filled = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('text', '').strip():
                filled += 1
        if filled < 2:
            raise ValidationError('Укажите минимум два варианта ответа с текстом.')


ChoiceFormSet = inlineformset_factory(
    Question,
    Choice,
    form=ChoiceForm,
    formset=BaseChoiceFormSet,
    extra=4,
    max_num=4,
    validate_max=True,
    can_delete=False,
    min_num=0,
    validate_min=False,
)


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'password', 'logo']
        widgets = {
            'password': forms.PasswordInput(render_value=True),
            'logo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }


class GameSessionForm(forms.ModelForm):
    class Meta:
        model = GameSession
        fields = ['name']
