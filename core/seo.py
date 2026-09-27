from urllib.parse import urlsplit
from django.conf import settings
from django.templatetags.static import static

PAGINAS = {
    "home": ("Danilo Oliveira | Software e manutenção técnica", "Desenvolvimento web e manutenção de computadores e notebooks em Londrina. Conheça os serviços, os projetos e acompanhe seu atendimento."),
    "sobre": ("Sobre | Danilo Oliveira", "Conheça a trajetória de Danilo Oliveira: Engenharia de Software, formação técnica em Informática e pós-graduação em Dados e IA pela PUC."),
    "servicos": ("Serviços | Danilo Oliveira", "Sites, soluções web e manutenção de computadores e notebooks. Atendimento direto, orçamento combinado e acompanhamento pela área do cliente."),
    "curriculo": ("Currículo | Danilo Oliveira", "Formação, experiência, certificação e competências de Danilo Oliveira em software, requisitos e manutenção técnica. Baixe o currículo em PDF."),
    "contato": ("Contato | Danilo Oliveira", "Converse sobre desenvolvimento de software ou manutenção de computadores e notebooks em Londrina. Consulte os canais de atendimento."),
}

def metadados(request):
    match = request.resolver_match
    namespace = match.namespace if match else ""
    name = match.url_name if match else ""
    public = namespace in {"core", "portfolio"}
    title, description = PAGINAS.get(name, ("Projetos | Danilo Oliveira", "Conheça os projetos de Danilo Oliveira, as tecnologias utilizadas e os desafios de cada solução."))
    # SITE_URL é a origem configurada pelo responsável, nunca o Host do visitante.
    origin = getattr(settings, "SITE_URL", "").rstrip("/")
    parsed = urlsplit(origin)
    valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not (parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password)
    def absolute(path):
        return origin + path if valid else ""
    return {
        "seo_titulo": title, "seo_descricao": description,
        "seo_publico": public,
        "seo_canonical": absolute(request.path) if public else "",
        "seo_imagem": absolute(static("img/brand/banner-nome.webp")) if public else "",
    }
