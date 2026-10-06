import copy
import importlib.util
import math
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/legacy_qc_adapter.py'
spec = importlib.util.spec_from_file_location('adapter', SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

PLAN = {'scenes': [{'id': 'one', 'start': 0, 'end': 2, 'screen_text': ['布局', '空间关系']} ]}
HTML = '''<style>.caption-cn{font-size:48px;text-shadow:0 1px 0 #fff}
.caption-label{font-size:24px}</style>
<p id="main-text" class="clip caption-cn" data-start=".1" data-duration="1.8" style="font-size:56px">空间关系</p>
<p class="clip caption-label" data-start=".1" data-duration="1.8">布局</p>'''


class CaptionTests(unittest.TestCase):
    def check(self, text=HTML, plan=PLAN):
        return adapter.caption_check(text, plan)['status']

    def test_real_roles_need_no_english_or_index(self):
        self.assertEqual(self.check(), 'PASS')

    def test_actual_inline_size_wins(self):
        n = next(n for n in adapter.Elements(HTML).nodes if n['attrs'].get('id') == 'main-text')
        self.assertEqual(adapter.font_px(HTML, n), 56)

    def test_id_specificity_wins_over_later_class(self):
        s = HTML.replace('style="font-size:56px"', '').replace('</style>', '#main-text{font-size:53px}.caption-cn{font-size:49px}</style>')
        n = next(n for n in adapter.Elements(s).nodes if n['attrs'].get('id') == 'main-text')
        self.assertEqual(adapter.font_px(s, n), 53)

    def test_small_main_fails_even_with_base48(self):
        self.assertEqual(self.check(HTML.replace('56px', '47px')), 'FAIL')

    def test_small_label_fails(self):
        self.assertEqual(self.check(HTML.replace('24px', '23px')), 'FAIL')

    def test_unresolved_css_fails(self):
        self.assertEqual(self.check(HTML.replace('56px', 'var(--font-size)')), 'FAIL')

    def test_missing_scene_caption_fails(self):
        self.assertEqual(self.check(HTML.replace('caption-cn"', 'not-caption-cn"')), 'FAIL')

    def test_unknown_extra_english_fails(self):
        self.assertEqual(self.check(HTML + '<p class="caption-en">test</p>'), 'FAIL')

    def test_duplicate_role_fails(self):
        self.assertEqual(self.check(HTML + '<p class="caption-cn">重复</p>'), 'FAIL')

    def test_copy_mismatch_fails(self):
        self.assertEqual(self.check(HTML.replace('空间关系', '已改文字')), 'FAIL')

    def test_scene_end_violation_fails(self):
        self.assertEqual(self.check(HTML.replace('1.8', '2.1')), 'FAIL')

    def test_missing_timing_fails(self):
        self.assertEqual(self.check(HTML.replace('data-start=".1"', '')), 'FAIL')

    def test_nonfinite_timing_fails(self):
        self.assertEqual(self.check(HTML.replace('data-start=".1"', 'data-start="nan"')), 'FAIL')

    def test_no_shadow_fails(self):
        self.assertEqual(self.check(HTML.replace('text-shadow:0 1px 0 #fff', 'color:white')), 'FAIL')

    def test_nested_text_is_preserved(self):
        self.assertEqual(self.check(HTML.replace('>空间关系<', '>空间<span>关系</span><')), 'PASS')

    def test_no_scenes_fails(self):
        self.assertEqual(self.check(plan={'scenes': []}), 'FAIL')


class MotionTests(unittest.TestCase):
    def test_all_six_short_scene_pairs_are_interior(self):
        for i in range(6):
            a, b = adapter.sample_times({'start': i * 2, 'end': (i + 1) * 2})
            self.assertTrue(i * 2 < a < b < (i + 1) * 2)

    def test_short_scene_fails_instead_of_crossing_cut(self):
        with self.assertRaises(ValueError):
            adapter.sample_times({'start': 0, 'end': .8})

    def test_nonfinite_scene_fails(self):
        with self.assertRaises(ValueError):
            adapter.sample_times({'start': math.nan, 'end': 2})

    def test_planned_decoded_hold_passes(self):
        self.assertEqual(adapter.pair_intent(.01, .001, True), 'PASS')

    def test_static_not_planned_as_hold_fails(self):
        self.assertEqual(adapter.pair_intent(.01, .001, False), 'FAIL')

    def test_whole_image_motion_in_hold_fails(self):
        self.assertEqual(adapter.pair_intent(8, .60, True), 'FAIL')

    def test_nonfinite_metrics_fail(self):
        self.assertEqual(adapter.pair_intent(math.nan, .1, True), 'FAIL')

    def test_full_range_pass_requires_all_frames(self):
        self.assertTrue(adapter.full_highlight_gate({'maximum_ymax':235, 'frames_decoded':720, 'frames_above235':0},720))

    def test_midpoint_pass_cannot_override_full_range_failure(self):
        self.assertFalse(adapter.full_highlight_gate({'maximum_ymax':247, 'frames_decoded':720, 'frames_above235':8},720))

    def test_missing_full_scan_cannot_pass(self):
        self.assertFalse(adapter.full_highlight_gate({},720))

    def test_incomplete_decode_cannot_pass(self):
        self.assertFalse(adapter.full_highlight_gate({'maximum_ymax':233, 'frames_decoded':60, 'frames_above235':0},720))

    def test_nonfinite_full_scan_cannot_pass(self):
        self.assertFalse(adapter.full_highlight_gate({'maximum_ymax':math.nan, 'frames_decoded':720, 'frames_above235':0},720))

    def test_negative_full_scan_cannot_pass(self):
        self.assertFalse(adapter.full_highlight_gate({'maximum_ymax':-1, 'frames_decoded':720, 'frames_above235':0},720))


if __name__ == '__main__':
    unittest.main()
