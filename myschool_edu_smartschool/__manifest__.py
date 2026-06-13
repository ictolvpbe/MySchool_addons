# -*- coding: utf-8 -*-
{
    'name': 'MySchool Edu — Smartschool',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Smartschool-connector (provisioning + config) als edu-plugin op myschool_core',
    'description': """
Smartschool-integratie als connector-plugin.

Bevat de SMARTSCHOOL/USER/* betask-handlers + cascade-emitters (geextraheerd
uit myschool_core) en haakt ze terug aan via de connector-extensiepunten op
myschool.betask.processor. myschool_core bevat zelf geen Smartschool-logica meer.
""",
    'author': 'OLVP ICT',
    'license': 'LGPL-3',
    'depends': ['myschool_core'],
    'data': [
        'security/ir.model.access.csv',
        'data/smartschool_task_types.xml',
        'views/smartschool_config_views.xml',
    ],
    'installable': True,
    'application': False,
}
