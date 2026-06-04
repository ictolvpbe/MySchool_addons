"""Koppelt een password.policy aan een school-org. Apart bestand zodat
de hoofd-org.py overzichtelijk blijft."""
from odoo import fields, models


class OrgPasswordPolicy(models.Model):
    _inherit = 'myschool.org'

    password_policy_id = fields.Many2one(
        'myschool.password.policy',
        string='Wachtwoordbeleid',
        ondelete='set null',
        help='Beleid dat bepaalt hoe wachtwoorden voor leerlingen / '
             'medewerkers binnen deze school worden gegenereerd of gekozen. '
             'Enkel betekenisvol op school-niveau-orgs.',
    )
