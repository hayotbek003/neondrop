from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Profile

class RegistrationForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'input-cyber', 'placeholder': 'Введите имя пользователя'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'input-cyber', 'placeholder': 'Введите ваш email'})
    )
    telegram_username = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'input-cyber', 'placeholder': '@telegram_username (необязательно)'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-cyber', 'placeholder': 'Введите пароль'})
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-cyber', 'placeholder': 'Повторите пароль'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Пользователь с таким именем уже существует.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "Пароли не совпадают.")
        return cleaned_data

class LoginForm(forms.Form):
    username_or_email = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'input-cyber', 'placeholder': 'Имя пользователя или Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-cyber', 'placeholder': 'Ваш пароль'})
    )

    def clean(self):
        cleaned_data = super().clean()
        username_or_email = cleaned_data.get('username_or_email')
        password = cleaned_data.get('password')

        if username_or_email and password:
            # Check if login input is email
            if '@' in username_or_email:
                try:
                    user_obj = User.objects.get(email__iexact=username_or_email)
                    user = authenticate(username=user_obj.username, password=password)
                except User.DoesNotExist:
                    user = None
            else:
                user = authenticate(username=username_or_email, password=password)

            if user is None:
                raise forms.ValidationError("Неверное имя пользователя/email или пароль.")
            self.user = user
        return cleaned_data

class ProfileSettingsForm(forms.ModelForm):
    telegram_username = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'input-cyber', 'placeholder': '@telegram_username'})
    )

    class Meta:
        model = Profile
        fields = ['telegram_username']
