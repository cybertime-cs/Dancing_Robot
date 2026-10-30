"""连续监听：句尾分段、短噪声、长句拒绝与设备释放。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utterance import UtteranceSegmenter, listening_settings, record_utterance

QUIET = bytes(640)
VOICE = np.full(320, 2000, dtype='<i2').tobytes()


class ListeningTests(unittest.TestCase):
    def test_microphone_name_selection_survives_device_index_changes(self):
        import os
        from audio import _input_device_index
        audio = Mock()
        audio.get_device_count.return_value = 3
        audio.get_device_info_by_index.side_effect = [
            {'name':'USB PnP', 'maxInputChannels':1},
            {'name':'C270 output', 'maxInputChannels':0},
            {'name':'C270 HD WEBCAM', 'maxInputChannels':1},
        ]
        with patch.dict(os.environ, {'MIC_DEVICE_NAME':'C270', 'MIC_DEVICE':'0'}):
            self.assertEqual(_input_device_index(audio), 2)

    def test_missing_named_microphone_does_not_fall_back_to_another(self):
        import os
        from audio import _input_device_index
        audio = Mock()
        audio.get_device_count.return_value = 1
        audio.get_device_info_by_index.return_value = {'name':'USB PnP','maxInputChannels':1}
        with patch.dict(os.environ, {'MIC_DEVICE_NAME':'C270'}):
            with self.assertRaisesRegex(RuntimeError, 'C270'):
                _input_device_index(audio)

    def test_long_silence_waits_without_unbounded_buffer(self):
        detector = UtteranceSegmenter()
        for _ in range(10000):
            self.assertIsNone(detector.feed(QUIET))
        self.assertEqual(len(detector.frames), 0)
        self.assertLessEqual(len(detector.pre), 15)

    def test_sentence_retains_onset_and_waits_for_end(self):
        detector = UtteranceSegmenter()
        for _ in range(20):
            detector.feed(QUIET)
        for _ in range(100):
            self.assertIsNone(detector.feed(VOICE))
        for _ in range(44):
            self.assertIsNone(detector.feed(QUIET))
        result = detector.feed(QUIET)
        self.assertEqual(result, QUIET * 15 + VOICE * 100 + QUIET * 45)

    def test_short_noise_is_ignored_and_next_sentence_works(self):
        detector = UtteranceSegmenter()
        for frame in [VOICE] * 3 + [QUIET] * 50:
            self.assertIsNone(detector.feed(frame))
        results = [detector.feed(frame) for frame in [VOICE] * 20 + [QUIET] * 45]
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_brief_pause_does_not_split_sentence(self):
        detector = UtteranceSegmenter()
        frames = [VOICE] * 20 + [QUIET] * 10 + [VOICE] * 20 + [QUIET] * 45
        results = [detector.feed(frame) for frame in frames]
        self.assertTrue(all(r is None for r in results[:-1]))
        self.assertEqual(results[-1], b''.join(frames))

    def test_show_settings_keep_both_halves_across_seven_tenths_second_pause(self):
        from queen_robot.queen_script import load_script
        import math
        settings = load_script()['listening']
        self.assertLessEqual(settings['silence_seconds'], 1.0, '避免句尾等待无界加长')
        for frame_seconds in (0.02, 512 / 16000):
            with self.subTest(frame_seconds=frame_seconds):
                detector = UtteranceSegmenter(settings, frame_seconds=frame_seconds)
                voice = np.full(detector.frame_samples, 2000, dtype='<i2').tobytes()
                quiet = bytes(detector.frame_samples * 2)
                end_frames = math.ceil(settings['silence_seconds'] / frame_seconds)
                frames = [voice] * 20 + [quiet] * math.ceil(0.7 / frame_seconds) + [voice] * 20 + [quiet] * end_frames
                results = [detector.feed(frame) for frame in frames]
                self.assertTrue(all(result is None for result in results[:-1]))
                self.assertEqual(results[-1], b''.join(frames))

    def test_overlong_sentence_is_discarded_not_truncated(self):
        detector = UtteranceSegmenter({'max_utterance_seconds': 1})
        for frame in [VOICE] * 100 + [QUIET] * 45:
            self.assertIsNone(detector.feed(frame))
        self.assertEqual(detector.dropped, 1)
        self.assertFalse(detector.discarding)

    def test_invalid_settings_rejected_before_recording(self):
        for settings in [{'silence_seconds':0}, {'energy_threshold':float('nan')},
                         {'pre_roll_seconds':100}, {'min_speech_seconds':30}, {'unknown':1}]:
            with self.assertRaises(ValueError):
                listening_settings(settings)

    def test_record_closes_microphone_before_saving(self):
        audio = Mock()
        mic = Mock(rate=16000, frames_per_buffer=320)
        mic.stream.read.side_effect = [VOICE] * 20 + [QUIET] * 45
        pyaudio = Mock()
        pyaudio.PyAudio.return_value = audio
        def save(path, frames):
            mic.stream.close.assert_called_once()
            audio.terminate.assert_called_once()
            self.assertTrue(frames[0].startswith(VOICE))
        with patch.dict(sys.modules, {'pyaudio':pyaudio}), \
             patch('audio.play_listening_cue'), \
             patch('audio.open_input_stream', return_value=mic), \
             patch('audio.save_wave_file', side_effect=save):
            record_utterance('unused.wav')

    def test_read_error_closes_devices(self):
        audio = Mock()
        mic = Mock(rate=16000, frames_per_buffer=320)
        mic.stream.read.side_effect = OSError('disconnected')
        pyaudio = Mock()
        pyaudio.PyAudio.return_value = audio
        with patch.dict(sys.modules, {'pyaudio':pyaudio}), \
             patch('audio.play_listening_cue'), \
             patch('audio.open_input_stream', return_value=mic), \
             patch('audio.save_wave_file') as save:
            with self.assertRaisesRegex(OSError, 'disconnected'):
                record_utterance('unused.wav')
            save.assert_not_called()
        mic.stream.close.assert_called_once()
        audio.terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
