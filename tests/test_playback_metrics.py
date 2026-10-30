import contextlib
import io
import threading
import unittest
from unittest.mock import Mock, patch
from playback_metrics import PlaybackMonitor, duration
from paths import find_audio


class PlaybackTimingTests(unittest.TestCase):
    def test_elapsed_is_player_completion_not_later_serial_wait(self):
        entered, release = threading.Event(), threading.Event()
        def wait(timeout):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test synchronization failed')
            return 0
        proc = Mock()
        proc.wait.side_effect = wait
        output=io.StringIO()
        with contextlib.redirect_stdout(output), patch('playback_metrics.time.monotonic',return_value=10) as clock:
            monitor=PlaybackMonitor(proc,'test',3,5)
            self.assertTrue(entered.wait(2))
            clock.return_value=12
            release.set()
            self.assertTrue(monitor.done.wait(2))
            clock.return_value=100
            monitor.wait()
        self.assertEqual(monitor.elapsed,2)
        self.assertIn('总时长 3.00 秒',output.getvalue())
        self.assertIn('实际耗时 2.00 秒',output.getvalue())

    def test_real_audio_has_indexed_duration(self):
        self.assertGreater(duration(find_audio('1-1')),1)

    def test_failed_player_is_not_reported_as_completed(self):
        proc=Mock()
        proc.wait.return_value=3
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            monitor=PlaybackMonitor(proc,'test',3,5)
            with self.assertRaisesRegex(RuntimeError,'播放失败'):
                monitor.wait()
        self.assertIn('失败',output.getvalue())
        self.assertNotIn('| 完成 |',output.getvalue())
