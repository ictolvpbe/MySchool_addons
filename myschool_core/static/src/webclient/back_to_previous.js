/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Generieke client-action die de gebruiker terugbrengt naar de vorige
 * controller in de breadcrumb-stack — met behoud van filterstatus,
 * scrollpositie, sortering en groeperingen.
 *
 * Gebruikt vanuit `action_delete`-methodes van aanvraag-modules
 * (professionalisering, activiteiten, drukwerk, ...) zodat de gebruiker na
 * verwijderen vanuit de form view in dezelfde lijst-status terugkeert.
 *
 * Server-side gebruik:
 *   return {
 *       'type': 'ir.actions.client',
 *       'tag': 'myschool_back_to_previous',
 *       'params': {'fallback_action': 'mijn_module.action_main'},
 *   }
 *
 * Fallback `fallback_action` wordt opgeroepen wanneer er geen vorige
 * controller op de stack staat (bv. directe URL naar de form).
 */
registry.category("actions").add("myschool_back_to_previous", async (env, action) => {
    try {
        await env.services.action.restore();
    } catch {
        const fallback = action.params?.fallback_action;
        if (fallback) {
            await env.services.action.doAction(fallback, { clearBreadcrumbs: true });
        }
    }
});
