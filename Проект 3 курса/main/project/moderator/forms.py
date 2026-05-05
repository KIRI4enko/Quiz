from django import forms
from django.forms import inlineformset_factory
from quiz.models import Question, Choice, Team, GameSession, GameQuestion

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'time_limit', 'image']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 4}),
        }

class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ['text', 'is_correct', 'order']
        widgets = {
            'text': forms.TextInput(attrs={'size': 50}),
        }

# Формсет для вариантов ответа (можно добавлять до 4 вариантов)
ChoiceFormSet = inlineformset_factory(
    Question, Choice, form=ChoiceForm,
    extra=4, max_num=4, validate_max=True,
    can_delete=True
)

class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'password', 'color', 'logo']
        widgets = {
            'password': forms.PasswordInput(render_value=True),
            'color': forms.TextInput(attrs={'type': 'color'}),
        }

class GameSessionForm(forms.ModelForm):
    class Meta:
        model = GameSession
        fields = ['name']