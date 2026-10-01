import os
import time
import warnings
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
warnings.filterwarnings('ignore', message='SymbolDatabase.GetPrototype.*')
import json
import serial
import cv2
from rhythm_recog import rhythm_recog
from speech_recog import speech_recog
from datapackage import DataPackageConverter
from posture_recognition.static_recognition import StaticPostureIdentifier
import config

pose_identifier = config.pose_identifier
FPS_LOG_FILE = "fps_log.txt"

# 初始化串口
def initialize_serial():
    try:
        ser = serial.Serial('/dev/ttyAMA0', 115200)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException as e:
        print(f"Error:{e}")
        raise Exception("Failed to initialize serial connection.")


def play_audio(audio_file):
    os.system('mplayer -volume 100 %s' % audio_file)

ser = initialize_serial();
movements = DataPackageConverter("0deer_dance2.odr").hex_output
ser.write(bytearray(movements)) # 执行动作
play_audio("resources/"+"TryEverything.MP3") # 播放歌曲