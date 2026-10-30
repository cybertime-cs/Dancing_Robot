"""回执分段、粘连与校时跳变的回归测试，不打开真实串口。"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import serial_link


class Clock:
    def __init__(self, wall_jump=0):
        self.elapsed = 0.0
        self.wall_jump = wall_jump

    def monotonic(self):
        return self.elapsed

    def time(self):
        return 100 + self.elapsed + (self.wall_jump if self.elapsed else 0)

    def sleep(self, seconds):
        self.elapsed += seconds


class Device:
    def __init__(self, clock, chunks=(), stale=b'', ready_after=0):
        self.clock, self.chunks = clock, list(chunks)
        self.stale, self.ready_after = stale, ready_after
        self.written = False

    def write(self, data):
        self.written = True
        return len(data)

    def inWaiting(self):
        if self.stale:
            return len(self.stale)
        if not self.written or self.clock.elapsed < self.ready_after:
            return 0
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size):
        if self.stale:
            data, self.stale = self.stale, b''
            return data
        return self.chunks.pop(0)

    def reset_input_buffer(self):
        self.stale = b''
        if self.written:
            self.chunks.clear()

    flushInput = reset_input_buffer


class SerialReceiveTests(unittest.TestCase):
    def run_send(self, chunks=(), *, stale=b'', wall_jump=0, ready_after=0):
        clock = Clock(wall_jump)
        device = Device(clock, chunks, stale, ready_after)
        with patch.dict(os.environ, {'PI_SERIAL_DRYRUN': '0'}), \
             patch.object(serial_link.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(serial_link.time, 'time', side_effect=clock.time), \
             patch.object(serial_link.time, 'sleep', side_effect=clock.sleep), \
             patch.object(serial_link, '_trace', create=True), \
             patch.object(serial_link, 'event'):
            accepted = serial_link.send_serial_data(device, b'command', timeout=0.2)
        return accepted, clock.elapsed

    def test_whole_existing_ack_remains_accepted(self):
        for ack in serial_link.ACK_FRAMES:
            self.assertTrue(self.run_send([ack])[0])

    def test_ack_split_at_any_byte_boundary_is_reassembled(self):
        ack = serial_link.ACK_FRAMES[0]
        for boundary in range(1, len(ack)):
            with self.subTest(boundary=boundary):
                self.assertTrue(self.run_send([ack[:boundary], ack[boundary:]])[0])

    def test_multiple_ack_frames_in_one_read_are_accepted(self):
        self.assertTrue(self.run_send([b''.join(serial_link.ACK_FRAMES)])[0])

    def test_noise_around_known_frame_does_not_hide_ack(self):
        self.assertTrue(self.run_send([b'\x17\x99'+serial_link.ACK_FRAMES[0]+b'\x00'])[0])

    def test_stale_ack_before_send_cannot_complete_new_command(self):
        self.assertFalse(self.run_send(stale=serial_link.ACK_FRAMES[0])[0])

    def test_forward_clock_adjustment_does_not_cause_early_timeout(self):
        accepted, elapsed = self.run_send([serial_link.ACK_FRAMES[0]], wall_jump=86400, ready_after=0.1)
        self.assertTrue(accepted)
        self.assertGreaterEqual(elapsed, 0.1)

    def test_partial_or_wrong_frame_does_not_count_as_ack(self):
        ack = serial_link.ACK_FRAMES[0]
        for frame in (ack[:7], ack[:-1]+b'\x23', b'noise'):
            with self.subTest(frame=frame):
                self.assertFalse(self.run_send([frame])[0])

    def test_no_response_waits_for_requested_elapsed_time(self):
        accepted, elapsed = self.run_send()
        self.assertFalse(accepted)
        self.assertGreaterEqual(elapsed, 0.2)
        self.assertLessEqual(elapsed, 0.25)


if __name__ == '__main__':
    unittest.main()
