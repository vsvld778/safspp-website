import hashlib
import hmac
from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.forms.utils import ErrorDict
from .models import CaseMessage, SupportCase, User

class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email", max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "username"}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().casefold()

class SignupForm(UserCreationForm):
    invite_code = forms.CharField(label="Код приглашения", max_length=200, required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}), help_text="Код предоставляется координатором тестирования.")

    class Meta:
        model = User
        fields = ("email", "display_name", "preferred_language", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["display_name"].help_text = "Можно указать имя, которым вам удобно представиться."
        if settings.REGISTRATION_MODE == "invite":
            self.fields["invite_code"].required = True
        else:
            self.fields.pop("invite_code")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот адрес уже используется. Войдите в существующий кабинет.")
        return email

    def full_clean(self):
        # Reject an invalid invitation before unique-email validation or password hints.
        # An unauthenticated visitor without a code must not enumerate existing users.
        if self.is_bound and settings.REGISTRATION_MODE == "invite":
            expected = settings.REGISTRATION_INVITE_SHA256
            supplied = hashlib.sha256(str(self.data.get("invite_code", "")).encode()).hexdigest()
            if len(expected) != 64 or not hmac.compare_digest(supplied, expected):
                self._errors = ErrorDict()
                self.cleaned_data = {}
                self.add_error("invite_code", "Код приглашения не подходит.")
                return
        super().full_clean()

    def clean(self):
        cleaned = super().clean()
        if settings.REGISTRATION_MODE == "closed":
            raise forms.ValidationError("Регистрация сейчас закрыта.")
        if settings.REGISTRATION_MODE == "invite":
            expected = settings.REGISTRATION_INVITE_SHA256
            supplied = hashlib.sha256(cleaned.get("invite_code", "").encode()).hexdigest()
            if len(expected) != 64 or not hmac.compare_digest(supplied, expected):
                self.add_error("invite_code", "Код приглашения не подходит.")
        return cleaned

class SupportCaseForm(forms.ModelForm):
    test_data_only = forms.BooleanField(label="Подтверждаю: это вымышленная ситуация без реальных персональных данных", required=False)
    privacy_consent = forms.BooleanField(label="Согласен на обработку данных для рассмотрения обращения", required=False)

    class Meta:
        model = SupportCase
        fields = ("title", "category", "description", "city", "preferred_language")
        widgets = {"description": forms.Textarea(attrs={"rows": 7, "maxlength": 6000})}
        help_texts = {"description": "Не указывайте номера паспортов, банковских карт и другие чувствительные данные. Документы на этом этапе не нужны."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.PORTAL_INTAKE_MODE == "test":
            self.fields["test_data_only"].required = True
            self.fields.pop("privacy_consent")
        else:
            self.fields.pop("test_data_only")
            self.fields["privacy_consent"].required = True

class CaseMessageForm(forms.ModelForm):
    class Meta:
        model = CaseMessage
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 4, "maxlength": 4000})}
