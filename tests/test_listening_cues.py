"""验证真实录音入口的提示顺序；仅替代外部播放器、麦克风和唤醒模型。"""
from contextlib import ExitStack
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio
import wake
from utterance import record_utterance


class ListeningCueTests(unittest.TestCase):
    def capture(self, mode, failure=None, cue=True):
        events = []
        driver = Mock()
        driver.terminate.side_effect = lambda: events.append('terminate')
        mic = Mock(rate=16000, frames_per_buffer=320)
        mic.stream.stop_stream.side_effect = lambda: events.append('stop')
        mic.stream.close.side_effect = lambda: events.append('close')
        speech = np.full(320, 2000, dtype='<i2').tobytes()
        frames = iter([speech] * 20 + [bytes(640)] * 45)

        def read(*args, **kwargs):
            events.append('read')
            if failure is not None:
                raise failure
            return next(frames)

        def open_mic(*args, **kwargs):
            events.append('open')
            return mic

        def play(sound, **kwargs):
            events.append(('cue', sound))
            self.assertFalse(kwargs.get('background', False))
            return True

        mic.stream.read.side_effect = read
        pyaudio = Mock()
        pyaudio.PyAudio.return_value = driver
        detector = Mock()
        detector.detect.side_effect = ['', '蜂后']
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {'pyaudio': pyaudio}))
            stack.enter_context(patch('audio.play_audio', side_effect=play))
            stack.enter_context(patch('audio.open_input_stream', side_effect=open_mic))
            stack.enter_context(patch('wake.open_input_stream', side_effect=open_mic))
            stack.enter_context(patch('audio.save_wave_file', side_effect=lambda *args: events.append('save')))
            stack.enter_context(patch('sherpa_speech.KwsDetector', return_value=detector))
            stack.enter_context(patch('time.sleep'))
            try:
                if mode == 'wake':
                    self.assertEqual(wake.wait_for_wake(), '蜂后')
                elif mode == 'utterance':
                    record_utterance('unused.wav', cue=cue)
                else:
                    audio.record_wav('unused.wav', 0.04, cue=cue)
            except BaseException as exc:
                if failure is None or exc is not failure:
                    raise
            else:
                if failure is not None:
                    self.fail('录音异常未传递给调用方')
        return events

    def test_each_capture_plays_one_ding_before_opening_microphone(self):
        for mode in ('wake', 'utterance', 'fixed'):
            with self.subTest(mode=mode):
                events = self.capture(mode)
                cues = [i for i, event in enumerate(events) if isinstance(event, tuple)]
                self.assertEqual(len(cues), 1, events)
                self.assertEqual(events[cues[0]], ('cue', 'ding.wav'))
                self.assertLess(cues[0], events.index('open'))
                self.assertLess(events.index('close'), events.index('terminate'))

    def test_recording_errors_and_interrupts_do_not_repeat_ding(self):
        for mode in ('wake', 'utterance', 'fixed'):
            for failure in (OSError('microphone disconnected'), KeyboardInterrupt()):
                with self.subTest(mode=mode, failure=type(failure).__name__):
                    events = self.capture(mode, failure=failure)
                    self.assertEqual([event for event in events if isinstance(event, tuple)],
                                     [('cue', 'ding.wav')])
                    self.assertIn('close', events)
                    self.assertIn('terminate', events)

    def test_fixed_recording_can_still_disable_cues(self):
        events = self.capture('fixed', cue=False)
        self.assertFalse(any(isinstance(event, tuple) for event in events))

    def test_retry_recording_can_open_microphone_without_another_ding(self):
        events = self.capture('utterance', cue=False)
        self.assertFalse(any(isinstance(event, tuple) for event in events))
        self.assertIn('open', events)
        self.assertIn('save', events)

    def test_recognition_follows_release_without_another_ding(self):
        import speech_recog
        events = []
        def record(*args, **kwargs):
            events.extend(self.capture('utterance'))

        def transcribe(path):
            self.assertIn('close', events)
            self.assertIn('terminate', events)
            return '执行 机体自检'

        with patch('utterance.record_utterance', side_effect=record), \
             patch.object(speech_recog, 'prepare_listening'), \
             patch.object(speech_recog, '_sherpa_transcribe', side_effect=transcribe):
            self.assertEqual(speech_recog.listen_for_line(), '执行机体自检')
        self.assertEqual([event for event in events if isinstance(event, tuple)],
                         [('cue', 'ding.wav')])

    def test_wake_then_two_lines_have_exactly_three_start_dings(self):
        events = self.capture('wake') + self.capture('utterance') + self.capture('utterance')
        self.assertEqual([event for event in events if isinstance(event, tuple)],
                         [('cue', 'ding.wav')] * 3)

    def test_recognition_retry_passes_silent_cue_policy_to_capture(self):
        import speech_recog
        events = []

        def record(*args, **kwargs):
            events.extend(self.capture('utterance', cue=kwargs['cue']))

        with patch('utterance.record_utterance', side_effect=record), \
             patch.object(speech_recog, 'prepare_listening'), \
             patch.object(speech_recog, '_sherpa_transcribe', return_value='执行机体自检'):
            self.assertEqual(speech_recog.listen_for_line(cue=False), '执行机体自检')
        self.assertFalse(any(isinstance(event, tuple) for event in events))

    def test_start_ding_settles_before_microphone_can_open(self):
        method = getattr(audio, 'play_listening_cue', None)
        self.assertTrue(callable(method), '缺少收音提示音函数')
        events = []
        with patch('audio.play_audio', side_effect=lambda *args, **kwargs: events.append('play') or True), \
             patch('time.sleep', side_effect=lambda delay: events.append(('settle', delay))):
            method('开始收音')
        self.assertEqual(events, ['play', ('settle', 0.12)])

    def test_failed_ding_is_reported_without_settling_delay(self):
        method = getattr(audio, 'play_listening_cue', None)
        self.assertTrue(callable(method), '缺少收音提示音函数')
        with patch('audio.play_audio', return_value=False), patch('time.sleep') as settle:
            with self.assertRaisesRegex(RuntimeError, '提示音'):
                method('开始收音')
            settle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
