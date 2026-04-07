from odoo.tests.common import TransactionCase


class TestProcessComposerBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.process_composer = cls.env['myschool.process'].create({
            'name': 'Test Process',
            'description': 'A test process map',
        })

        cls.lane = cls.env['myschool.process.lane'].create({
            'name': 'Test Lane',
            'map_id': cls.process_composer.id,
            'sequence': 10,
        })

        cls.start_step = cls.env['myschool.process.step'].create({
            'name': 'Start',
            'step_type': 'start',
            'map_id': cls.process_composer.id,
            'lane_id': cls.lane.id,
            'x_position': 50,
            'y_position': 50,
        })

        cls.task_step = cls.env['myschool.process.step'].create({
            'name': 'Review Document',
            'step_type': 'task',
            'map_id': cls.process_composer.id,
            'lane_id': cls.lane.id,
            'x_position': 200,
            'y_position': 50,
        })

        cls.end_step = cls.env['myschool.process.step'].create({
            'name': 'End',
            'step_type': 'end',
            'map_id': cls.process_composer.id,
            'lane_id': cls.lane.id,
            'x_position': 400,
            'y_position': 50,
        })

        cls.env['myschool.process.connection'].create({
            'source_step_id': cls.start_step.id,
            'target_step_id': cls.task_step.id,
            'map_id': cls.process_composer.id,
        })

        cls.env['myschool.process.connection'].create({
            'source_step_id': cls.task_step.id,
            'target_step_id': cls.end_step.id,
            'map_id': cls.process_composer.id,
        })
