/* Progressive enhancement: o conteúdo e os links existem mesmo sem JavaScript. */
(function () {
    "use strict";
    if (!document.body.hasAttribute("data-publico-interativo")) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reduced = () => preference.matches;
    const controllers = new WeakMap();

    function modal(dialog) {
        if (!dialog || typeof dialog.showModal !== "function") return null;
        if (controllers.has(dialog)) return controllers.get(dialog);
        let trigger = null, timer = null, pointerOutside = false;
        function finish() {
            clearTimeout(timer); timer = null;
            dialog.classList.remove("pi-saindo");
            dialog.close();
            restore();
        }
        function close() {
            if (!dialog.open || timer !== null) return;
            if (reduced()) { finish(); return; }
            dialog.classList.add("pi-saindo");
            timer = setTimeout(finish, 180);
        }
        dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
        dialog.querySelector("[data-fechar]").addEventListener("click", close);
        function restore() {
            // close é um evento assíncrono; não deve interferir numa reabertura.
            if (dialog.open) return;
            clearTimeout(timer); timer = null;
            dialog.classList.remove("pi-saindo");
            if (!document.querySelector("dialog[open]")) document.body.classList.remove("pi-modal-aberto");
            const previous = trigger;
            trigger = null;
            if (previous && previous.isConnected) previous.focus({ preventScroll: true });
        }
        dialog.addEventListener("close", restore);
        const outside = event => {
            const rect = dialog.getBoundingClientRect();
            return event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom);
        };
        dialog.addEventListener("pointerdown", event => { pointerOutside = outside(event); });
        dialog.addEventListener("click", event => {
            if (pointerOutside && outside(event)) close();
            pointerOutside = false;
        });
        const controller = { close, open(button, heading) {
            if (document.querySelector("dialog[open]")) return false;
            trigger = button;
            document.body.classList.add("pi-modal-aberto");
            dialog.showModal();
            dialog.scrollTop = 0;
            if (heading) heading.focus({ preventScroll: true });
            return true;
        }};
        controllers.set(dialog, controller);
        return controller;
    }
    window.PublicoUI = { modal };
    const dialog = document.getElementById("detalhes-publicos");
    const detail = modal(dialog);
    const title = dialog.querySelector("#pi-modal-title");
    const content = dialog.querySelector("[data-pi-content]");
    const makeButton = (text, name) => {
        const button = document.createElement("button");
        button.type = "button"; button.className = "pi-detail-button";
        button.textContent = text;
        button.setAttribute("aria-haspopup", "dialog");
        button.setAttribute("aria-controls", "detalhes-publicos");
        button.setAttribute("aria-label", `${text}: ${name}`);
        return button;
    };
    function cleanClone(source) {
        const clone = source.cloneNode(true);
        [clone, ...clone.querySelectorAll("*")].forEach(node => {
            ["id", "aria-labelledby", "aria-describedby", "data-pi-details", "data-pi-project", "data-pi-image"].forEach(attr => node.removeAttribute(attr));
        });
        clone.querySelectorAll("img").forEach(img => { img.loading = "eager"; });
        return clone;
    }
    function show(name, node, button, image = false) {
        title.textContent = name;
        content.replaceChildren(node);
        dialog.classList.toggle("pi-image-modal", image);
        detail.open(button, title);
    }
    if (detail) {
        document.querySelectorAll("[data-pi-details]").forEach(card => {
            const heading = card.querySelector("h3");
            if (!heading) return;
            const copy = cleanClone(card);
            copy.className = "pi-detail-copy";
            copy.querySelector("h3").remove();
            // Metadados permanecem na página. O corpo completo vai para a janela.
            const body = [...card.children].filter(child => child.matches("p, ul, .p3-application"));
            const lead = card.querySelector(":scope > p, :scope > ul > li");
            const text = lead ? lead.textContent.trim() : "";
            if (text) {
                const summary = document.createElement("p"); summary.className = "pi-summary";
                summary.textContent = text.length > 145 ? text.slice(0, 145).replace(/\s+\S*$/, "") + "…" : text;
                body.forEach(child => { child.hidden = true; child.setAttribute("data-pi-original", ""); });
                card.appendChild(summary);
            }
            const button = makeButton("Ver detalhes", heading.textContent.trim());
            button.addEventListener("click", () => show(heading.textContent.trim(), copy.cloneNode(true), button));
            card.appendChild(button);
        });
        document.querySelectorAll("[data-pi-project]").forEach(card => {
            const heading = card.querySelector("h2");
            const copy = cleanClone(card); copy.className = "pi-project-preview";
            copy.querySelector("h2").remove();
            const button = makeButton("Prévia do projeto", heading.textContent.trim());
            button.addEventListener("click", () => show(heading.textContent.trim(), copy.cloneNode(true), button));
            card.querySelector(".p3-project-body").appendChild(button);
        });
        document.querySelectorAll("[data-pi-image] .p4-cover-photo img").forEach(img => {
            const button = makeButton("Ampliar imagem", img.alt || "Imagem do projeto");
            button.classList.add("pi-enlarge");
            button.addEventListener("click", () => {
                const copy = cleanClone(img); copy.className = "pi-full-image";
                show(img.alt || "Imagem do projeto", copy, button, true);
            });
            img.closest("[data-pi-image]").appendChild(button);
        });
    }
    const animations = new Set();
    const targets = document.querySelectorAll("#conteudo .p3-heading, #conteudo .p3-about-layout, #conteudo .p3-grid > .p3-card, #conteudo .p3-timeline > li, #conteudo .p3-resume-aside > section, #conteudo .p4-project-card, #conteudo .p4-narrative > section, #conteudo .p3-contact-panel, #conteudo .p3-contact-link, #conteudo .pm-service-card, #conteudo .pm-how, #conteudo .p4-detail-cover");
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver(entries => entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            observer.unobserve(entry.target);
            if (reduced() || !entry.target.animate) return;
            const animation = entry.target.animate([{ opacity: .55, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 300, easing: "ease-out" });
            animations.add(animation);
            animation.onfinish = () => animations.delete(animation);
        }), { threshold: .08 });
        targets.forEach(target => observer.observe(target));
    }
    preference.addEventListener("change", () => {
        if (reduced()) { animations.forEach(animation => animation.cancel()); animations.clear(); }
    });
})();
