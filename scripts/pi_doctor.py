"""检查演出依赖；--hardware 额外打开麦克风检查输入，并检查串口权限，不发动作。"""
import argparse
import importlib
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--silent-actions', action='store_true')
    args = parser.parse_args(argv)
    errors = []

    def check(label, callback):
        try:
            callback()
            print('[通过] ' + label)
        except Exception as exc:
            errors.append(label)
            print('[失败] %s：%s' % (label, exc))

    for module in ('numpy', 'pyaudio', 'serial', 'sherpa_onnx', 'pypinyin'):
        check('依赖 ' + module, lambda m=module: importlib.import_module(m))

    def assets():
        from queen_robot.queen_script import load_script
        from action_catalog import load_actions
        from paths import find_audio
        load_script()
        for action in load_actions():
            if find_audio(action['audio']) is None:
                raise FileNotFoundError(action['audio'])
    check('剧本与全部动作音频', assets)

    def models():
        from sherpa_speech import kws_model_files, asr_model_files, keywords_file
        if not kws_model_files() or not asr_model_files():
            raise FileNotFoundError('运行 python scripts/prepare_sherpa_models.py 准备语音模型')
        if not Path(keywords_file()).is_file() or not Path(keywords_file()).read_text(encoding='utf-8').strip():
            raise FileNotFoundError('运行 python scripts/make_keywords.py 生成唤醒词')
        from queen_robot.queen_script import load_script
        if load_script().get('listening', {}).get('backend') == 'silero' and not (ROOT/'models/vad/silero_vad.onnx').is_file():
            raise FileNotFoundError('缺少 models/vad/silero_vad.onnx 人声检测模型')
    check('语音模型与唤醒词文件', models)

    def player():
        if not (shutil.which('mplayer') or shutil.which('ffplay')):
            raise RuntimeError('请安装 mplayer 或 ffmpeg')
    check('音频播放器', player)

    if args.hardware:
        def microphone():
            import pyaudio
            from audio import open_input_stream, no_alsa_error
            audio = None
            mic = None
            try:
                with no_alsa_error():
                    audio = pyaudio.PyAudio()
                mic = open_input_stream(audio, 1600)
                print('  麦克风采样率：%s' % mic.rate)
            finally:
                try:
                    if mic is not None:
                        try:
                            mic.stream.stop_stream()
                        finally:
                            mic.stream.close()
                finally:
                    if audio is not None:
                        audio.terminate()
        check('麦克风', microphone)

        def serial_access():
            from serial_link import PORT_CANDIDATES, PORT_ENV, dry_run
            if args.silent_actions or dry_run():
                print('  静默排练：跳过串口设备检查')
                return
            ports = [os.environ[PORT_ENV]] if os.getenv(PORT_ENV) else PORT_CANDIDATES
            if not any(os.path.exists(port) and os.access(port, os.R_OK | os.W_OK) for port in ports):
                raise RuntimeError('未发现可读写串口；配置 PI_SERIAL_PORT，检查 UART 与 dialout 权限')
        check('串口设备与权限（未打开、未发送）', serial_access)
    print('检查完成：%d 项失败。实际动作与音量仍需现场验证。' % len(errors))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
