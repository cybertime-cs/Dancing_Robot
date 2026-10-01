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
from interaction_zh import interaction

pose_identifier = config.pose_identifier

# 初始化串口
def initialize_serial():
    try:
        ser = serial.Serial('/dev/ttyAMA10', 115200)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException as e:
        print(f"Error:{e}")
        raise Exception("Failed to initialize serial connection.")


def play_audio(audio_file):
    os.system('mplayer -volume 200 %s' % audio_file)
def play_audio_small(audio_file):
    os.system('mplayer -volume 100 %s' % audio_file)
# 保存局部变量到文件
def save_variable_to_file(value):
    with open('temp.txt', 'w') as file:
        file.write(str(value))


def action_neo(text):
    # 读取 speech_train.json 文件
    try:
        with open('speech_train.json', 'r', encoding='utf-8') as f:
            speech_data = json.load(f)
    except Exception as e:
        print(f"Error loading speech_train.json: {e}")
        return

    ser = initialize_serial()
    keyword = "" # 存储指令的name字段
    
    # 遍历 speech_train.json 检查是否有匹配的关键词
    for action, action_data in speech_data.items():
        # 跳过黑名单
        if action == "黑名单":
            continue
        
        # 检查 text 是否包含列表中的任一关键词
        for keyword_text in action_data["list"]:
            if keyword_text in text:
                # 找到匹配的关键词，使用对应的 name 值
                keyword = action_data["name"]
                print(f"找到关键词 '{keyword_text}'，对应动作 '{action}'，指令名称 '{keyword}'")
                break
        
        if keyword:  # 如果找到了关键词，退出外层循环
            break

    if not keyword:
        play_audio('resources/sorry.wav')
        
    else:
        # 姿态识别
        if keyword == "pose_recognition":
            total_inference_time = 0.0
            inference_count = 0
            fps_log_start_time = time.time()
            
            while True:
                play_audio('resources/pose.wav')
                send_bytes = DataPackageConverter("zr_adapt.bin").hex_output
                send_serial_data(ser, send_bytes)
                play_audio('resources/dong.wav') 
                # 检查姿势识别器是否已成功初始化
                global pose_identifier
                if pose_identifier is None:
                    print("姿势识别器未初始化，尝试重新初始化...")
                    try:
                        pose_identifier = StaticPostureIdentifier()
                        print("姿势识别器重新初始化成功")
                    except FileNotFoundError as e:
                        print(f"姿势识别器初始化失败 - 模型文件缺失: {e}")
                        play_audio('resources/sorry.wav')
                        return
                    except Exception as e:
                        print(f"姿势识别器初始化失败 - 未知错误: {e}")
                        play_audio('resources/sorry.wav')
                        return
                
                
                # 使用初始化好的识别器实例
                print("请在摄像头前保持姿势...")
                # 调用静态姿势识别函数
                infer_start = time.perf_counter()
                pose = pose_identifier.recognize_posture(camera_index=0, timeout=15, stable_duration=2.0, display=False,camera_rotation = 270)
                send_bytes = DataPackageConverter("zr_return.bin").hex_output
                send_serial_data(ser, send_bytes)
                
                if pose is None:
                    play_audio('resources/timeout.wav')
                    send_bytes = DataPackageConverter("zr_return.bin").hex_output
                    send_serial_data(ser, send_bytes)
                    break
                
                if pose == "stop":
                    play_audio('resources/stop.wav')
                    send_bytes = DataPackageConverter("zr_return.bin").hex_output
                    send_serial_data(ser, send_bytes)
                    break
            
                play_audio("resources/" + pose + ".wav")
                send_bytes = DataPackageConverter("zr_"+pose + ".bin").hex_output
                send_serial_data(ser, send_bytes) 

        # 韵律识别
        elif keyword == "rhythm_recognition":
            #play_audio("resources/rhythm.wav")
            #matched_song, compare_result = rhythm_recog()
            matched_song="choice.wav"
            play_audio("resources/index"+matched_song) # 歌曲名称
            if matched_song == "choice.wav":
                movements = DataPackageConverter("zr_chioce.odr").hex_output
            else:
                movements = DataPackageConverter("zr_dance.odr").hex_output
            ser.write(bytearray(movements)) # 执行动作
            play_audio("resources/"+matched_song) # 播放歌曲
        # 语音识别自选动作
        elif keyword == "speech_recognition":
            #send_bytes = DataPackageConverter("zr_RightHandUp.bin").hex_output
            #send_serial_data(ser, send_bytes)
            #time.sleep(20)
            print("进入语音识别模式，请说出动作指令...")
            play_audio('resources/please_speak.wav')  # 播放提示音
            failed_count = 0  # 记录连续失败次数
            max_failed_attempts = 3  # 最大失败次数
            
            while True:
                # 进行语音识别，识别具体的动作指令
                word = speech_recog()
                print(f"识别到的指令: {word}")
                # 检查是否是退出指令
                if "结束" in word or "仅剩" in word or "既然说" in word or "家住" in word or "引述" in word or "别墅" in word or "野兽" in word:
                    print("识别到退出指令，结束语音识别模式")
                    play_audio('resources/exit.wav')
                    break
                
                # 在speech_train.json中查找匹配的动作
                action_found = False
                for action, action_data in speech_data.items():
                    if action == "黑名单":
                        continue
                        
                    # 检查识别到的word是否在当前动作的关键词列表中
                    for keyword_text in action_data["list"]:
                        if keyword_text in word:
                            action_keyword = action_data["name"]
                            print(f"找到匹配动作: {action} -> {action_keyword}")
                            
                            # 执行对应的动作
                            audio_file = "resources/" + action_keyword + ".wav"
                            play_audio(audio_file)
                            if action in ["前进","后退","左移","右移","向左转","向右转"]:
                                send_bytes = DataPackageConverter("zr_"+action_keyword + ".odr").hex_output
                                send_serial_data(ser, send_bytes)
                            else :
                                send_bytes = DataPackageConverter("zr_"+action_keyword + ".bin").hex_output
                                send_serial_data(ser, send_bytes)
                            action_found = True
                            failed_count = 0  # 重置失败计数
                            play_audio('resources/please_speak.wav')
                            break
                    
                    if action_found:
                        break
                
                # 如果没有找到匹配的动作
                if not action_found:
                    failed_count += 1
                    print(f"未找到匹配的动作 (失败次数: {failed_count}/{max_failed_attempts})")
                    play_audio('resources/sorry.wav')
                    
                    # 检查是否达到最大失败次数
                    if failed_count >= max_failed_attempts:
                        print("连续3次未识别到有效动作，退出语音识别模式")
                        play_audio('resources/exit.wav')
                        break
                    else:
                        print("请重新说出动作指令...")
                        play_audio('resources/please_speak.wav')
                else:
                    # 成功执行动作后，提示继续或结束
                    print("动作执行完成，请继续说出下一个动作指令，或说'结束'退出")
                    
        elif keyword == "interaction_mode":
            print("进入交互模式,请说出你的问题")
            inter_text = speech_recog()
            while(1):
                print(inter_text)
                if("结束" in inter_text or "退出" in inter_text):
                    break
                interaction(inter_text)
                print("请说出下一个问题")
                inter_text = speech_recog()
            print("交互模式结束")
   
            
        if ser and ser.isOpen():
            ser.close()
            



