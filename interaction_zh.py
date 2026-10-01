import os
# 在导入 ollama 之前清除可能含有错误格式的代理环境变量
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('all_proxy', None)
os.environ.pop('ALL_PROXY', None)

import ollama
import time
import signal
import sys
import subprocess
from threading import Lock

tts_lock = Lock()

current_tts_process =None

def init_environment():
    """初始化环境"""
    # 注册信号处理，允许通过 Ctrl+C 优雅退出
    signal.signal(signal.SIGTERM, lambda s,f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s,f: sys.exit(0))

def speak(text):
    """文本转语音 - 直接使用系统 espeak 命令"""
    global current_tts_process
    with tts_lock:
        try:
            subprocess.run(
                    ['espeak','-v','zh','-s','120',text],
                    stderr=sys.stderr,
                    check=True
                )

        except Exception as e:
            print(f"\n语音播报错误: {e}", flush=True)

def robust_offline_query(prompt, max_tokens=128):
    """鲁棒的离线查询 - 增强流式响应处理与边读边播"""
    init_environment()
    sentence_buffer = ""
    full_response = "" # 用于保存最终返回的完整文本
    
    try:
        client = ollama.Client(
            host='http://127.0.0.1:11434',
            timeout=30000
        )
        
        print("生成中: ", end="", flush=True)
        
        # 使用chat接口并设置流式响应
        stream = client.chat(
            model='qwen:0.5b',
            messages=[{'role': 'user', 'content': prompt}],
            stream=True,
            options={
                'num_predict': max_tokens,
                'temperature': 0.7,
                'num_ctx': 512,
                'num_thread': 2
            }
        )
        
        try:
            for chunk in stream:
                content = chunk.get('message', {}).get('content', '')
                if content:
                    print(content, end='', flush=True)
                    full_response += content  # 正确收集完整的回复
                    
                    # 中文句子检测
                    clean_content = content.replace('*', '').replace('#', '')
                    sentence_buffer += clean_content
                    
                    # 遇到标点符号，或者句子够长了，就触发一次播报
                    if (any(punc in content for punc in ["。", "！", "？", "；", "\n"])) or len(sentence_buffer) > 30: 
                        if len(sentence_buffer.strip()) > 1:  # 忽略纯单个标点
                            speak(sentence_buffer.strip())
                            sentence_buffer = ""
                            
        except Exception as inner_e:
            print(f"\n流式处理错误: {str(inner_e)}", flush=True)
        
        # 播报剩余最后一点内容
        if sentence_buffer.strip():
            speak(sentence_buffer.strip())
            
        # 修复：返回真正收集到的完整字符串，而不是空的 response_chunks
        return full_response
    
    except Exception as e:
        error_msg = f"错误: {str(e)}"
        print(error_msg, flush=True)
        return error_msg

def interaction(prompt):
    start_time = time.time()
    
    response = robust_offline_query(prompt, max_tokens=128)
    elapsed = time.time() - start_time
        
    token_count = len(response)
        
    print(f"\n\n耗时: {elapsed:.1f}秒")
    print(f"字符数: {token_count}")
        

if __name__ == "__main__":
    print("=== 离线语音测试 ===")
    prompt = input('请输入指令（输入q退出): ')
    self_recog = "自我认知：你的名字是红莲，是一个人型舞蹈机器人，擅长跳舞，动作模仿和交流互动"
    prompt = self_recog+prompt
    while prompt.lower() != 'q':
        start_time = time.time()
        
        response = robust_offline_query(prompt, max_tokens=128)
        elapsed = time.time() - start_time
        
        token_count = len(response)
        
        print(f"\n\n耗时: {elapsed:.1f}秒")
        print(f"字符数: {token_count}")
        
        prompt = input('\n请输入指令（输入q退出): ')
