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
        const janela = doc.defaultView;
        const movimentoReduzido = () => janela.matchMedia && janela.matchMedia("(prefers-reduced-motion: reduce)").matches;
        let atual = null;
        let fechamento = null;
        const rolar = (elemento) => {
            if (elemento.scrollIntoView) elemento.scrollIntoView({ block: "start", behavior: movimentoReduzido() ? "instant" : "smooth" });
        };
        // O dialog nativo mantém o foco na janela e torna o restante da página inerte.
        // Em navegadores antigos os canais de contato continuam disponíveis abaixo.
        if (typeof painel.showModal !== "function") {
            const aviso = doc.createElement("p");
            aviso.className = "p3-card ps-sem-js";
            aviso.textContent = "Para preencher os formulários, atualize seu navegador ou ";
            const contato = doc.createElement("a");
            contato.href = doc.querySelector("#desenvolvimento a").href;
            contato.textContent = "acesse os canais de contato.";
            aviso.appendChild(contato);
            painel.before(aviso);
            return;
        }
        doc.querySelectorAll("[data-opcoes]").forEach((botao) => {
            const opcoes = doc.getElementById(botao.dataset.opcoes);
            if (!opcoes) return;
            let animacao = null;
            botao.disabled = false;
            botao.addEventListener("click", () => {
                const abrir = botao.getAttribute("aria-expanded") !== "true";
                const altura = opcoes.hidden ? 0 : opcoes.getBoundingClientRect().height;
                if (animacao) { animacao.cancel(); animacao = null; }
                botao.setAttribute("aria-expanded", String(abrir));
                botao.querySelector("[data-opcoes-texto]").textContent = abrir ? "Ocultar opções" : "Ver opções";
                opcoes.hidden = false;
                opcoes.inert = !abrir;
                if (movimentoReduzido() || !opcoes.animate) { opcoes.hidden = !abrir; return; }
                animacao = opcoes.animate([
                    { height: `${altura}px`, opacity: abrir ? 0 : 1 },
                    { height: `${abrir ? opcoes.scrollHeight : 0}px`, opacity: abrir ? 1 : 0 }
                ], { duration: 220, easing: "ease" });
                animacao.onfinish = () => { opcoes.hidden = !abrir; animacao = null; };
            });
        });
        function finalizarFechamento() {
            janela.clearTimeout(fechamento);
            fechamento = null;
            painel.classList.remove("ps-saindo");
            painel.close();
        }
        function fechar() {
            if (!painel.open || fechamento !== null) return;
            if (movimentoReduzido()) { finalizarFechamento(); return; }
            painel.classList.add("ps-saindo");
            fechamento = janela.setTimeout(finalizarFechamento, 180);
        }
        painel.addEventListener("close", () => {
            janela.clearTimeout(fechamento);
            fechamento = null;
            painel.classList.remove("ps-saindo");
            doc.body.classList.remove("ps-modal-aberto");
            if (atual) atual.focus({ preventScroll: true });
        });
        painel.addEventListener("cancel", (evento) => { evento.preventDefault(); fechar(); });
        painel.querySelector("[data-fechar]").addEventListener("click", fechar);
        let iniciouFora = false;
        const fora = (evento) => {
            const r = painel.getBoundingClientRect();
            return evento.target === painel && (evento.clientX < r.left || evento.clientX > r.right || evento.clientY < r.top || evento.clientY > r.bottom);
        };
        painel.addEventListener("pointerdown", (evento) => { iniciouFora = fora(evento); });
        painel.addEventListener("click", (evento) => {
            if (iniciouFora && fora(evento)) fechar();
            iniciouFora = false;
        });
        botoes.forEach((botao) => {
            const form = formularios.find((item) => item.dataset.formServico === botao.dataset.servico);
            if (!form) return;
            botao.disabled = false;
            botao.addEventListener("click", () => {
                atual = botao;
                formularios.forEach((item) => { item.hidden = item !== form; });
                const titulo = form.querySelector(".ps-form-titulo");
                painel.setAttribute("aria-labelledby", titulo.id);
                doc.body.classList.add("ps-modal-aberto");
                painel.showModal();
                painel.scrollTop = 0;
                titulo.focus({ preventScroll: true });
            });
        });
        formularios.forEach((form) => {
            const campos = [...form.querySelectorAll("[data-pergunta]")];
            const preview = form.querySelector("[data-preview]");
            const texto = form.querySelector("[data-mensagem]");
            const email = form.querySelector("[data-link-email]");
            const whatsapp = form.querySelector("[data-link-whatsapp]");
            const status = form.querySelector("[data-status]");
            const copiar = form.querySelector("[data-copiar]");
            function confirmarCopia() {
                copiar.classList.add("ps-copiado");
                copiar.textContent = "Mensagem copiada ✓";
                status.textContent = "Mensagem copiada. Cole no canal de contato escolhido.";
            }
            function limparPreview() {
                copiar.classList.remove("ps-copiado");
                copiar.textContent = "Copiar mensagem";
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
            copiar.addEventListener("click", async () => {
                if (!texto.value) return;
                try {
                    if (!doc.defaultView.navigator.clipboard) throw new Error("Área de transferência indisponível");
                    await doc.defaultView.navigator.clipboard.writeText(texto.value);
                    confirmarCopia();
                } catch (_) {
                    texto.focus();
                    texto.select();
                    let copiado = false;
                    try { copiado = !!doc.execCommand && doc.execCommand("copy"); } catch (_) { /* Cópia manual abaixo. */ }
                    if (copiado) confirmarCopia();
                    else status.textContent = "Mensagem selecionada. Use a opção Copiar do dispositivo ou Ctrl+C e cole no contato escolhido.";
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
