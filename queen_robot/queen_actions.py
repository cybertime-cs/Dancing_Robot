"""演出动作适配：复用路径/串口协议，单独管理可回收的音频进程。"""
import os
import shutil
import subprocess
import time

from datapackage import DataPackageConverter
from paths import find_audio
from playback_metrics import PlaybackMonitor, duration
from runtime_log import event


class QueenActions:
    def __init__(self, script, dry_run=False, silent_actions=False):
        self.timing = script['timing']
        self.dry_run = dry_run
        self.silent_actions = silent_actions or os.getenv('PI_SERIAL_DRYRUN', '').lower() in ('1', 'true', 'yes', 'on')
        self.player = None
        self.serial_module = None
        self.playback = None

    def _play(self, name):
        target = find_audio(name)
        if target is None:
            raise RuntimeError('音频不存在：%s' % name)
        mplayer = shutil.which('mplayer')
        ffplay = shutil.which('ffplay')
        if mplayer:
            args = [mplayer, '-really-quiet', '-nolirc', '-volume', '100', target]
        elif ffplay:
            args = [ffplay, '-nodisp', '-autoexit', '-loglevel', 'error', target]
        else:
            raise RuntimeError('未安装 mplayer/ffplay，请在树莓派执行 sudo apt install mplayer')
        total = duration(target)
        event('音频', '%s | 开始 | 总时长 %s' % (name, '未知' if total is None else '%.2f 秒' % total))
        self.player = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL)
        if self.player.poll() not in (None, 0):
            raise RuntimeError('播放失败：%s' % name)
        self.playback = PlaybackMonitor(self.player, name, total, self.timing['audio_timeout_seconds'])

    def _wait_player(self):
        self.playback.wait()

    def stop_audio(self):
        proc, self.player = self.player, None
        if proc is not None and proc.poll() is None:
            if self.playback is not None:
                self.playback.cancelled = True
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        if self.playback is not None:
            self.playback.thread.join(timeout=2)
        self.playback = None

    def execute(self, step):
        key, value = next(iter(step.items()))
        if self.dry_run:
            event('模拟', '%s: %s' % (key, value))
        if key == 'notice':
            event('提示', str(value))
            return
        if self.dry_run:
            return
        if key == 'wait':
            event('等待', '%.1f 秒' % value)
            time.sleep(value)
            return
        if key not in ('audio', 'dance'):
            raise ValueError('未知操作：%s' % key)
        if key == 'dance':
            from action_catalog import get_action
            self.run_action(get_action(value))
            return
        try:
            self._play(value)
            self._wait_player()
        finally:
            self.stop_audio()

    def run_action(self, action):
        event('动作', '%s | %s' % (action['label'], action['file']))
        if self.dry_run:
            event('模拟', '音频：%s；动作：%s' % (action['audio'], action['file']))
            return
        try:
            ser = None
            if not self.silent_actions:
                import serial_link
                self.serial_module = serial_link
                ser = serial_link.get_serial()
            self._play(action['audio'])
            # 普通动作先播放名称；五段舞蹈同时起音乐和动作。
            if not action['parallel_audio']:
                self._wait_player()
                self.stop_audio()
            if self.silent_actions:
                event('动作', '静默模式，跳过 %s' % action['file'])
            else:
                packet = DataPackageConverter(action['file']).hex_output
                timeout = (self.timing['dance_timeout_seconds'] if action['parallel_audio']
                           else action['timeout_seconds'])
                if not self.serial_module.send_serial_data(ser, packet, timeout):
                    raise RuntimeError('动作 %s 未收到下位机应答；停止推进，请检查机器人状态' % action['id'])
            if action['parallel_audio']:
                self._wait_player()
        finally:
            self.stop_audio()

    def close(self):
        try:
            self.stop_audio()
        finally:
            if self.serial_module is not None:
                self.serial_module.close_serial()
