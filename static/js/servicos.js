/* Prepara mensagens localmente. Nenhum formulário é enviado ao servidor. */
(function () {
    "use strict";

    function criarMensagem(grupo, titulo, respostas) {
        const linhas = respostas
            .map(({ pergunta, valor }) => ({ pergunta, valor: String(valor).trim() }))
            .filter(({ valor }) => valor)
            .map(({ pergunta, valor }) => `${pergunta}: ${valor}`);
        return ["Olá, Danilo! Gostaria de conversar sobre este serviço.", "",
            `Área: ${grupo}`, `Serviço: ${titulo}`, "", ...linhas, "",
            "Pode me orientar sobre a avaliação, os valores e a disponibilidade?"].join("\n");
    }

    function criarLinks(email, whatsapp, titulo, mensagem) {
        const links = {
            email: `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(`Solicitação de serviço - ${titulo}`)}&body=${encodeURIComponent(mensagem.replace(/\r?\n/g, "\r\n"))}`,
            whatsapp: ""
        };
        if (/^https:\/\/wa\.me\/\d{10,15}$/.test(whatsapp)) {
            links.whatsapp = `${whatsapp}?text=${encodeURIComponent(mensagem)}`;
        }
        return links;
    }

    function iniciar(doc) {
        const painel = doc.getElementById("preparar-contato");
        if (!painel) return;
        const formularios = [...painel.querySelectorAll("[data-form-servico]")];
        const botoes = [...doc.querySelectorAll("[data-servico]")];
        let atual = null;
        const rolar = (elemento) => {
            if (elemento.scrollIntoView) elemento.scrollIntoView({ block: "start", behavior: "auto" });
        };
        botoes.forEach((botao) => {
            const form = formularios.find((item) => item.dataset.formServico === botao.dataset.servico);
            if (!form) return;
            botao.disabled = false;
            botao.addEventListener("click", () => {
                atual = botao;
                formularios.forEach((item) => { item.hidden = item !== form; });
                botoes.forEach((item) => { item.setAttribute("aria-expanded", String(item === botao)); });
                painel.hidden = false;
                form.querySelector(".ps-form-titulo").focus({ preventScroll: true });
                rolar(painel);
            });
        });
        painel.querySelector("[data-voltar]").addEventListener("click", () => {
            painel.hidden = true;
            botoes.forEach((item) => { item.setAttribute("aria-expanded", "false"); });
            if (atual) atual.focus();
        });
        formularios.forEach((form) => {
            const campos = [...form.querySelectorAll("[data-pergunta]")];
            const preview = form.querySelector("[data-preview]");
            const texto = form.querySelector("[data-mensagem]");
            const email = form.querySelector("[data-link-email]");
            const whatsapp = form.querySelector("[data-link-whatsapp]");
            const status = form.querySelector("[data-status]");
            function limparPreview() {
                preview.hidden = true;
                texto.value = "";
                email.removeAttribute("href");
                if (whatsapp) whatsapp.removeAttribute("href");
                status.textContent = "";
            }
            campos.forEach((campo) => {
                ["input", "change"].forEach((evento) => campo.addEventListener(evento, () => {
                    campo.setCustomValidity("");
                    limparPreview();
                }));
            });
            form.addEventListener("submit", (evento) => {
                evento.preventDefault();
                campos.forEach((campo) => campo.setCustomValidity(
                    campo.required && !campo.value.trim() ? "Preencha este campo." : ""
                ));
                if (!form.reportValidity()) { limparPreview(); return; }
                const mensagem = criarMensagem(form.dataset.grupo, form.dataset.titulo,
                    campos.map((campo) => ({ pergunta: campo.dataset.pergunta, valor: campo.value })));
                const links = criarLinks(form.dataset.email, form.dataset.whatsapp, form.dataset.titulo, mensagem);
                texto.value = mensagem;
                email.href = links.email;
                if (whatsapp) {
                    whatsapp.hidden = !links.whatsapp;
                    if (links.whatsapp) whatsapp.href = links.whatsapp;
                }
                status.textContent = "Mensagem preparada. Escolha um canal para continuar.";
                preview.hidden = false;
                preview.querySelector("h3").focus({ preventScroll: true });
                rolar(preview);
            });
            form.querySelector("[data-copiar]").addEventListener("click", async () => {
                if (!texto.value) return;
                try {
                    if (!doc.defaultView.navigator.clipboard) throw new Error("Área de transferência indisponível");
                    await doc.defaultView.navigator.clipboard.writeText(texto.value);
                    status.textContent = "Mensagem copiada. Cole no canal de contato escolhido.";
                } catch (_) {
                    texto.focus();
                    texto.select();
                    let copiado = false;
                    try { copiado = !!doc.execCommand && doc.execCommand("copy"); } catch (_) { /* Cópia manual abaixo. */ }
                    status.textContent = copiado ? "Mensagem copiada. Cole no canal de contato escolhido."
                        : "Mensagem selecionada. Use a opção Copiar do dispositivo ou Ctrl+C e cole no contato escolhido.";
                }
            });
        });
    }
    if (typeof module !== "undefined" && module.exports) module.exports = { criarMensagem, criarLinks, iniciar };
    if (typeof document !== "undefined") {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => iniciar(document), { once: true });
        else iniciar(document);
    }
})();
