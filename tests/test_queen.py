"""Stage behavior tests: no microphone, speakers or serial device required."""
import copy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from queen_robot.queen_script import load_script, validate_script
from queen_robot.queen_state import QueenState
from queen_robot.queen_actions import QueenActions


class Recorder:
    def __init__(self, fail=None):
        self.events = []
        self.fail = fail

    def execute(self, step):
        self.events.append(step)
        if self.fail is not None and step.get('audio') == self.fail:
            raise RuntimeError('playback failed')


class QueenTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script()
        self.actions = Recorder()
        self.engine = QueenState(self.script, self.actions)

    def test_complete_show_uses_revised_voices_and_all_five_dances(self):
        self.engine.start()
        for line in self.script['demo_inputs']:
            self.assertTrue(self.engine.handle(line), (self.engine.state, line))
        self.assertEqual(self.engine.state, 'ENDING')
        events = self.actions.events
        self.assertEqual([e['dance'] for e in events if 'dance' in e],
                         ['act1', 'act2', 'act3', 'act4', 'act5'])
        voices = [e['audio'] for e in events if 'audio' in e and e['audio'][0].isdigit()]
        self.assertEqual(voices, ['1-1', '1-3', '1-4', '2-1', '2-2', '2-3', '2-4',
                                  '3-1', '4-2', '4-3', '5-3'])
        self.assertEqual([e['audio'] for e in events if e.get('audio', '').startswith('bgm')],
                         ['bgm1', 'bgm2', 'bgm3', 'bgm4', 'bgm5'])
        self.assertEqual(len(self.script['demo_inputs']), 11)
        for number in (2, 3, 4):
            dance_index = events.index({'dance': f'act{number}'})
            self.assertEqual(events[dance_index + 1], {'audio': f'bgm{number}'})
        self.assertFalse(self.engine.handle('蜂后'))

    def test_wrong_duplicate_and_negative_cues_do_not_advance(self):
        self.engine.start()
        self.assertFalse(self.engine.handle('执行机体自检'))
        self.assertTrue(self.engine.handle('蜂后，蜂后！'))
        self.assertFalse(self.engine.handle('蜂后'))
        self.assertFalse(self.engine.handle('不要执行机体自检'))
        self.assertEqual(self.engine.state, 'SELF_CHECK')
        self.assertTrue(self.engine.handle('蜂后，执行机体自检。'))
        before = len(self.actions.events)
        self.assertFalse(self.engine.handle('蜂后执行机体自检'))
        self.assertEqual(len(self.actions.events), before)

    def test_visual_sequence_is_automatic_and_uses_configured_gaps(self):
        self.script['timing']['vision_first_seconds'] = 2
        self.script['timing']['vision_change_seconds'] = 9
        engine = QueenState(self.script, self.actions, 'VISION_START')
        engine.start()
        self.assertTrue(engine.handle('启动环境视觉识别系统'))
        self.assertEqual(engine.state, 'TRAVEL')
        self.assertEqual([e['audio'] for e in self.actions.events if 'audio' in e],
                         ['2-1','se-3','2-2','se-4','2-3','se-5','2-4'])
        self.assertEqual([e['wait'] for e in self.actions.events if 'wait' in e], [2,9,9])

    def test_failure_latches_error_without_repeating_action(self):
        engine = QueenState(self.script, Recorder('1-3'), 'SELF_CHECK')
        with self.assertRaisesRegex(RuntimeError, 'playback failed'):
            engine.handle('执行机体自检')
        self.assertEqual(engine.state, 'ERROR')
        self.assertEqual(engine.failed_state, 'SELF_CHECK')
        count = len(engine.actions.events)
        self.assertFalse(engine.handle('执行机体自检'))
        self.assertEqual(len(engine.actions.events), count)

    def test_config_rejects_broken_targets_cycles_timings_and_assets(self):
        for change in [
            lambda s: s['states']['BOOT'].update(next='MISSING'),
            lambda s: s['states']['VISION_FLOWER'].update(next='VISION_DESERT'),
            lambda s: s['timing'].update(vision_first_seconds=-1),
            lambda s: s['timing'].update(vision_first_seconds=float('nan')),
            lambda s: s['states']['BOOT']['steps'].append({'audio':'absent'}),
        ]:
            with self.subTest(change=change):
                script = copy.deepcopy(self.script)
                change(script)
                with self.assertRaises(ValueError):
                    validate_script(script)

    def test_entry_runs_outside_project_and_demo_is_safe(self):
        entry = ROOT/'queen_robot'/'main_queen.py'
        result = subprocess.run([sys.executable, '-X', 'utf8', str(entry), '--dry-run', '--demo'],
                                cwd=ROOT.parent, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('ENDING', result.stdout)
        result = subprocess.run([sys.executable, str(entry), '--demo'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script()

    def test_dry_run_never_opens_player_or_serial(self):
        with patch('queen_robot.queen_actions.subprocess.Popen') as popen:
            actions = QueenActions(self.script, dry_run=True)
            actions.execute({'audio':'1-1'})
            actions.execute({'dance':'act1'})
            actions.execute({'wait':50})
            popen.assert_not_called()

    def test_serial_failure_stops_music(self):
        proc = Mock()
        proc.poll.return_value = None
        fake_serial = Mock()
        fake_serial.send_serial_data.return_value = False
        with patch.dict(sys.modules, {'serial_link':fake_serial}), \
             patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            actions = QueenActions(self.script)
            with self.assertRaisesRegex(RuntimeError, '应答'):
                actions.execute({'dance':'act1'})
            proc.terminate.assert_called_once()
            packet = fake_serial.send_serial_data.call_args.args[1]
            self.assertEqual(bytes(packet[7:-1]), b'act1.odr')

    def test_dance_waits_for_music_after_ack(self):
        proc = Mock()
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        fake_serial = Mock()
        fake_serial.send_serial_data.return_value = True
        with patch.dict(sys.modules, {'serial_link':fake_serial}), \
             patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            QueenActions(self.script).execute({'dance':'act3'})
            proc.wait.assert_called_once()

    def test_audio_failure_does_not_succeed(self):
        proc = Mock()
        proc.wait.return_value = 1
        proc.poll.return_value = 1
        with patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            with self.assertRaisesRegex(RuntimeError, '播放失败'):
                QueenActions(self.script).execute({'audio':'1-1'})

    def test_player_timeout_cleans_up(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('player', 240), 0]
        with patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            with self.assertRaisesRegex(RuntimeError, '超时'):
                QueenActions(self.script).execute({'audio':'1-1'})
            proc.terminate.assert_called_once()

    def test_keyboard_interrupt_cleans_up_music(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [KeyboardInterrupt, 0]
        with patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            with self.assertRaises(KeyboardInterrupt):
                QueenActions(self.script).execute({'audio':'1-1'})
            proc.terminate.assert_called_once()

    def test_silent_actions_waits_for_music_without_serial(self):
        proc = Mock()
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        fake_serial = Mock()
        with patch.dict(sys.modules, {'serial_link':fake_serial}), \
             patch('queen_robot.queen_actions.shutil.which', return_value='player'), \
             patch('queen_robot.queen_actions.subprocess.Popen', return_value=proc):
            QueenActions(self.script, silent_actions=True).execute({'dance':'act2'})
            proc.wait.assert_called_once()
            fake_serial.get_serial.assert_not_called()


class SpeechTests(unittest.TestCase):
    def test_stage_can_record_longer_without_stage_beeps(self):
        import speech_recog
        with patch.object(speech_recog, 'record_wav') as record, \
             patch.object(speech_recog, 'prepare_listening'), \
             patch.object(speech_recog, 'resolve_asr_backend', return_value='sherpa'), \
             patch.object(speech_recog, '_sherpa_transcribe', return_value='蜂后 执行机体自检'):
            text = speech_recog.speech_recog(seconds=8, cue=False)
            self.assertEqual(text, '蜂后执行机体自检')
            self.assertEqual(record.call_args.args[1], 8)
            self.assertEqual(record.call_args.kwargs, {'cue': False})

    def test_old_speech_call_keeps_record_duration_and_cues(self):
        import speech_recog
        with patch.object(speech_recog, 'record_wav') as record, \
             patch.object(speech_recog, 'prepare_listening'), \
             patch.object(speech_recog, 'resolve_asr_backend', return_value='sherpa'), \
             patch.object(speech_recog, '_sherpa_transcribe', return_value='前进'):
            self.assertEqual(speech_recog.speech_recog(), '前进')
            self.assertEqual(record.call_args.args[1], 3.75)
            self.assertTrue(record.call_args.kwargs.get('cue', True))


if __name__ == '__main__':
    unittest.main()
