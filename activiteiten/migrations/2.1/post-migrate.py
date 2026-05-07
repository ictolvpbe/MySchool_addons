import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migratie naar 2.1: heeft_overnachting is nieuw en gate't de
    annulatieverzekering 2%. Voor bestaande activiteiten waar de
    verzekering al toegepast was (verzekering_done=True), nemen we aan
    dat er overnachting was en zetten we de flag op True. Anders zou
    de verzekering bij volgende S-Code-bevestiging onterecht weggehaald
    worden.
    """
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'activiteiten_record'
          AND column_name = 'heeft_overnachting'
    """)
    if not cr.fetchone():
        _logger.warning('[activiteiten 2.1] heeft_overnachting kolom ontbreekt, skip')
        return
    cr.execute("""
        UPDATE activiteiten_record
        SET heeft_overnachting = TRUE
        WHERE verzekering_done = TRUE
          AND (heeft_overnachting IS NULL OR heeft_overnachting = FALSE)
    """)
    n = cr.rowcount
    _logger.info(
        '[activiteiten 2.1] heeft_overnachting=True gezet op %d records '
        'met bestaande verzekering', n,
    )
