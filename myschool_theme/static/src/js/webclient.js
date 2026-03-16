/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { AppSidebar } from "@myschool_theme/js/sidebar";

patch(WebClient, {
    components: {
        ...WebClient.components,
        AppSidebar,
    },
});
