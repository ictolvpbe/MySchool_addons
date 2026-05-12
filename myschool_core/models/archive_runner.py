"""Centrale auto-archive runner.

Eén cron loopt dagelijks; rond `myschool.archive_date` (default
``08-15``) worden in elke beschikbare module records gearchiveerd
waarvan de afgewerkte (``done``) status meer dan één schooljaar geleden
is. Wordt automatisch overgeslagen indien het al gebeurd is dit jaar.

De datum is enkel aanpasbaar door admin gebruikers via de standaard
"Technisch → Systeemparameters" UI (Odoo beschermt die module al).
"""
import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DATE = '08-15'  # 15 augustus — net vóór nieuw schooljaar


class MyschoolArchiveRunner(models.AbstractModel):
    _name = 'myschool.archive.runner'
    _description = 'Auto-archive coordinator'

    @api.model
    def _get_archive_date(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'myschool.archive_date', DEFAULT_ARCHIVE_DATE)
        try:
            month_str, day_str = param.split('-')
            month, day = int(month_str), int(day_str)
            # Valideer met date() — gooit op ongeldige datum
            date(2000, month, day)
            return month, day
        except Exception:
            _logger.warning(
                'Ongeldige myschool.archive_date "%s" — terug naar default %s',
                param, DEFAULT_ARCHIVE_DATE)
            return 8, 15

    @api.model
    def _get_archive_cutoff(self, today=None):
        """Records ouder dan deze datum worden gearchiveerd.

        We werken in schooljaren (sept-juni). Aan het einde van de zomer
        archiveren we records van het vorige schooljaar — dat is het
        schooljaar dat eindigde meer dan één heel schooljaar geleden.
        Concreet: cutoff = 1 september van (huidig schooljaar-startjaar - 1).
        """
        today = today or fields.Date.today()
        # Huidig schooljaar start: 1 sept van dit jaar als we al voorbij
        # sept zijn, anders 1 sept van vorig jaar.
        if today.month >= 9:
            schooljaar_start_year = today.year
        else:
            schooljaar_start_year = today.year - 1
        return date(schooljaar_start_year - 1, 9, 1)

    @api.model
    def _cron_auto_archive(self):
        """Dagelijkse cron — voert archief uit één keer per jaar."""
        Param = self.env['ir.config_parameter'].sudo()
        month, day = self._get_archive_date()
        today = fields.Date.today()
        # Pas archiveren als we vandaag of later in het jaar zitten dan
        # de geconfigureerde datum.
        if (today.month, today.day) < (month, day):
            return
        last_run_year = int(Param.get_param(
            'myschool.archive_last_run_year', '0'))
        if last_run_year >= today.year:
            # Al gedaan dit jaar.
            return
        cutoff = self._get_archive_cutoff(today)
        _logger.info(
            'Auto-archive: start (cutoff=%s, modules zoeken records vóór die datum).',
            cutoff,
        )
        # Roep per module hun eigen archive aan — als de module er niet
        # is, slaan we hem stil over.
        for model_name, method in (
            ('myschool_activiteiten.record', '_auto_archive_old_done'),
            ('myschool_professionalisering.record', '_auto_archive_old_done'),
            ('myschool_drukwerk.record', '_auto_archive_old_done'),
        ):
            if model_name not in self.env:
                continue
            try:
                count = getattr(self.env[model_name], method)(cutoff)
                _logger.info(
                    'Auto-archive %s: %d records gearchiveerd.',
                    model_name, count or 0)
            except Exception as e:
                _logger.exception(
                    'Auto-archive faalde voor %s: %s', model_name, e)
        Param.set_param('myschool.archive_last_run_year', str(today.year))
        _logger.info('Auto-archive: klaar — gemarkeerd voor %s.', today.year)
