"""实时识别回归，不接触麦克风、扬声器和主控串口。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from yinhe_robot import PerformanceFSM, SherpaStreamingRecognizer


class FakeVad:
    """第 2 帧起音，第 5 帧结束；真实 VAD 一样保留起音前样本。"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.frames = []
        self.queue = []
        self.ended = False

    def accept_waveform(self, frame):
        self.frames.append(frame.copy())
        if len(self.frames) == 5:
            self.queue.append(self.current_segment)
            self.ended = True

    @property
    def current_segment(self):
        return SimpleNamespace(start=0, samples=np.concatenate(self.frames))

    def is_speech_detected(self):
        return 2 <= len(self.frames) < 5

    def empty(self):
        return not self.queue

    @property
    def front(self):
        return self.queue[0]

    def pop(self):
        self.queue.pop(0)

    def flush(self):
        if self.frames and not self.ended:
            self.queue.append(self.current_segment)
            self.ended = True


class FakeStream:
    def __init__(self):
        self.samples = []
        self.ready = False
        self.finished = False
        self.text = ""

    def accept_waveform(self, rate, samples):
        self.samples.extend(samples)
        self.ready = True

    def input_finished(self):
        self.finished = True


class FakeAsr:
    def __init__(self):
        self.streams = []

    def create_stream(self):
        stream = FakeStream()
        self.streams.append(stream)
        return stream

    def is_ready(self, stream):
        return stream.ready

    def decode_stream(self, stream):
        stream.ready = False
        count = np.count_nonzero(stream.samples)
        stream.text = "银河银河尾音" if count >= 2048 else "银河银河"

    def get_result(self, stream):
        return stream.text


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.rec = SherpaStreamingRecognizer.__new__(SherpaStreamingRecognizer)
        self.rec.sample_rate = 16000
        self.rec.vad = FakeVad()
        self.rec.recognizer = FakeAsr()
        self.frames_read = 0
        self.closed = False

        def chunks(max_seconds):
            self.limit = max_seconds
            try:
                for value in range(1, 7):
                    self.frames_read += 1
                    yield np.full(512, value, dtype=np.float32)
            finally:
                self.closed = True

        self.rec._audio_chunks = chunks

    def test_match_before_utterance_end_and_release_recorder(self):
        text = self.rec.listen_once(None, lambda s: "银河银河" in s)
        self.assertEqual(text, "银河银河")
        self.assertEqual(self.frames_read, 2)
        self.assertTrue(self.closed)
        self.assertIsNone(self.limit)
        self.assertFalse(self.rec.recognizer.streams[0].finished)
        self.assertEqual(self.rec.vad.frames, [])

    def test_training_waits_for_complete_utterance(self):
        text = self.rec.listen_once()
        self.assertEqual(text, "银河银河尾音")
        self.assertEqual(self.frames_read, 5)
        self.assertTrue(self.rec.recognizer.streams[0].finished)
        self.assertTrue(self.closed)

    def test_preroll_preserved_samples_never_resent(self):
        self.rec.listen_once()
        samples = self.rec.recognizer.streams[0].samples
        speech = np.asarray(samples)[np.asarray(samples) != 0]
        np.testing.assert_array_equal(speech, np.repeat(np.arange(1, 6), 512))

    def test_unmatched_text_does_not_stop_listening(self):
        self.assertEqual(self.rec.listen_once(None, lambda _: False), "")
        self.assertEqual(self.frames_read, 6)
        self.assertTrue(self.closed)

    def test_next_listen_has_no_previous_segment(self):
        self.rec.listen_once(None, lambda _: True)
        self.rec.listen_once(None, lambda _: True)
        self.assertEqual(len(self.rec.recognizer.streams), 2)
        self.assertEqual([len(s.samples) for s in self.rec.recognizer.streams], [1024, 1024])

    def test_microphone_error_releases_recorder(self):
        def broken_chunks(_):
            try:
                yield np.ones(512, dtype=np.float32)
                raise OSError("disconnected")
            finally:
                self.closed = True
        self.rec._audio_chunks = broken_chunks
        with self.assertRaisesRegex(OSError, "disconnected"):
            self.rec.listen_once(None, lambda _: False)
        self.assertTrue(self.closed)
        self.assertEqual(self.rec.vad.frames, [])


class StateGateTests(unittest.TestCase):
    def setUp(self):
        self.hardware = Mock()
        self.config = {
            "master_wake": {"phrases": ["星途已定，即刻启航"], "steps": []},
            "commands": {
                "wake": {"phrases": ["银河银河"], "steps": []},
                "depart": {"phrases": ["出发"], "steps": []},
                "last": {"phrases": ["汇报任务完成情况"], "steps": [], "return_to_master_wake": True},
            },
        }
        self.fsm = PerformanceFSM(self.config, self.hardware)

    def test_only_master_wake_is_eligible_before_unlock(self):
        self.assertFalse(self.fsm.accepts_text("银河银河出发"))
        self.assertTrue(self.fsm.accepts_text("星途已定即刻启航"))
        self.assertEqual(self.fsm.state, self.fsm.WAITING_FOR_MASTER_WAKE)
        self.hardware.assert_not_called()

    def test_original_substring_matching_and_final_relock(self):
        self.fsm.handle_text("星途已定即刻启航")
        self.assertTrue(self.fsm.accepts_text("银河号现在出发吧"))
        self.fsm.handle_text("出发")
        self.assertEqual(self.fsm.state, self.fsm.IDLE)
        self.fsm.handle_text("汇报任务完成情况")
        self.assertFalse(self.fsm.accepts_text("出发"))
        self.assertTrue(self.fsm.accepts_text("星途已定即刻启航"))

    def test_conflict_does_not_trigger(self):
        self.config["commands"]["ambiguous"] = {"phrases": ["出发"], "steps": []}
        self.fsm.handle_text("星途已定即刻启航")
        self.assertFalse(self.fsm.accepts_text("现在出发"))

    def test_busy_state_does_not_accept_speech(self):
        self.fsm.state = self.fsm.EXECUTING
        self.assertFalse(self.fsm.accepts_text("银河银河"))


if __name__ == "__main__":
    unittest.main()
