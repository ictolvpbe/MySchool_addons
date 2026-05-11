import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migratie naar 2.9: tussenstaat 's_code_toegekend' wordt verwijderd.
    Records die hier nog in staan, worden doorgeschoven naar 'aanwezigheid'.
    Moet pre-migrate gebeuren zodat de selectie-validatie van Odoo niet
    valt over een ongeldige waarde."""
    cr.execute("""
        SELECT COUNT(*) FROM activiteiten_record
        WHERE state = 's_code_toegekend'
    """)
    n = cr.fetchone()[0]
    if not n:
        _logger.info('[activiteiten 2.9] geen records in s_code_toegekend')
        return
    cr.execute("""
        UPDATE activiteiten_record
        SET state = 'aanwezigheid'
        WHERE state = 's_code_toegekend'
    """)
    _logger.info(
        '[activiteiten 2.9] %d records van s_code_toegekend → aanwezigheid', n,
    )
