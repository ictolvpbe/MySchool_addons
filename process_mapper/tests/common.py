from odoo.tests.common import TransactionCase


class TestProcessMapperBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.process_map = cls.env['process.map'].create({
            'name': 'Test Process',
            'description': 'A test process map',
        })

        cls.lane = cls.env['process.map.lane'].create({
            'name': 'Test Lane',
            'map_id': cls.process_map.id,
            'sequence': 10,
        })

        cls.start_step = cls.env['process.map.step'].create({
            'name': 'Start',
            'step_type': 'start',
            'map_id': cls.process_map.id,
            'lane_id': cls.lane.id,
            'x_position': 50,
            'y_position': 50,
        })

        cls.task_step = cls.env['process.map.step'].create({
            'name': 'Review Document',
            'step_type': 'task',
            'map_id': cls.process_map.id,
            'lane_id': cls.lane.id,
            'x_position': 200,
            'y_position': 50,
        })

        cls.end_step = cls.env['process.map.step'].create({
            'name': 'End',
            'step_type': 'end',
            'map_id': cls.process_map.id,
            'lane_id': cls.lane.id,
            'x_position': 400,
            'y_position': 50,
        })

        cls.env['process.map.connection'].create({
            'source_step_id': cls.start_step.id,
            'target_step_id': cls.task_step.id,
            'map_id': cls.process_map.id,
        })

        cls.env['process.map.connection'].create({
            'source_step_id': cls.task_step.id,
            'target_step_id': cls.end_step.id,
            'map_id': cls.process_map.id,
        })