def send_serial_data(ser, data):
    ser.write(bytearray(data))
    start_time = time.time()  # 记录开始时间
    timeout = 200  # 设置超时时长

    while True:
        # 检查是否超时
        if time.time() - start_time > timeout:
            print("串口通信超时，自动退出循环")
            break
            
        size = ser.inWaiting()  # 获得缓冲区字符
        if size != 0:
            res = ser.read(size)  # 读取内容并显示
            print(res)
            ser.flushInput()  # 情况接收缓存区
            if res == b'\xff\x00\x05\x05\x00\x00\x18\x22' or res == b'\xff\x00\x05\x05\x00\x00\x19\x22':
                break
            time.sleep(0.5)  # 软件延时(注意缩进)
            
            


if __name__ == '__main__':
     # 测试代码
    while True:
        order = int(input("请输入指令:0:退出 1:voice 2:keyboard"))
        if order == 0:
            break
        elif order == 1:
            print("请说出指令...")
            text = speech_recog()
            print(text)
            action_neo(text)
        elif order == 2:
            choice = int(input("请输入指令:1:姿态识别 2:韵律识别 3:语音识别"))
            if choice == 1:
                action_neo("姿态识别")
            elif choice == 2:
                action_neo("韵律识别")
            else:
                action_neo("语音识别")
