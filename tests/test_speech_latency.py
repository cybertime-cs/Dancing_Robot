"""验证模型预热、关麦后直接识别，以及第二幕衔接等待。"""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speech_recog
from queen_robot.main_queen import main
from queen_robot.queen_script import load_script
from queen_robot.queen_state import QueenState


class SpeechLatencyTests(unittest.TestCase):
    def tearDown(self):
        prepare = getattr(speech_recog, 'prepare_listening', None)
        if callable(prepare) and hasattr(prepare, 'cache_clear'):
            prepare.cache_clear()

    def test_model_is_ready_before_waiting_for_wake(self):
        order = []
        speech = Mock()
        speech.prepare_listening.side_effect = lambda: order.append('ready')

        def wake():
            order.append('wake')
            raise KeyboardInterrupt

        with patch.dict(sys.modules, {'speech_recog': speech, 'wake': Mock(wait_for_wake=wake)}), \
             patch('queen_robot.main_queen.QueenActions'):
            self.assertEqual(main(['--silent-actions']), 130)
        self.assertEqual(order, ['ready', 'wake'])

    def test_prepare_loads_and_warms_model_once_for_all_lines(self):
        prepare = getattr(speech_recog, 'prepare_listening', None)
        self.assertTrue(callable(prepare), '缺少启动时语音模型预热')
        recognizer = Mock()
        with patch('sherpa_speech.get_asr', return_value=recognizer) as get:
            prepare()
            prepare()
        get.assert_called_once()
        recognizer.transcribe.assert_called_once()
        samples = recognizer.transcribe.call_args.args[0]
        self.assertEqual(samples.dtype, np.float32)
        self.assertGreaterEqual(len(samples), 8000)
        self.assertFalse(np.any(samples))

    def test_decoding_starts_after_capture_without_end_cue(self):
        order = []

        def record(*args, **kwargs):
            order.append('closed')

        def transcribe(path):
            self.assertIn('closed', order)
            order.append('decode')
            return '执行 机体自检'

        with patch.object(speech_recog, 'prepare_listening', create=True), \
             patch('utterance.record_utterance', side_effect=record), \
             patch.object(speech_recog, '_sherpa_transcribe', side_effect=transcribe), \
             patch('audio.play_listening_cue') as cue:
            self.assertEqual(speech_recog.listen_for_line(), '执行机体自检')
        cue.assert_not_called()
        self.assertEqual(order, ['closed', 'decode'])

    def test_failed_recognition_does_not_play_another_ding(self):
        with patch.object(speech_recog, 'prepare_listening', create=True), \
             patch('utterance.record_utterance'), \
             patch.object(speech_recog, '_sherpa_transcribe', side_effect=RuntimeError('decode failed')), \
             patch('audio.play_listening_cue') as cue:
            with self.assertRaisesRegex(RuntimeError, 'decode failed'):
                speech_recog.listen_for_line()
        cue.assert_not_called()

    def test_default_visual_sequence_has_no_more_than_six_seconds_of_wait(self):
        actions = Mock()
        engine = QueenState(load_script(), actions, 'VISION_START')
        engine.start()
        self.assertTrue(engine.handle('启动环境视觉识别系统'))
        waits = [call.args[0]['wait'] for call in actions.execute.call_args_list if 'wait' in call.args[0]]
        self.assertEqual(len(waits), 3)
        self.assertLessEqual(sum(waits), 6)
        self.assertEqual(engine.state, 'TRAVEL')


if __name__ == '__main__':
    unittest.main()
