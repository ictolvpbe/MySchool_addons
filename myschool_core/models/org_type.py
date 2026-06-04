from odoo import models, fields

# ----------------------------------------------------------------------
# myschool.org.type (OrgType.java)
class OrgType(models.Model):
    _name = 'myschool.org.type'
    _description = 'Organisatie Type'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    is_active = fields.Boolean(string='Actief', default=False)

    # Visual identity. The object browser prefers ``icon_image`` (if set)
    # over ``icon_fa_class`` over the generic per-type fallback in the JS.
    icon_image = fields.Binary(
        string='Icoon',
        help='Optioneel pictogram voor dit org-type (klein, vierkant, '
             'transparante achtergrond werkt het best).')
    icon_fa_class = fields.Char(
        string='Font Awesome class',
        help='Fallback-icoon wanneer geen afbeelding is geüpload, bv. '
             '"fa fa-graduation-cap". Wordt gebruikt door de Organisation '
             'Manager voor tree-, members- en details-views.')
    # Hex color string (#rrggbb). Frontend tint-formule maakt er een lichte
    # achtergrond van met alpha — werkt in zowel light als dark mode.
    icon_color = fields.Char(
        string='Icoonkleur',
        help='Hex-kleur (#rrggbb) voor het icoon van dit type. '
             'De Organisation Manager kleurt het icoon zelf en het '
             'avatar-achtergrondtintje. Leeg = brand-kleur als default.')