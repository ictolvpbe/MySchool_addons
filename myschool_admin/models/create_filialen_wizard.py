from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CreateFilialenWizard(models.TransientModel):
    _name = 'myschool.create.filialen.wizard'
    _description = 'Maak filialen aan vanuit scholen'

    parent_company_id = fields.Many2one(
        'res.company', string='Hoofdbedrijf',
        default=lambda self: self.env.company,
        required=True,
    )
    school_ids = fields.Many2many(
        'myschool.org', string='Scholen',
        compute='_compute_school_ids', readonly=True,
    )
    school_count = fields.Integer(compute='_compute_school_ids')
    map_users = fields.Boolean(
        string='Gebruikers koppelen aan bedrijven',
        default=True,
        help='Voeg de nieuwe bedrijven toe aan company_ids van gebruikers '
             'die de school in hun school_ids hebben.',
    )

    @api.depends('parent_company_id')
    def _compute_school_ids(self):
        OrgType = self.env['myschool.org.type']
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)
        for wiz in self:
            if not school_type:
                wiz.school_ids = False
                wiz.school_count = 0
                continue
            # Find schools not yet linked to a company
            existing_school_ids = self.env['res.company'].search([
                ('school_id', '!=', False),
            ]).mapped('school_id').ids
            schools = self.env['myschool.org'].search([
                ('org_type_id', '=', school_type.id),
                ('is_active', '=', True),
                ('is_administrative', '=', False),
                ('id', 'not in', existing_school_ids),
            ])
            wiz.school_ids = schools
            wiz.school_count = len(schools)

    def action_create_filialen(self):
        self.ensure_one()
        if not self.school_ids:
            raise UserError("Er zijn geen scholen gevonden om filialen voor aan te maken.")
        created = self.env['res.company']
        for school in self.school_ids:
            company = self.env['res.company'].create({
                'name': school.name,
                'parent_id': self.parent_company_id.id,
                'school_id': school.id,
            })
            created |= company
            _logger.info("Filiaal '%s' aangemaakt voor school '%s'", company.name, school.name)
        # Optionally map users
        if self.map_users and created:
            for company in created:
                users = self.env['res.users'].search([
                    ('school_ids', 'in', [company.school_id.id]),
                ])
                for user in users:
                    user.sudo().write({
                        'company_ids': [(4, company.id)],
                    })
                if users:
                    _logger.info(
                        "Filiaal '%s': %d gebruikers gekoppeld",
                        company.name, len(users),
                    )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Filialen aangemaakt',
                'message': '%d filialen aangemaakt.' % len(created),
                'type': 'success',
                'sticky': False,
            },
        }
