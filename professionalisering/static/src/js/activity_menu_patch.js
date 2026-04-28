/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@mail/core/web/activity_menu";

/**
 * Wanneer de gebruiker in het activity-bell-menu klikt op de groep
 * "Professionalisering Adres / Locatie", openen we direct onze gefilterde
 * action (needs_review = True) zodat het meteen duidelijk is welke adressen
 * nog door directie bevestigd moeten worden.
 */
patch(ActivityMenu.prototype, {
    openActivityGroup(group, filter = "all", newWindow) {
        if (group?.model === "professionalisering.address") {
            this.dropdown.close();
            this.action.doAction(
                "professionalisering.action_professionalisering_addresses_review",
                { clearBreadcrumbs: true }
            );
            return;
        }
        return super.openActivityGroup(group, filter, newWindow);
    },
});
