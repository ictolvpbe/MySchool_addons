# my_module/services/person_service.py
from odoo import models, api, _

class PersonService(models.AbstractModel):
    _name = 'myschool.informat.service'
    _description = 'Service for managing informat '

    @api.model
    def get_all_persons_data(self):
        """
        Haalt alle records op van het persons model.persons
        """
        # We gebruiken self.env['modelnaam'] om het model te benaderen
        all_persons = self.env['my_module.persons'].search([])

        if not all_persons:
            print("Geen personen gevonden.")
            return []

        results = []
        for person in all_persons:
            results.append({
                'id': person.id,
                'name': person.name,
                'age': person.age,
            })
            print(f"Persoon gevonden: {person.name} (ID: {person.id})")

        return results

