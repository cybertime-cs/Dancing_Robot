import cv2
from static_recognition import StaticPostureIdentifier
import time

# ================= 配置区域 =================
LOG_FILE = "inference_fps_log.txt"
CAMERA_INDEX = 0
# =============================================

def main():
    # 1. 初始化摄像头
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("错误: 无法打开摄像头")
        return

    # 2. 初始化静态姿势识别器
    print("正在初始化静态姿势识别器...")
    try:
        estimator = StaticPostureIdentifier()
        print("识别器初始化完成。")
    except Exception as e:
        print(f"错误: 初始化识别器失败 - {e}")
        cap.release()
        return

    # 3. 准备日志文件
    try:
        with open(LOG_FILE, "w", encoding='utf-8') as f:
            f.write("=== 纯终端推理 FPS 日志 ===\n")
            f.write(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("-" * 40 + "\n")
        print(f"日志文件已创建: {LOG_FILE}")
    except IOError as e:
        print(f"错误: 无法创建日志文件 - {e}")
        cap.release()
        return

    # 4. 变量初始化
    # --- 姿势识别相关 ---
    current_posture = None
    stable_duration = 2.0
    last_detection_time = 0
    
    # --- 性能统计相关 ---
    total_inference_time = 0.0
    inference_count = 0
    
    # 用于计算日志写入频率的时间基准
    log_check_start_time = time.time()

    print("程序开始运行... (按 Ctrl+C 停止)")

    try:
        while True:
            # --- 1. 读取图像 ---
            ret, frame = cap.read()
            if not ret:
                print("警告: 无法获取图像帧")
                continue

            # --- 2. 精准推理计时开始 ---
            start_infer = time.perf_counter()
            
            # 核心识别逻辑
            # 注意：虽然 estimator.use 返回了 annotated_frame，但我们直接忽略它（用 _ 接收）
            # 因为我们在终端不需要画图，这样可以节省内存和CPU
            _, has_posture, detected_posture = estimator.use(frame)
            
            end_infer = time.perf_counter()
            # --- 2. 精准推理计时结束 ---

            # 统计推理耗时
            current_inference_time = end_infer - start_infer
            total_inference_time += current_inference_time
            inference_count += 1

            # --- 3. 姿势稳定检测逻辑 (纯数据逻辑) ---
            current_time = time.time()

            if has_posture:
                # 逻辑保持不变：如果检测到姿势，且（是新姿势 或 还是原来的姿势）
                if current_posture == detected_posture or current_posture is None:
                    current_posture = detected_posture
                    if last_detection_time == 0:
                        last_detection_time = current_time
                    
                    stable_time = current_time - last_detection_time
                    
                    # 如果姿势稳定足够时间
                    if stable_time >= stable_duration:
                        print(f"[{time.strftime('%H:%M:%S')}] ✅ 识别结果: {current_posture}")
                        last_detection_time = 0 # 重置计时器
                else:
                    # 姿势变了，重置
                    last_detection_time = 0
            else:
                # 没检测到姿势，重置
                last_detection_time = 0

            # --- 4. 记录 FPS 到文件 ---
            # 每 1 秒写入一次日志，避免频繁IO影响推理速度
            if current_time - log_check_start_time >= 1.0:
                if inference_count > 0:
                    avg_inference_time_ms = (total_inference_time / inference_count) * 1000
                    avg_inference_fps = 1.0 / (total_inference_time / inference_count)
                    
                    log_msg = f"平均推理耗时: {avg_inference_time_ms:.2f} ms | 推理 FPS: {avg_inference_fps:.2f}"
                    
                    # 打印到终端
                    print(log_msg)
                    
                    # 写入文件
                    with open(LOG_FILE, "a", encoding='utf-8') as f:
                        f.write(f"{log_msg}\n")
                    
                    # 重置统计数据
                    total_inference_time = 0.0
                    inference_count = 0
                    log_check_start_time = current_time

    except KeyboardInterrupt:
        print("\n检测到用户停止 (Ctrl+C)")
    
    finally:
        # --- 5. 清理资源 ---
        print("正在释放资源...")
        cap.release()
        print("程序已退出。")

if __name__ == "__main__":
    main()