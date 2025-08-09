from speech_recog import speech_recog
import json
import os

speech_result = {   1 : '前进', 
                    2 : '后退', 
                    3 : '左移', 
                    4 : '右移', 
                    5 : '左脚撑', 
                    6 : '右脚撑',
                    7 : '举左手',
                    8 : '举双手',
                    9 : '向左转',
                    10 : '向右转',
                    11 : '姿态识别',
                    12 : '韵律识别',
                    13 : '展臂',
                    14 : '抱头',
                    15 : '拉伸',
                    16 : '语音识别',
                    17 : '结束'   }

def list_clean(json_path='speech_train.json'):
    """
    清理不同指令列表中的重复文本，并将这些文本添加到黑名单列表
    """
    print("开始清理重复的语音指令...")
    
    # 读取语音训练数据
    with open(json_path, 'r', encoding='utf-8') as f:
        speech_data = json.load(f)
    
    # 创建黑名单列表（如果不存在）
    if "黑名单" not in speech_data:
        speech_data["黑名单"] = []
    
    # 存储所有指令的文本及其所属指令
    all_commands = {}
    actions = [action for action in speech_data.keys() if action != "黑名单"]
    
    # 收集所有命令文本
    for action in actions:
        for text in speech_data[action]["list"]:
            if text in all_commands:
                all_commands[text].append(action)
            else:
                all_commands[text] = [action]
    
    # 找出重复的文本
    duplicates = {text: actions for text, actions in all_commands.items() if len(actions) > 1}
    
    if not duplicates:
        print("没有发现重复的语音指令")
        return
    
    # 清理重复的文本并添加到黑名单
    for text, conflicted_actions in duplicates.items():
        print(f"发现重复文本 '{text}' 出现在以下指令中: {', '.join(conflicted_actions)}")
        
        # 将文本从所有列表中移除
        for action in conflicted_actions:
            speech_data[action]["list"].remove(text)
            print(f"  - 已从 '{action}' 中移除")
        
        # 添加到黑名单
        if text not in speech_data["黑名单"]:
            speech_data["黑名单"].append(text)
            print(f"  - 已添加到黑名单")
    
    # 保存更新后的数据
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(speech_data, f, ensure_ascii=False, indent=4)
    
    print(f"清理完成！已处理 {len(duplicates)} 个重复文本")

def speech_train():
    # 读取现有的语音训练数据
    json_path = 'speech_train.json'
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            speech_data = json.load(f)
    else:
        print("找不到speech_train.json文件!")
        return

    while True:
        print("请输入你要训练的语音指令：")
        print("0:退出 1:前进 2:后退 3:左移 4:右移 5:左脚撑 6:右脚撑 7:举左手 8:举双手 9:向左转 10:向右转 11:姿态识别 12:韵律识别 13:展臂 14:抱头 15:拉伸 16:语音识别 17:结束")
        try:
            num = int(input())
            if num == 0:
                break
                            
            if num not in speech_result.keys():
                print("输入错误，请重新输入")
                continue
            
            count = 10
            while count > 0:
                count -= 1
                print(f"请说出{speech_result[num]}的语音指令...")
                text = speech_recog()
                if text:
                    # 清理文本，去除换行符和多余的空格
                    cleaned_text = text.replace('\n', '').strip()
                
                    # 检查是否在黑名单中
                    if "黑名单" in speech_data and cleaned_text in speech_data["黑名单"]:
                        print(f"'{cleaned_text}' 在黑名单中，因为它会导致指令冲突")
                        continue
                
                    # 获取对应的动作名称
                    action_name = speech_result[num]
                    # 显示识别结果并请求再次确认
                    print(f"识别结果: {cleaned_text}")
                    second_confirm = input(f"确认将 '{cleaned_text}' 添加到 '{action_name}' 吗？(y/n): ")
                    if second_confirm.lower() != 'y':
                        print("已取消添加")
                        continue
                
                    # 检查是否已存在相同的语音命令
                    if cleaned_text in speech_data[action_name]["list"]:
                        print(f"'{cleaned_text}' 已存在于 '{action_name}' 的语音命令列表中")
                        continue
                
                    # 将识别结果添加到对应动作的list中
                    speech_data[action_name]["list"].append(cleaned_text)
                    print(f"成功添加: {cleaned_text} -> {action_name}")
                
                    # 保存更新后的数据
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(speech_data, f, ensure_ascii=False, indent=4)
                    print(f"数据已保存到 {json_path}")
                else:
                    print("未能识别语音，请重试")
        except ValueError:
            print("请输入有效的数字")
        except Exception as e:
            print(f"发生错误: {e}")

if __name__ == "__main__":
    speech_train()
    list_clean()

