/** @odoo-module **/

import { FormRenderer } from "@web/views/form/form_renderer";
import { patch } from "@web/core/utils/patch";
import { useRef, onMounted, onPatched, onWillUnmount } from "@odoo/owl";

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this._chatterRootRef = useRef("compiled_view_root");
        this._chatterToggleBtn = null;
        onMounted(() => this._setupChatterToggle());
        onPatched(() => this._setupChatterToggle());
        onWillUnmount(() => this._removeChatterToggle());
    },

    _removeChatterToggle() {
        if (this._chatterToggleBtn) {
            this._chatterToggleBtn.remove();
            this._chatterToggleBtn = null;
        }
    },

    _setupChatterToggle() {
        const el = this._chatterRootRef.el;
        if (!el) {
            this._removeChatterToggle();
            return;
        }

        const chatter = el.querySelector(":scope > .o-mail-Form-chatter");
        if (!chatter) {
            this._removeChatterToggle();
            return;
        }

        // Mark form as having chatter
        el.classList.add("ms-has-chatter");

        // Hide chatter on first load
        if (!chatter.dataset.chatterToggle) {
            chatter.dataset.chatterToggle = "1";
            chatter.style.display = "none";
            el.classList.add("ms-chatter-hidden");
        }

        // Already have a working button for this form
        if (this._chatterToggleBtn && this._chatterToggleBtn.isConnected) return;

        // Remove any stale button
        this._removeChatterToggle();

        const btn = document.createElement("button");
        btn.className = "btn btn-secondary ms-chatter-toggle";
        btn.type = "button";
        btn.innerHTML = '<i class="fa fa-comments me-1"></i> Berichten';
        Object.assign(btn.style, {
            position: "fixed",
            bottom: "20px",
            right: "20px",
            zIndex: "1050",
            borderRadius: "20px",
            padding: "10px 20px",
            boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
        });

        btn.addEventListener("click", () => {
            const hidden = chatter.style.display === "none";
            chatter.style.display = hidden ? "" : "none";
            el.classList.toggle("ms-chatter-hidden", !hidden);
            btn.classList.toggle("btn-secondary", !hidden);
            btn.classList.toggle("btn-primary", hidden);
        });

        document.body.appendChild(btn);
        this._chatterToggleBtn = btn;
    },
});
