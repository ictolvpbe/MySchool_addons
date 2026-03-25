import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";

patch(WebClient.prototype, {
    async _loadDefaultApp() {
        // Instead of opening the first app, click the apps menu toggle
        // to show the myschool_theme fullscreen apps overlay
        const appsMenuBtn = document.querySelector(".o_navbar_apps_menu .dropdown-toggle");
        if (appsMenuBtn) {
            appsMenuBtn.click();
        }
    },
});
