import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class KostenDashboard(models.Model):
    _name = 'kosten.dashboard'
    _description = 'Kosten Dashboard'

    name = fields.Char(default='Kosten Dashboard')

    # KPI fields
    kpi_totale_kost = fields.Float(string='Totale kost', compute='_compute_kpis')
    kpi_aantal_medewerkers = fields.Integer(string='Medewerkers', compute='_compute_kpis')
    kpi_gemiddelde_kost = fields.Float(string='Gemiddelde kost', compute='_compute_kpis')
    kpi_kost_activiteiten = fields.Float(string='Kost activiteiten', compute='_compute_kpis')
    kpi_kost_prof = fields.Float(string='Kost professionalisering', compute='_compute_kpis')
    kpi_aantal_activiteiten = fields.Integer(string='Aantal activiteiten', compute='_compute_kpis')
    kpi_aantal_prof = fields.Integer(string='Aantal prof.', compute='_compute_kpis')
    kpi_aantal_totaal = fields.Integer(string='Totaal items', compute='_compute_kpis')

    # Top spenders HTML
    top_spenders_html = fields.Html(string='Top kosten', compute='_compute_top_spenders', sanitize=False)

    @api.depends_context('uid')
    def _compute_kpis(self):
        for rec in self:
            data = self.env['kosten.per.medewerker'].sudo().search_read(
                [], ['totale_kost', 'kost_activiteiten', 'kost_prof',
                     'aantal_activiteiten', 'aantal_prof'])
            rec.kpi_totale_kost = sum(d['totale_kost'] for d in data)
            rec.kpi_aantal_medewerkers = len(data)
            rec.kpi_gemiddelde_kost = (
                rec.kpi_totale_kost / rec.kpi_aantal_medewerkers
                if rec.kpi_aantal_medewerkers else 0
            )
            rec.kpi_kost_activiteiten = sum(d['kost_activiteiten'] for d in data)
            rec.kpi_kost_prof = sum(d['kost_prof'] for d in data)
            rec.kpi_aantal_activiteiten = sum(d['aantal_activiteiten'] for d in data)
            rec.kpi_aantal_prof = sum(d['aantal_prof'] for d in data)
            rec.kpi_aantal_totaal = rec.kpi_aantal_activiteiten + rec.kpi_aantal_prof

    @api.depends_context('uid')
    def _compute_top_spenders(self):
        for rec in self:
            data = self.env['kosten.per.medewerker'].sudo().search_read(
                [], ['employee_id', 'school_id', 'totale_kost', 'kost_activiteiten', 'kost_prof'],
                order='totale_kost desc', limit=5)
            if not data:
                rec.top_spenders_html = '<div class="ms-empty">Geen kostengegevens beschikbaar</div>'
                continue

            max_kost = data[0]['totale_kost'] if data else 1
            rows = []
            for i, d in enumerate(data, 1):
                name = d['employee_id'][1] if d['employee_id'] else 'Onbekend'
                school = d['school_id'][1] if d['school_id'] else ''
                pct = (d['totale_kost'] / max_kost * 100) if max_kost else 0
                rows.append(f'''
                    <tr>
                        <td class="ms-rank">{i}</td>
                        <td>
                            <div class="ms-name">{name}</div>
                            <div class="ms-school">{school}</div>
                        </td>
                        <td class="ms-amount">
                            &euro; {d['totale_kost']:,.2f}
                            <div class="ms-cost-bar-bg">
                                <div class="ms-cost-bar" style="width: {pct:.0f}%"></div>
                            </div>
                        </td>
                    </tr>
                ''')

            rec.top_spenders_html = f'<table class="ms-top-table">{"".join(rows)}</table>'

    def action_open_kosten_medewerker(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Kosten per medewerker',
            'res_model': 'kosten.per.medewerker',
            'view_mode': 'list,form,pivot,graph',
            'target': 'current',
        }

    def action_open_kosten_detail(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Kosten detail',
            'res_model': 'kosten.detail',
            'view_mode': 'list,pivot',
            'target': 'current',
        }

    def action_open_kosten_pivot(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Kosten per medewerker',
            'res_model': 'kosten.per.medewerker',
            'view_mode': 'pivot,list,graph',
            'target': 'current',
        }

    def action_open_kosten_graph(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Kosten per medewerker',
            'res_model': 'kosten.per.medewerker',
            'view_mode': 'graph,list,pivot',
            'target': 'current',
        }

    # --- Optional module integration ---

    _OPTIONAL_GROUP_LINKS = [
        ('activiteiten.group_activiteiten_directie', 'kosten_dashboard.group_kosten_user'),
        ('activiteiten.group_activiteiten_admin', 'kosten_dashboard.group_kosten_admin'),
        ('professionalisering.group_professionalisering_directie', 'kosten_dashboard.group_kosten_user'),
        ('professionalisering.group_professionalisering_admin', 'kosten_dashboard.group_kosten_admin'),
    ]

    @api.model
    def _register_hook(self):
        super()._register_hook()
        try:
            # Recreate SQL views with current module availability
            self.env['kosten.per.medewerker'].init()
            self.env['kosten.detail'].init()
            # Link security groups from optional modules
            self._link_optional_groups()
        except Exception:
            _logger.warning('Failed to setup kosten dashboard optional modules', exc_info=True)

    @api.model
    def _link_optional_groups(self):
        """When activiteiten/professionalisering is installed, auto-grant kosten access."""
        for source_xmlid, target_xmlid in self._OPTIONAL_GROUP_LINKS:
            source = self.env.ref(source_xmlid, raise_if_not_found=False)
            target = self.env.ref(target_xmlid, raise_if_not_found=False)
            if source and target and target not in source.implied_ids:
                source.sudo().write({'implied_ids': [(4, target.id)]})
