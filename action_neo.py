import os
import time
import json
import serial
import cv2
from rhythm_recog import rhythm_recog
from speech_recog import speech_recog
from datapackage import DataPackageConverter
from posture_recognition.static_recognition import StaticPostureIdentifier
import config

pose_identifier = config.pose_identifier


# 初始化串口
def initialize_serial():
    try:
        ser = serial.Serial('/dev/ttyAMA0', 115200)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException:
        raise Exception("Failed to initialize serial connection.")


def play_audio(audio_file):
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
        play_audio('resources/sorry.MP3')
        
    else:
        # 姿态识别
        if keyword == "pose_recognition":

            
            while True:
                play_audio('resources/pose.MP3')
                send_bytes = DataPackageConverter("0deer_see.bin").hex_output
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
                        play_audio('resources/sorry.MP3')
                        return
                    except Exception as e:
                        print(f"姿势识别器初始化失败 - 未知错误: {e}")
                        play_audio('resources/sorry.MP3')
                        return
                
                
                # 使用初始化好的识别器实例
                print("请在摄像头前保持姿势...")
                # 调用静态姿势识别函数
                pose = pose_identifier.recognize_posture(camera_index=0, timeout=15, stable_duration=2.0, display=True,camera_rotation = 180)
                send_bytes = DataPackageConverter("0deer_reset.bin").hex_output
                send_serial_data(ser, send_bytes)
                
                if pose is None:
                    play_audio('resources/timeout.MP3')
                    break
                
                if pose == "stop":
                    play_audio('resources/stop.MP3')
                    break
            
                play_audio("resources/" + pose + ".MP3")
                send_bytes = DataPackageConverter(pose + ".bin").hex_output
                send_serial_data(ser, send_bytes)

        # 韵律识别
        elif keyword == "rhythm_recognition":
            play_audio("resources/rhythm.MP3")
            matched_song, compare_result = rhythm_recog()
            play_audio("resources/index"+matched_song) # 歌曲名称
            if matched_song == "TryEverything.MP3":
                movements = DataPackageConverter("0deer_dance2.odr").hex_output
            else:
                movements = DataPackageConverter("0deer_dance1.odr").hex_output
            ser.write(bytearray(movements)) # 执行动作
            play_audio("resources/"+matched_song) # 播放歌曲

        # 语音识别自选动作
        elif keyword == "speech_recognition":
            print("进入语音识别模式，请说出动作指令...")
            play_audio('resources/please_speak.MP3')  # 播放提示音
            
            failed_count = 0  # 记录连续失败次数
            max_failed_attempts = 3  # 最大失败次数
            
            while True:
                # 进行语音识别，识别具体的动作指令
                word = speech_recog()
                print(f"识别到的指令: {word}")
                
                # 检查是否是退出指令
                if "结束" in word or "仅剩" in word or "既然说" in word or "家住" in word or "引述" in word or "别墅" in word or "野兽" in word:
                    print("识别到退出指令，结束语音识别模式")
                    play_audio('resources/exit.MP3')
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
                            audio_file = "resources/" + action_keyword + ".MP3"
                            play_audio(audio_file)
                            if action in ["前进","后退","左移","右移","向左转","向右转"]:
                                send_bytes = DataPackageConverter(action_keyword + ".odr").hex_output
                                send_serial_data(ser, send_bytes)
                            else :
                                send_bytes = DataPackageConverter(action_keyword + ".bin").hex_output
                                send_serial_data(ser, send_bytes)
                            action_found = True
                            failed_count = 0  # 重置失败计数
                            play_audio('resources/please_speak.MP3')
                            break
                    
                    if action_found:
                        break
                
                # 如果没有找到匹配的动作
                if not action_found:
                    failed_count += 1
                    print(f"未找到匹配的动作 (失败次数: {failed_count}/{max_failed_attempts})")
                    play_audio('resources/sorry.MP3')
                    
                    # 检查是否达到最大失败次数
                    if failed_count >= max_failed_attempts:
                        print("连续3次未识别到有效动作，退出语音识别模式")
                        play_audio('resources/exit.MP3')
                        break
                    else:
                        print("请重新说出动作指令...")
                        play_audio('resources/please_speak.MP3')
                else:
                    # 成功执行动作后，提示继续或结束
                    print("动作执行完成，请继续说出下一个动作指令，或说'结束'退出")
        
        else:
            play_audio("resources/" + keyword + ".MP3")
            if keyword in ["QianJin","HouTui", "ZuoYi", "YouYi", "XiangZuoZhuan", "XiangYouZhuan"]:
                send_bytes = DataPackageConverter(keyword + ".odr").hex_output
                send_serial_data(ser, send_bytes)
            else:
                send_bytes = DataPackageConverter(keyword + ".bin").hex_output
                send_serial_data(ser, send_bytes)
            
        if ser and ser.isOpen():
            ser.close()
            



def send_serial_data(ser, data):
    ser.write(bytearray(data))
    start_time = time.time()  # 记录开始时间
    timeout = 30  # 设置30秒超时

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
            if res == b'\xff\x00\x05\x05\x00\x00\x18"' or res == b'\xff\x00\x05\x05\x00\x00\x19"':
                break
            time.sleep(0.5)  # 软件延时
            


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
