# -*- coding: utf-8 -*-
{
    'name': 'MySchool Edu — Informat connector',
    'version': '1.0',
    'category': 'MySchool',
    'summary': 'Informat (SAP) ingestie-connector als edu-plugin',
    'description': """
        MySchool Edu — Informat
        =======================
        Edition-plugin die de Informat-koppeling (onderwijs-administratie SAP)
        levert bovenop het neutrale platform. Bevat de Informat-service,
        DTO's, configuratie, de gerichte-sync-wizard en de per-school
        sync-knop. Het platform (myschool_core / myschool_admin) noemt geen
        Informat-concept meer; deze module haakt aan via de bestaande
        betask-pipeline en view-extensies.
    """,
    'author': 'MySchool OLVP',
    'website': 'https://www.olvp.be',
    'license': 'LGPL-3',
    'depends': ['myschool_core', 'myschool_admin'],
    'external_dependencies': {
        'python': ['zeep'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/informat_service_config_views.xml',
        'views/informat_sync_wizard_views.xml',
        'views/org_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        'data/sap_sync_cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
