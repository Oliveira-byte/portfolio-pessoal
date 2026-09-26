from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


class LoginClienteForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Não foi possível entrar. Confira seus dados de acesso.",
        "inactive": "Não foi possível entrar. Confira seus dados de acesso.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = (
            "E-mail" if self.username_field.name == "email" else "Usuário"
        )
        self.fields["username"].widget.attrs.update({
            "class": "p5-input", "autocomplete": "username", "autocapitalize": "none",
            "spellcheck": "false",
        })
        self.fields["password"].label = "Senha"
        self.fields["password"].widget.attrs.update({
            "class": "p5-input", "autocomplete": "current-password",
        })


class SenhaClienteForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "old_password": "Senha atual",
            "new_password1": "Nova senha",
            "new_password2": "Confirme a nova senha",
        }
        for name, field in self.fields.items():
            field.label = labels[name]
            field.widget.attrs["class"] = "p5-input"
