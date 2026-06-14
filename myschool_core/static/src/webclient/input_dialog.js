/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Eenvoudige Odoo-dialog die om één tekstwaarde vraagt — vervangt het
 * native (en niet-getthematiseerde) ``window.prompt``.
 *
 * Gebruik (binnen een component met de dialog-service):
 *   const value = await new Promise((resolve) => {
 *       this.dialog.add(InputDialog, {
 *           title: "Hernoem",
 *           label: "Nieuwe naam:",
 *           defaultValue: current,
 *           confirm: (v) => resolve(v),
 *           cancel: () => resolve(null),
 *       });
 *   });
 */
export class InputDialog extends Component {
    static template = "myschool_core.InputDialog";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        label: { type: String, optional: true },
        defaultValue: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        confirmLabel: { type: String, optional: true },
        confirm: { type: Function },
        cancel: { type: Function, optional: true },
        close: { type: Function }, // door de dialog-service geïnjecteerd
    };

    setup() {
        this.state = useState({ value: this.props.defaultValue || "" });
        this.inputRef = useRef("input");
        onMounted(() => this.inputRef.el && this.inputRef.el.focus());
    }

    get title() {
        return this.props.title || _t("Invoer");
    }

    get confirmLabel() {
        return this.props.confirmLabel || _t("OK");
    }

    onConfirm() {
        this.props.confirm(this.state.value);
        this.props.close();
    }

    onCancel() {
        if (this.props.cancel) {
            this.props.cancel();
        }
        this.props.close();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.onConfirm();
        }
    }
}
