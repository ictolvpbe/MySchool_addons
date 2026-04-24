import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";


const cogMenuRegistry = registry.category("cogMenu");


async function _isDisplayed(env) {
    const resModel = env.config?.resModel || env.searchModel?.resModel;
    if (env.config?.viewType !== "list" || resModel !== "drukwerk.record") {
        return false;
    }
    return (
        (await user.hasGroup("drukwerk.group_drukwerk_boekhouding")) ||
        (await user.hasGroup("drukwerk.group_drukwerk_admin"))
    );
}


export class DrukwerkConfigCogItem extends Component {
    static template = "drukwerk.ConfigCogItem";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    async onClick() {
        await this.action.doAction("drukwerk.action_drukwerk_config_open");
    }
}


export class DrukwerkClassReportCogItem extends Component {
    static template = "drukwerk.ClassReportCogItem";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    async onClick() {
        await this.action.doAction("drukwerk.action_drukwerk_class_report");
    }
}


export class DrukwerkStudentReportCogItem extends Component {
    static template = "drukwerk.StudentReportCogItem";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    async onClick() {
        await this.action.doAction("drukwerk.action_drukwerk_student_report");
    }
}


cogMenuRegistry.add(
    "drukwerk-config",
    { Component: DrukwerkConfigCogItem, groupNumber: 20, isDisplayed: _isDisplayed },
    { sequence: 100 },
);
cogMenuRegistry.add(
    "drukwerk-class-report",
    { Component: DrukwerkClassReportCogItem, groupNumber: 20, isDisplayed: _isDisplayed },
    { sequence: 101 },
);
cogMenuRegistry.add(
    "drukwerk-student-report",
    { Component: DrukwerkStudentReportCogItem, groupNumber: 20, isDisplayed: _isDisplayed },
    { sequence: 102 },
);
