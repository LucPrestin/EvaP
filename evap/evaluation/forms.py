import logging

from django import forms
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from django.views.decorators.debug import sensitive_variables

from evap.evaluation.models import UserProfile

logger = logging.getLogger(__name__)


class LoginEmailForm(forms.Form):
    """Form encapsulating the login with email and password, for example from an Active Directory.
    """

    email = forms.CharField(label=_("Email"), max_length=254, widget=forms.EmailInput(attrs={'autofocus': True}))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)

    def __init__(self, request, *args, **kwargs):
        """
        If request is passed in, the form will validate that cookies are
        enabled. Note that the request (a HttpRequest object) must have set a
        cookie with the key TEST_COOKIE_NAME and value TEST_COOKIE_VALUE before
        running this validation.
        """
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    @sensitive_variables('password')
    def clean_password(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')

        email = email.lower()

        if email and password:
            self.user_cache = authenticate(email=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(_("Please enter a correct email and password."))
        self.check_for_test_cookie()
        return password

    def check_for_test_cookie(self):
        if self.request and not self.request.session.test_cookie_worked():
            raise forms.ValidationError(_("Your Web browser doesn't appear to have cookies enabled. Cookies are required for logging in."))

    def get_user_id(self):
        if self.user_cache:
            return self.user_cache.id
        return None

    def get_user(self):
        return self.user_cache


class NewKeyForm(forms.Form):
    email = forms.EmailField(label=_("Email address"))

    def __init__(self, *args, **kwargs):
        self.user_cache = None

        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if not UserProfile.email_needs_login_key(email):
            raise forms.ValidationError(_("HPI users cannot request login keys. Please login using your domain credentials."))

        try:
            user = UserProfile.objects.get(email__iexact=email)
            self.user_cache = user
        except UserProfile.DoesNotExist as e:
            raise forms.ValidationError(
                _("No user with this email address was found. Please make sure to enter the email address used for registration.")
            ) from e

        if not user.is_active:
            raise forms.ValidationError(_("Inactive users cannot request login keys."))

        return email

    def get_user(self):
        return self.user_cache


class UserModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.full_name_with_additional_info


class UserModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.full_name_with_additional_info


class DelegatesForm(forms.ModelForm):
    delegates = UserModelMultipleChoiceField(queryset=UserProfile.objects.exclude(is_active=False).exclude(is_proxy_user=True),
                                             required=False)

    class Meta:
        model = UserProfile
        fields = ('delegates',)
        field_classes = {
            'delegates': UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, *args, **kw):
        super().save(*args, **kw)
        logger.info('User "{}" edited the settings.'.format(self.instance.email))
