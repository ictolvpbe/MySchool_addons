/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Listener voor de aangepaste bus-notificatie 'professionalisering_address_review'.
 * Toont een toast met een "Naar adressen"-knop die direct de gefilterde lijst opent.
 */
const addressReviewListener = {
    dependencies: ["bus_service", "action", "notification"],
    start(env, { bus_service, action, notification }) {
        bus_service.subscribe("professionalisering_address_review", (payload) => {
            notification.add(payload.message || "", {
                title: payload.title || "Nieuw adres",
                type: "info",
                sticky: true,
                buttons: [
                    {
                        name: "Naar adressen",
                        primary: true,
                        onClick: () => {
                            // Gefilterde-variant heeft een hard-coded domain
                            // (needs_review = True), dus altijd correct gefilterd.
                            action.doAction(
                                "professionalisering.action_professionalisering_addresses_review"
                            );
                        },
                    },
                ],
            });
        });
    },
};

registry
    .category("services")
    .add("professionalisering_address_review_listener", addressReviewListener);
