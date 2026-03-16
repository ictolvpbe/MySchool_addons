/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { AppsMenu } from "@myschool_theme/js/appsmenu";

patch(NavBar, {
    components: {
        ...NavBar.components,
        AppsMenu,
    },
});
