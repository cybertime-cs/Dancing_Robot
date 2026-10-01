import cv2
from static_recognition import StaticPostureIdentifier
import time

# 初始化摄像头
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("无法打开摄像头")
    exit()

# 初始化静态姿势识别器
print("初始化静态姿势识别器...")
estimator = StaticPostureIdentifier()

# 用于显示姿势结果的变量
current_posture = None
posture_confidence = 0
start_time = time.time()
stable_duration = 2.0  # 姿势需要保持稳定的秒数
last_detection_time = 0
result_display_duration = 3.0  # 结果显示时间（秒）

print("准备就绪，请在摄像头前保持稳定姿势...")

while True:
    # 读取摄像头图像
    ret, frame = cap.read()
    if not ret:
        print("无法获取图像")
        break

    # 创建用于显示的图像副本
    display_frame = frame.copy()
    
    # 识别姿势
    annotated_frame, has_posture, detected_posture = estimator.use(frame)
    
    current_time = time.time()
    
    # 如果检测到姿势并且与当前姿势相同，记录稳定时间
    if has_posture and (current_posture == detected_posture or current_posture is None):
        current_posture = detected_posture
        if last_detection_time == 0:
            last_detection_time = current_time
        
        # 计算姿势稳定的持续时间
        stable_time = current_time - last_detection_time
        
        # 显示稳定进度
        progress = min(stable_time / stable_duration * 100, 100)
        cv2.putText(annotated_frame, f"保持姿势: {progress:.0f}%", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
        
        # 如果姿势稳定足够长时间，显示结果
        if stable_time >= stable_duration:
            # 获取并显示识别结果
            posture_confidence = 100  # 假设这里我们有置信度，但从静态识别器中无法直接获取
            
            # 重置计时器，以便下次检测
            last_detection_time = 0
            
            # 在主窗口显示结果
            result_text = f"识别结果: {current_posture}"
            cv2.putText(annotated_frame, result_text, (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
    else:
        # 如果姿势改变或丢失，重置计时器
        last_detection_time = 0
        cv2.putText(annotated_frame, "请保持稳定姿势", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

    # 显示帧率
    elapsed_time = current_time - start_time
    if elapsed_time > 0:
        fps = 1.0 / elapsed_time
        #cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (10, 30), 
                   #cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    start_time = current_time

    # 显示结果
    cv2.imshow('静态姿势识别', annotated_frame)
    
    # 按'q'退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()
print("程序已退出")