"""Offline editorial/selector contracts; no real episode is rendered or consumed."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import renovation_series as series
import renovation_knowledge as knowledge


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.plan = series.read(series.PLAN)

    def test_exact_100_interleaved_editorial_questions(self):
        result = series.verify(self.plan)
        self.assertEqual((result['episodes'], result['domains']), (100, 25))
        self.assertFalse(result['production_ready_claimed'])

    def test_duplicate_title_is_not_content_diversity(self):
        self.plan['episodes'][1]['title'] = self.plan['episodes'][0]['title']
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_EPISODE_TITLE'):
            series.verify(self.plan)

    def test_unregistered_source_is_rejected(self):
        self.plan['episodes'][0]['source_anchor_ids'] = ['unread-source']
        with self.assertRaisesRegex(ValueError, 'SOURCE_ANCHOR_MISSING'):
            series.verify(self.plan)

    def test_next_is_read_only_and_needs_real_card_admission(self):
        usage = {'used': []}
        before = copy.deepcopy((self.plan, usage))
        result = series.next_episode(self.plan, usage, {'cards': []}, '2026-10-14')
        self.assertEqual(result['episode']['id'], 'E001')
        self.assertTrue(result['research_admission_required'])
        self.assertEqual(before, (self.plan, usage))

    def test_hold_is_not_consumption_and_can_select_other_domain(self):
        result = series.next_episode(self.plan, {'used': []}, {'cards': []}, '2026-10-14', ['E001'])
        self.assertEqual(result['episode']['id'], 'E002')
        self.assertEqual(result['rendered_count'], 0)

    def test_unknown_exclusion_rejected(self):
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EXCLUDED_EPISODE'):
            series.next_episode(self.plan, {'used': []}, {'cards': []}, '2026-10-14', ['E999'])

    def test_daily_render_cap_uses_canonical_adoption_not_calendar_pointer(self):
        row = {'task_id': self.plan['episodes'][0]['production_task_id'], 'used_at': '2026-10-14'}
        with mock.patch.object(series, 'actual_series_rows', return_value=[row]):
            result = series.next_episode(self.plan, {'used': []}, {'cards': []}, '2026-10-14')
        self.assertEqual(result['status'], 'NO_CHANGE_DATE_ALREADY_RENDERED')
        self.assertTrue(result['do_not_create_second_video_today'])

    def test_100_actual_rendered_stops_but_does_not_claim_independent_pass(self):
        rows = [{'task_id': e['production_task_id'], 'used_at': '2026-10-14'} for e in self.plan['episodes']]
        with mock.patch.object(series, 'actual_series_rows', return_value=rows):
            result = series.next_episode(self.plan, {'used': []}, {'cards': []}, '2027-01-22')
        self.assertEqual(result['status'], 'SERIES_RENDERING_COMPLETE_STOP_SCHEDULE')
        self.assertEqual(result['independent_acceptance'], 'NOT_INFERRED')
        self.assertFalse(result['published'])

    def test_series_paths_cannot_escape_project(self):
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_PROJECT'):
            series.read('/private/tmp/outside-series.json')


class ExactKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.bank = knowledge.read(knowledge.BANK_PATH)
        self.state_dir = series.ROOT / 'drafts/creative/fc-20261014-renovation-pain-100ep-plan-v1/plan-v1/runtime/test-tmp'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.card = next(c for c in self.bank['cards'] if 'renovation_mistake_guide' in c['supported_products'])

    def pick(self, **kwargs):
        return knowledge.choose(self.bank, {'used': []}, self.state_dir, 'renovation_mistake_guide', **kwargs)

    def test_exact_topic_selected_without_replacing_scope_or_consuming(self):
        result = self.pick(topic_id=self.card['id'], context='any')
        self.assertEqual(result['topic']['id'], self.card['id'])
        self.assertEqual(result['status'], 'PROPOSED_NOT_ADOPTED')

    def test_unknown_exact_card_never_silently_falls_back(self):
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EXPLICIT_TOPIC_ID'):
            self.pick(topic_id='not-an-admitted-card')

    def test_exact_card_still_obeys_scene(self):
        other = next(s['key'] for s in self.bank['scenes'] if s['key'] != self.card['scene_key'])
        with self.assertRaisesRegex(ValueError, 'NO_COMPATIBLE_TOPIC'):
            self.pick(topic_id=self.card['id'], scene=other, context='any')

    def test_exact_card_does_not_bypass_recent_semantic_dedup(self):
        usage = {'used': [{'task_id': 'fixture-used', 'used_at': '2026-10-14', 'semantic_key': self.card['semantic_key']}]}
        with self.assertRaisesRegex(ValueError, 'CONTENT_POOL_EXHAUSTED'):
            knowledge.choose(self.bank, usage, self.state_dir, 'renovation_mistake_guide', context='any', topic_id=self.card['id'])

    def test_rework_cannot_replace_already_used_topic(self):
        args = SimpleNamespace(task_id='fixture-used', product_type='renovation_mistake_guide', topic_id='new-card')
        usage = {'used': [{'task_id': args.task_id, 'product_type': args.product_type, 'topic_id': self.card['id']}]}
        with self.assertRaisesRegex(ValueError, 'TASK_TOPIC_CONFLICT'):
            knowledge.select(args, self.bank, usage, self.state_dir)

    def test_parser_exposes_exact_card_only_on_peek(self):
        args = knowledge.parser().parse_args(['peek', '--product-type', 'renovation_mistake_guide', '--topic-id', self.card['id']])
        self.assertEqual(args.topic_id, self.card['id'])


if __name__ == '__main__':
    unittest.main()
