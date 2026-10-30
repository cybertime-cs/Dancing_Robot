"""验证多轮必须重新唤醒、错误不重演，以及开机音频路由。"""
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

from queen_robot.main_queen import main
from queen_robot.queen_script import load_script
from scripts import pi_service_prepare as prepare


class RepeatTests(unittest.TestCase):
    def test_completed_show_requires_new_wake_before_each_round(self):
        script = load_script()
        cues = iter(script['demo_inputs'][1:] * 2)
        wake = Mock(side_effect=['蜂后', '蜂后', KeyboardInterrupt()])
        speech = Mock()
        speech.listen_for_line.side_effect = lambda settings, **kwargs: next(cues)
        actions = []
        def make_actions(*args):
            runner = Mock()
            actions.append(runner)
            return runner
        with patch.dict(sys.modules, {'wake': Mock(wait_for_wake=wake), 'speech_recog': speech}), \
             patch('queen_robot.main_queen.QueenActions', side_effect=make_actions):
            self.assertEqual(main(['--repeat', '--silent-actions']), 130)
        self.assertEqual(wake.call_count, 3)
        self.assertTrue(all(call.kwargs['cue'] for call in speech.listen_for_line.call_args_list))
        for runner in actions[:2]:
            dances = [call.args[0]['dance'] for call in runner.execute.call_args_list if 'dance' in call.args[0]]
            self.assertEqual(dances, ['act1', 'act2', 'act3', 'act4', 'act5'])
            runner.close.assert_called_once()
        actions[2].execute.assert_not_called()
        actions[2].close.assert_called_once()

    def test_retries_do_not_ding_until_playback_finishes_and_next_turn_starts(self):
        speech = Mock()
        lines = iter(['别人的声音', '执行', '执行机体自检。'])
        cues = []

        def listen(settings, *, cue):
            cues.append(cue)
            try:
                return next(lines)
            except StopIteration:
                raise KeyboardInterrupt

        speech.listen_for_line.side_effect = listen
        with patch.dict(sys.modules, {'wake': Mock(wait_for_wake=lambda: '蜂后'), 'speech_recog': speech}), \
             patch('queen_robot.main_queen.QueenActions') as actions:
            self.assertEqual(main(['--silent-actions']), 130)
        self.assertEqual(cues, [True, False, False, True])
        steps = [call.args[0] for call in actions.return_value.execute.call_args_list]
        self.assertEqual(steps[-1], {'audio': '1-3'})

    def test_failed_show_does_not_start_another_round(self):
        speech = Mock()
        wake = Mock(wait_for_wake=Mock(return_value='蜂后'))
        with patch.dict(sys.modules, {'wake': wake, 'speech_recog': speech}), \
             patch('queen_robot.main_queen.QueenActions') as action_type:
            action_type.return_value.execute.side_effect = RuntimeError('playback failed')
            self.assertEqual(main(['--repeat', '--silent-actions']), 1)
            self.assertEqual(action_type.call_count, 1)
            wake.wait_for_wake.assert_called_once()

    def test_repeat_cannot_skip_wake_or_start_mid_show(self):
        for options in (['--dry-run'], ['--text'], ['--start-state', 'RESTORE'], ['--action', 'act1']):
            with self.subTest(options=options), self.assertRaises(SystemExit) as error:
                main(['--repeat', *options])
            self.assertEqual(error.exception.code, 2)


class PrepareTests(unittest.TestCase):
    def test_uses_named_usb_output_even_if_hdmi_is_present(self):
        nodes = [{'id': 35, 'info': {'props': {'media.class': 'Audio/Sink', 'node.description': 'HDMI'}}},
                 {'id': 80, 'info': {'props': {'media.class': 'Audio/Sink', 'node.description': 'KT USB Audio Analog Stereo'}}}]
        result = Mock(stdout=json.dumps(nodes), returncode=0)
        with patch.object(prepare.subprocess, 'run', return_value=result) as run:
            prepare.prepare_once('KT USB Audio', 0.8)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(['wpctl', 'set-default', '80'], commands)
        self.assertIn(['wpctl', 'set-volume', '80', '0.8'], commands)

    def test_missing_output_prevents_start_and_does_not_fall_back_to_hdmi(self):
        with patch.object(prepare.subprocess, 'run', return_value=Mock(stdout='[]')) as run:
            with self.assertRaisesRegex(RuntimeError, '匹配 0'):
                prepare.prepare_once('KT USB Audio', 0.8)
            self.assertEqual(run.call_count, 1)

    def test_boot_wait_retries_then_succeeds(self):
        with patch.object(prepare, 'prepare_once', side_effect=[RuntimeError('not ready'), None]) as probe, \
             patch.object(prepare.time, 'sleep') as sleep:
            self.assertEqual(prepare.main(), 0)
        self.assertEqual(probe.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_invalid_volume_is_configuration_error(self):
        with patch.dict(os.environ, {'AUDIO_VOLUME': '2.0'}), patch.object(prepare, 'prepare_once') as probe:
            self.assertEqual(prepare.main(), 1)
        probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
