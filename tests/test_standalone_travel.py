"""单句跨流程执行：使用真实匹配和状态机，不打开外设。"""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from queen_robot.main_queen import run_dialog
from queen_robot.queen_script import load_script
from queen_robot.queen_state import QueenState

TRAVEL = '蜂后，前往目标区域，执行生态巡查任务。'


class StandaloneTravelTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script()

    def engine(self, state='SELF_CHECK', actions=None):
        engine = QueenState(self.script, actions or Mock(), state)
        engine.start()
        return engine

    def test_cross_flow_runs_only_travel_steps_and_retains_every_waiting_state(self):
        for state, node in self.script['states'].items():
            if state in ('BOOT', 'TRAVEL', 'ENDING') or node.get('auto'):
                continue
            with self.subTest(state=state):
                engine = self.engine(state)
                before = engine.prompt
                self.assertTrue(engine.handle(TRAVEL))
                self.assertEqual(engine.state, state)
                self.assertEqual(engine.prompt, before)
                self.assertFalse(engine.busy)
                self.assertIsNone(engine.failed_state)
                self.assertEqual([call.args[0] for call in engine.actions.execute.call_args_list],
                                 [{'dance': 'act2'}, {'audio': 'bgm2'}])

    def test_explicit_short_command_and_full_homophone_are_accepted(self):
        for text in ('前往目标区域', '丰后前往目标区域', '丰厚前往目标区域执行生态巡查任务'):
            with self.subTest(text=text):
                engine = self.engine()
                self.assertTrue(engine.handle(text))
                self.assertEqual(engine.state, 'SELF_CHECK')

    def test_same_explicit_command_can_be_repeated_after_completion(self):
        engine = self.engine()
        self.assertTrue(engine.handle(TRAVEL))
        self.assertTrue(engine.handle(TRAVEL))
        self.assertEqual(engine.state, 'SELF_CHECK')
        self.assertEqual(engine.actions.execute.call_count, 4)

    def test_normal_travel_still_advances_to_restore(self):
        engine = self.engine('TRAVEL')
        self.assertTrue(engine.handle(TRAVEL))
        self.assertEqual(engine.state, 'RESTORE')
        self.assertEqual(engine.actions.execute.call_count, 2)

    def test_unrelated_keywords_negatives_and_truncated_lines_are_rejected(self):
        for text in ('生态巡查', '前往目标区', '不前往目标区域', '别前往目标区域',
                     '不要前往目标区域', '取消前往目标区域', '前往目标区域吗',
                     '刚才说前往目标区域', '前往目标区域执行生态巡查任务不要执行',
                     '前往目标区域执行生态巡逻任务', '生命之舞', '花海巡礼', '怎么做'):
            with self.subTest(text=text):
                engine = self.engine()
                self.assertFalse(engine.handle(text))
                self.assertEqual(engine.state, 'SELF_CHECK')
                engine.actions.execute.assert_not_called()

    def test_original_cue_still_works_after_return(self):
        engine = self.engine()
        self.assertTrue(engine.handle(TRAVEL))
        self.assertTrue(engine.handle('执行机体自检'))
        self.assertEqual(engine.state, 'SEARCH')

    def test_pre_wake_finished_and_error_states_do_not_accept_travel(self):
        for state in ('BOOT', 'ENDING', 'ERROR'):
            with self.subTest(state=state):
                engine = QueenState(self.script, Mock())
                engine.state = state
                self.assertFalse(engine.handle(TRAVEL))
                engine.actions.execute.assert_not_called()

    def test_reentrant_command_is_not_queued_during_action(self):
        engine = self.engine()
        rejected = []
        engine.actions.execute.side_effect = lambda step: rejected.append(engine.handle(TRAVEL))
        self.assertTrue(engine.handle(TRAVEL))
        self.assertEqual(rejected, [False, False])
        self.assertEqual(engine.actions.execute.call_count, 2)

    def test_failure_stops_and_identifies_travel_without_replaying_it(self):
        for failure in (RuntimeError('serial timeout'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                engine = self.engine()
                engine.actions.execute.side_effect = failure
                with self.assertRaises(type(failure)):
                    engine.handle(TRAVEL)
                self.assertEqual(engine.state, 'ERROR')
                self.assertEqual(engine.failed_state, 'TRAVEL')
                self.assertFalse(engine.busy)
                self.assertFalse(engine.handle(TRAVEL))
                engine.actions.execute.assert_called_once()

    def test_return_uses_one_new_turn_ding_and_does_not_ding_for_retry(self):
        engine = self.engine()
        cues = []
        lines = iter([TRAVEL, '随便聊天'])

        def listen(*, cue):
            cues.append(cue)
            try:
                return next(lines)
            except StopIteration:
                raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_dialog(engine, listen)
        self.assertEqual(cues, [True, True, False])
        self.assertEqual(engine.state, 'SELF_CHECK')

    def test_main_entry_can_call_travel_and_then_resume_original_cue_without_hardware(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(root / 'main.py'), '--dry-run', '--start-state', 'SELF_CHECK'],
            input='前往目标区域\n执行机体自检\n', text=True, encoding='utf-8',
            capture_output=True, timeout=15,
        )
        # 输入用尽后按普通手动退出处理，不触发下一段真实动作。
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assertIn('[独立调用] TRAVEL', result.stdout)
        self.assertIn('[返回等待] SELF_CHECK', result.stdout)
        self.assertIn('[模拟] dance: act2', result.stdout)
        self.assertIn('[模拟] dance: act1', result.stdout)
        self.assertIn('等待 SEARCH', result.stdout)


if __name__ == '__main__':
    unittest.main()
