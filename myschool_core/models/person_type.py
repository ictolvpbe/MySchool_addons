from odoo import models, fields

# myschool.person.type (PersonType.java)
class PersonType(models.Model):
    _name = 'myschool.person.type'
    _description = 'Persoon Type'

    name = fields.Char(string='Naam')
    is_active = fields.Boolean(string='Actief', default=False)

    # Optioneel pictogram voor personen van dit type. Persons vallen
    # standaard terug op de avatar-initialen wanneer geen image en geen
    # FA-class is ingesteld — bewust om de huidige look te behouden.
    icon_image = fields.Binary(
        string='Icoon',
        help='Optioneel pictogram voor personen van dit type. Indien leeg '
             'tonen we de gekleurde initialen-avatar (huidig gedrag).')
    icon_fa_class = fields.Char(
        string='Font Awesome class',
        help='Optioneel fallback-icoon (bv. "fa fa-graduation-cap"). '
             'Indien leeg blijft de initialen-avatar zichtbaar.')
    icon_color = fields.Char(
        string='Icoonkleur',
        help='Hex-kleur (#rrggbb) voor de avatar-achtergrond en icoon-tint '
             'van personen van dit type. Leeg = de huidige defaults '
             '(blauw voor employee, teal voor student).')