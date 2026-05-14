/** @odoo-module **/

/**
 * myschool_theme — global light/dark/auto preference.
 *
 * Reads the active user's `myschool_theme_mode` (Selection on res.users)
 * at webclient startup and applies it as `data-theme="dark"` (or absent)
 * on <body>. Listens to OS-level prefers-color-scheme changes so 'auto'
 * mode tracks the system in real time.
 *
 * Public API on the service object:
 *   - mode            current stored mode ('auto'|'light'|'dark')
 *   - effective       resolved theme ('light'|'dark')
 *   - setMode(m)      persist a new mode (writes to res.users) + apply
 *   - cycle()         convenience: auto → dark → light → auto
 *   - bus             EventBus, dispatches 'change' on every apply
 */

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { EventBus } from "@odoo/owl";

const VALID_MODES = ["auto", "light", "dark"];
const ATTR_HOST = () => document.body;

function resolveEffective(mode, systemDark) {
    if (mode === "dark") return "dark";
    if (mode === "light") return "light";
    return systemDark ? "dark" : "light";
}

function applyToBody(effective) {
    const host = ATTR_HOST();
    if (!host) return;
    if (effective === "dark") {
        host.setAttribute("data-theme", "dark");
    } else {
        host.removeAttribute("data-theme");
    }
}

export const themeService = {
    dependencies: ["orm"],

    async start(env, { orm }) {
        const bus = new EventBus();
        const systemDarkMedia = window.matchMedia("(prefers-color-scheme: dark)");

        // Local mirror of the user's preference. Defaults to 'auto' if
        // the field is missing on the user record (older installs).
        let mode = "auto";

        const dispatch = () => {
            const effective = resolveEffective(mode, systemDarkMedia.matches);
            applyToBody(effective);
            bus.trigger("change", { mode, effective });
        };

        // Apply optimistically before the RPC returns so the first paint
        // already uses the system preference. The RPC overrides this once
        // the user's stored choice is known.
        dispatch();

        // Fetch the user's stored choice. Use sudo-less ORM read on
        // res.users for the current uid; the field is in SELF_READABLE_FIELDS
        // so this works for any logged-in user.
        try {
            const result = await orm.read(
                "res.users",
                [user.userId],
                ["myschool_theme_mode"],
            );
            const stored = result?.[0]?.myschool_theme_mode;
            if (VALID_MODES.includes(stored)) {
                mode = stored;
                dispatch();
            }
        } catch (e) {
            // If the field doesn't exist yet (module not upgraded) or
            // the user has no read access, fall back to 'auto'. Don't
            // block webclient startup on a theme preference.
            console.warn("myschool_theme: could not read user pref:", e);
        }

        // Track system changes — only re-apply when in auto mode, but
        // dispatch the bus event always so listeners can refresh icons.
        systemDarkMedia.addEventListener("change", () => dispatch());

        const setMode = async (newMode) => {
            if (!VALID_MODES.includes(newMode)) return;
            mode = newMode;
            dispatch();
            try {
                await orm.write(
                    "res.users",
                    [user.userId],
                    { myschool_theme_mode: newMode },
                );
            } catch (e) {
                console.warn("myschool_theme: could not persist user pref:", e);
            }
        };

        const cycle = () => {
            const order = ["auto", "dark", "light"];
            const next = order[(order.indexOf(mode) + 1) % order.length];
            return setMode(next);
        };

        return {
            bus,
            get mode() { return mode; },
            get effective() { return resolveEffective(mode, systemDarkMedia.matches); },
            setMode,
            cycle,
        };
    },
};

registry.category("services").add("myschool_theme", themeService);
