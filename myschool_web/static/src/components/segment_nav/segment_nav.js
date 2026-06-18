/** @odoo-module **/

import {
    Component,
    useState,
    useRef,
    onMounted,
    onWillUnmount,
    useExternalListener,
} from "@odoo/owl";

/**
 * SegmentNav — responsieve contextuele sub-navigatie (segment-tabs).
 *
 * Een module-eigen menu: toont zijn secties als een pill-balk. Wat niet past
 * vouwt automatisch in een "Meer ▾"-overflow-dropdown. Een ResizeObserver meet
 * de *beschikbare* breedte (de buitenste wrapper, niet de balk zelf) en schat
 * per pill de breedte; zoveel tabs als passen blijven zichtbaar, minstens één.
 * Zit de actieve tab in de overflow, dan toont de "Meer"-knop dat label en
 * licht hij op.
 *
 * Brand-neutraal: alle kleuren via de gedeelde --ms-* tokens MET fallback, dus
 * de component werkt ook zonder dat er een theme geïnstalleerd is (light + dark).
 *
 * Props:
 *   - tabs:     Array<{ key: string, label: string }>
 *   - value:    string   — key van de actieve tab
 *   - onChange: Function  — (key) => void, aangeroepen bij selectie
 *
 * Gebruik (in een ouder-component):
 *   import { SegmentNav } from "@myschool_web/components/segment_nav/segment_nav";
 *   static components = { SegmentNav };
 *   <SegmentNav tabs="sections" value="state.section" onChange="(k) => this.setSection(k)"/>
 *
 * De consumerende app declareert `myschool_web` in haar `depends` (en NIET per se
 * een theme).
 */
export class SegmentNav extends Component {
    static template = "myschool_web.SegmentNav";
    static props = {
        tabs: { type: Array },
        value: { type: String, optional: true },
        onChange: { type: Function, optional: true },
    };

    // Schatting in lijn met de design-handoff (font 13px, padding 16px/zijde).
    static GAP = 4;
    static PAD = 8;
    static MORE_W = 98;

    setup() {
        this.root = useRef("root");
        this.state = useState({ width: 0, open: false });

        onMounted(() => {
            const el = this.root.el;
            if (el && window.ResizeObserver) {
                this._ro = new ResizeObserver((entries) => {
                    const w = Math.round(entries[0].contentRect.width);
                    if (Math.abs(w - this.state.width) > 1) {
                        this.state.width = w;
                    }
                });
                this._ro.observe(el);
                this.state.width = Math.round(el.getBoundingClientRect().width);
            }
        });
        onWillUnmount(() => {
            if (this._ro) {
                this._ro.disconnect();
            }
        });

        // Sluit de overflow-dropdown bij een klik buiten het component.
        useExternalListener(window, "click", this.onWindowClick);
    }

    estWidth(label) {
        return Math.ceil((label || "").length * 7.1) + 34;
    }

    /** Verdeelt de tabs in zichtbaar vs. overflow op basis van de breedte. */
    get layout() {
        const tabs = this.props.tabs || [];
        const value = this.props.value;
        const w = this.state.width;
        const { GAP, PAD, MORE_W } = this.constructor;

        const widths = tabs.map((t) => this.estWidth(t.label));
        const total =
            widths.reduce((a, b) => a + b, 0) + GAP * Math.max(0, tabs.length - 1) + PAD;

        let visible = tabs;
        let overflow = [];
        if (w > 0 && total > w) {
            const avail = w - MORE_W - PAD;
            const vis = [];
            let acc = 0;
            for (let i = 0; i < tabs.length; i++) {
                acc += widths[i] + (i > 0 ? GAP : 0);
                if (acc <= avail) {
                    vis.push(tabs[i]);
                } else {
                    break;
                }
            }
            if (vis.length === 0) {
                vis.push(tabs[0]);
            }
            visible = vis;
            overflow = tabs.slice(vis.length);
        }

        const activeOverflow = overflow.find((t) => t.key === value);
        return {
            visible,
            overflow,
            hasOverflow: overflow.length > 0,
            moreActive: !!activeOverflow,
            moreLabel: activeOverflow ? activeOverflow.label : "Meer",
        };
    }

    selectTab(key) {
        this.state.open = false;
        (this.props.onChange || (() => {}))(key);
    }

    toggleOpen() {
        this.state.open = !this.state.open;
    }

    onWindowClick(ev) {
        if (this.state.open && this.root.el && !this.root.el.contains(ev.target)) {
            this.state.open = false;
        }
    }
}
