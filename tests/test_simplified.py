"""精简后入口、唤醒交接、独立动作及隔离边界的回归测试。"""
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from action_catalog import load_actions, get_action
from queen_robot.queen_actions import QueenActions
from queen_robot.queen_script import load_script
from queen_robot.queen_state import QueenState
from queen_robot.main_queen import run_dialog


class SimplifiedTests(unittest.TestCase):
    def test_full_show_wakes_once_then_uses_script_cues(self):
        script = load_script()
        events = []
        actions = Mock()
        actions.execute.side_effect = lambda step: events.append(step)
        engine = QueenState(script, actions)
        lines = iter(script['demo_inputs'][1:])
        wake = Mock(side_effect=lambda: events.append('wake'))
        run_dialog(engine, lambda **kwargs: next(lines), wake)
        self.assertEqual(events[0], 'wake')
        self.assertEqual(engine.state, 'ENDING')
        wake.assert_called_once()
        self.assertEqual([e['dance'] for e in events if isinstance(e, dict) and 'dance' in e],
                         ['act1','act2','act3','act4','act5'])

    def test_resume_wakes_before_any_automatic_action(self):
        script = load_script()
        actions = Mock()
        engine = QueenState(script, actions, 'VISION_DESERT')
        def interrupt():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run_dialog(engine, Mock(), interrupt)
        actions.execute.assert_not_called()

    def test_all_independent_actions_send_the_correct_file_and_wait(self):
        catalog = load_actions()
        self.assertEqual(len(catalog), 18)
        for action in catalog:
            with self.subTest(action=action['id']):
                events = []
                serial = Mock()
                def send(ser, packet, timeout):
                    events.append('send')
                    self.assertEqual(bytes(packet[7:-1]).decode('ascii'), action['file'])
                    self.assertEqual(packet[:5], [255, 0, 5, 5, 0])
                    self.assertEqual(packet[5], len(action['file']))
                    self.assertEqual(packet[6], 14 if action['file'].endswith('.odr') else 9)
                    self.assertEqual(packet[-1], sum(packet[:-1]) % 255)
                    self.assertEqual(timeout, action['timeout_seconds'])
                    return True
                serial.send_serial_data.side_effect = send
                with patch.dict(os.environ, {'PI_SERIAL_DRYRUN':'0'}), \
                     patch.dict(sys.modules, {'serial_link':serial}):
                    runner = QueenActions(load_script())
                    runner._play = Mock(side_effect=lambda name: events.append('play'))
                    runner._wait_player = Mock(side_effect=lambda: events.append('wait'))
                    runner.run_action(action)
                    self.assertEqual(events, ['play','send','wait'] if action['parallel_audio']
                                     else ['play','wait','send'])
                    runner.close()
                    serial.close_serial.assert_called_once()

    def test_unknown_action_cannot_send_a_filename(self):
        with self.assertRaises(ValueError):
            get_action('../something.odr')

    def test_unified_cli_runs_from_elsewhere_without_hardware(self):
        for args, expected in [(['--check'], '18'), (['--list-actions'], 'act5'),
                               (['--dry-run','--demo'], 'ENDING'),
                               (['--action','act3','--dry-run'], 'act3.odr'),
                               (['--action','前进','--dry-run'], 'scwforward.odr')]:
            result = subprocess.run([sys.executable, '-X','utf8',str(ROOT/'main.py'),*args],
                                    cwd=ROOT.parent, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(expected, result.stdout)

    def test_active_code_does_not_import_isolated_modules(self):
        banned = {'cv2','mediapipe','sklearn','librosa','dtw','vosk','snowboydecoder',
                  'action_pose','action_rhythm','action_neo','action_loop','rhythm_recog',
                  'rhythm_features','config','intent','flow','posture_recognition'}
        for path in ROOT.rglob('*.py'):
            if '.venv' in path.parts or 'tests' in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                names = ([x.name for x in node.names] if isinstance(node, ast.Import)
                         else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    self.assertNotIn(name.split('.')[0], banned, str(path))
        for package in ('opencv','mediapipe','librosa','vosk','scikit-learn'):
            self.assertNotIn(package, (ROOT/'requirements.txt').read_text(encoding='utf-8'))

    def test_doctor_reports_missing_dependencies_without_crashing(self):
        from scripts import pi_doctor
        import contextlib
        import io
        output = io.StringIO()
        with patch.object(pi_doctor.importlib, 'import_module', side_effect=ImportError('missing test dependency')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(pi_doctor.main([]), 1)
        self.assertIn('missing test dependency', output.getvalue())
        self.assertIn('检查完成', output.getvalue())


class WakeTests(unittest.TestCase):
    def run_wake(self, *, fail_open=False, fail_read=False):
        import numpy  # Load before patch.dict restores sys.modules.
        import wake
        audio = Mock()
        mic = Mock(rate=16000, frames_per_buffer=1600)
        mic.stream.read.return_value = b'\x00\x00' * 1600
        if fail_read:
            mic.stream.read.side_effect = OSError('microphone disconnected')
        pyaudio = Mock()
        pyaudio.PyAudio.return_value = audio
        kws = Mock()
        kws.detect.side_effect = ['', '蜂后']
        with patch.dict(sys.modules, {'pyaudio':pyaudio}), \
             patch('sherpa_speech.KwsDetector', return_value=kws), \
             patch.object(wake, 'play_listening_cue'), \
             patch.object(wake, 'open_input_stream', side_effect=OSError('cannot open') if fail_open else None,
                          return_value=mic):
            try:
                return wake.wait_for_wake()
            finally:
                audio.terminate.assert_called_once()
                if not fail_open:
                    mic.stream.close.assert_called_once()

    def test_wake_returns_and_releases_microphone(self):
        self.assertEqual(self.run_wake(), '蜂后')

    def test_wake_read_error_is_reported_and_releases_microphone(self):
        with self.assertRaisesRegex(OSError, 'disconnected'):
            self.run_wake(fail_read=True)

    def test_wake_open_error_releases_audio_driver(self):
        with self.assertRaisesRegex(OSError, 'cannot open'):
            self.run_wake(fail_open=True)

    def test_asr_failure_is_reported_without_legacy_fallback(self):
        import speech_recog
        with patch.object(speech_recog, 'record_wav'), \
             patch.object(speech_recog, 'prepare_listening'), \
             patch.object(speech_recog, '_sherpa_transcribe', side_effect=RuntimeError('ASR failed')):
            with self.assertRaisesRegex(RuntimeError, 'ASR failed'):
                speech_recog.speech_recog()


if __name__ == '__main__':
    unittest.main()
