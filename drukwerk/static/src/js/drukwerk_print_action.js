import { registry } from "@web/core/registry";


/**
 * Custom client action: opens the PDF in a new tab AND opens the confirmation wizard.
 * Triggered from action_download_pdf on drukwerk.record.
 */
async function drukwerkPrintAndConfirm(env, action) {
    const { record_id, url } = action.params || {};

    // 1. Open the PDF in a new tab
    if (url) {
        window.open(url, "_blank");
    }

    // 2. Create the confirmation wizard and open it via the XML-defined action
    const orm = env.services.orm;
    const actionService = env.services.action;

    const wizardIds = await orm.create("drukwerk.print.confirm.wizard", [
        { record_id },
    ]);

    await actionService.doAction("drukwerk.action_drukwerk_print_confirm_wizard", {
        additionalContext: { active_id: wizardIds[0] },
        props: { resId: wizardIds[0] },
    });
}

registry.category("actions").add("drukwerk_print_and_confirm", drukwerkPrintAndConfirm);
