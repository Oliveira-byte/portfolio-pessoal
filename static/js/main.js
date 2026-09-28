/* O Bootstrap controla a abertura animada da navegação. */
(function () {
    "use strict";
    const menu = document.getElementById("mainNavbar");
    const botao = document.querySelector('[data-bs-target="#mainNavbar"]');
    if (!menu || !botao) return;
    const mobile = () => window.matchMedia("(max-width: 1199.98px)").matches;
    const atualizarRotulo = (aberto) => botao.setAttribute("aria-label", aberto ? "Fechar menu" : "Abrir menu");
    function fecharMenu(devolverFoco) {
        if (!mobile()) return;
        if (window.bootstrap) window.bootstrap.Collapse.getOrCreateInstance(menu, { toggle: false }).hide();
        else { menu.classList.remove("show"); botao.setAttribute("aria-expanded", "false"); atualizarRotulo(false); }
        if (devolverFoco) botao.focus();
    }
    menu.addEventListener("show.bs.collapse", () => atualizarRotulo(true));
    menu.addEventListener("hide.bs.collapse", () => atualizarRotulo(false));
    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape" && menu.classList.contains("show")) fecharMenu(true);
    });
    menu.querySelectorAll("a[href]").forEach((link) => link.addEventListener("click", () => fecharMenu(false)));
    // Mantém o menu acessível se o carregamento do script externo falhar.
    if (!window.bootstrap) botao.addEventListener("click", () => {
        const aberto = menu.classList.toggle("show");
        botao.setAttribute("aria-expanded", String(aberto));
        atualizarRotulo(aberto);
    });
})();
