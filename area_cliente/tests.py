from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(AUTH_PASSWORD_VALIDATORS=[
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
])
class AreaClienteTests(TestCase):
    senha = "SenhaDeTeste!8392"
    nova_senha = "OutraSenha!92745"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        def criar(nome):
            identificador = f"{nome}@example.com" if User.USERNAME_FIELD == "email" else nome
            dados = {User.USERNAME_FIELD: identificador, "password": cls.senha}
            if User.USERNAME_FIELD != "email":
                dados["email"] = f"{nome}@example.com"
            return User.objects.create_user(**dados)

        cls.usuario = criar("cliente_a")
        cls.outro = criar("cliente_b")

    def entrar(self, client=None, senha=None, **extra):
        client = client or self.client
        return client.post(reverse("area_cliente:entrar"), {
            "username": self.usuario.get_username(),
            "password": senha or self.senha,
            **extra,
        })

    def test_visitante_e_encaminhado_ao_login(self):
        for nome in ["painel", "alterar_senha", "senha_alterada"]:
            with self.subTest(nome=nome):
                response = self.client.get(reverse(f"area_cliente:{nome}"))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("area_cliente:entrar"), response.url)

    def test_login_valido_abre_painel(self):
        response = self.entrar()
        self.assertRedirects(response, reverse("area_cliente:painel"))
        self.assertEqual(str(self.usuario.pk), self.client.session["_auth_user_id"])

    def test_login_invalido_nao_inicia_sessao(self):
        response = self.entrar(senha="SenhaErrada!123")
        self.assertContains(response, "Não foi possível entrar.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_usuario_inativo_nao_entra(self):
        self.usuario.is_active = False
        self.usuario.save()
        self.entrar()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_local_e_respeitado(self):
        response = self.entrar(next=reverse("area_cliente:alterar_senha"))
        self.assertRedirects(response, reverse("area_cliente:alterar_senha"))

    def test_next_externo_e_rejeitado(self):
        for destino in ["https://outro.example/", "//outro.example/"]:
            with self.subTest(destino=destino):
                client = Client()
                response = self.entrar(client=client, next=destino)
                self.assertRedirects(response, reverse("area_cliente:painel"))

    def test_painel_mostra_apenas_usuario_logado(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("area_cliente:painel"), {"user_id": self.outro.pk})
        self.assertContains(response, self.usuario.get_username())
        self.assertNotContains(response, self.outro.email)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.client.force_login(self.outro)
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertContains(response, self.outro.get_username())
        self.assertNotContains(response, self.usuario.email)

    def test_logout_exige_post_e_encerra_sessao(self):
        self.client.force_login(self.usuario)
        url = reverse("area_cliente:sair")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.client.post(url), reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_formularios_exigem_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.entrar(client=client).status_code, 403)
        client.force_login(self.usuario)
        for nome in ["alterar_senha", "sair"]:
            with self.subTest(nome=nome):
                self.assertEqual(client.post(reverse(f"area_cliente:{nome}")).status_code, 403)

    def test_login_e_logout_com_csrf_valido(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("area_cliente:entrar"))
        token = client.cookies["csrftoken"].value
        response = self.entrar(client=client, csrfmiddlewaretoken=token)
        self.assertEqual(response.status_code, 302)
        token = client.cookies["csrftoken"].value
        response = client.post(reverse("area_cliente:sair"), {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)

    def test_senha_atual_incorreta_e_recusada(self):
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("area_cliente:alterar_senha"), {
            "old_password": "senha errada",
            "new_password1": self.nova_senha, "new_password2": self.nova_senha,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("old_password", response.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.senha))

    def test_senhas_diferentes_e_fracas_sao_recusadas(self):
        self.client.force_login(self.usuario)
        for primeira, segunda in [(self.nova_senha, "Diferente!990"), ("123", "123")]:
            with self.subTest(primeira=primeira):
                response = self.client.post(reverse("area_cliente:alterar_senha"), {
                    "old_password": self.senha,
                    "new_password1": primeira, "new_password2": segunda,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.senha))

    def test_troca_senha_mantem_sessao_atual_e_revoga_outra(self):
        outro_navegador = Client()
        self.entrar()
        self.entrar(client=outro_navegador)
        response = self.client.post(reverse("area_cliente:alterar_senha"), {
            "old_password": self.senha,
            "new_password1": self.nova_senha, "new_password2": self.nova_senha,
        })
        self.assertRedirects(response, reverse("area_cliente:senha_alterada"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.nova_senha))
        self.assertEqual(self.client.get(reverse("area_cliente:painel")).status_code, 200)
        self.assertEqual(outro_navegador.get(reverse("area_cliente:painel")).status_code, 302)
        visitante = Client()
        self.entrar(client=visitante, senha=self.senha)
        self.assertNotIn("_auth_user_id", visitante.session)
        self.entrar(client=visitante, senha=self.nova_senha)
        self.assertIn("_auth_user_id", visitante.session)

    def test_login_ja_autenticado_oferece_painel(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("area_cliente:entrar"))
        self.assertContains(response, "Você já está conectado.")
        self.assertNotContains(response, 'name="password"')
