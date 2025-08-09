import cv2
from static_recognition import StaticPostureIdentifier
import time

def main():
    """主函数，提供不同旋转角度的姿势识别选项"""
    print("姿势识别系统")
    print("请选择摄像头旋转角度:")
    print("0 - 正立 (0度)")
    print("1 - 顺时针旋转90度")
    print("2 - 倒立 (180度)")
    print("3 - 逆时针旋转90度")
    
    choice = input("请输入选择 (0-3): ").strip()
    
    rotation_map = {
        "0": 0,
        "1": 90,
        "2": 180,
        "3": 270
    }
    
    if choice not in rotation_map:
        print("无效选择，使用默认角度0度")
        rotation_angle = 0
    else:
        rotation_angle = rotation_map[choice]
    
    print(f"已选择旋转角度: {rotation_angle}度")
    
    # 初始化摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头")
        return

    # 初始化静态姿势识别器，使用选定的旋转角度
    print("初始化静态姿势识别器...")
    estimator = StaticPostureIdentifier(camera_rotation=rotation_angle)

    # 用于显示姿势结果的变量
    current_posture = None
    posture_confidence = 0
    start_time = time.time()
    stable_duration = 2.0  # 姿势需要保持稳定的秒数
    last_detection_time = 0
    
    print("准备就绪，请在摄像头前保持稳定姿势...")
    print("按 'q' 退出，按 'r' 切换旋转角度")

    while True:
        # 读取摄像头图像
        ret, frame = cap.read()
        if not ret:
            print("无法获取图像")
            break

        # 识别姿势
        annotated_frame, has_posture, detected_posture = estimator.use(frame)
        
        current_time = time.time()
        
        # 在屏幕上显示当前旋转角度
        cv2.putText(annotated_frame, f"旋转角度: {rotation_angle}度", (10, annotated_frame.shape[0] - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        
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

        # 显示结果
        cv2.imshow('静态姿势识别', annotated_frame)
        
        # 处理按键
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("用户退出")
            break
        elif key == ord('r'):
            # 切换旋转角度
            cap.release()
            cv2.destroyAllWindows()
            print("\n重新选择旋转角度...")
            main()  # 重新调用主函数
            return

    # 释放资源
    cap.release()
    cv2.destroyAllWindows()
    print("程序已退出")

def test_rotation_angles():
    """测试不同旋转角度的函数"""
    print("测试所有旋转角度...")
    
    for angle in [0, 90, 180, 270]:
        print(f"\n测试旋转角度: {angle}度")
        print("按任意键继续下一个角度，按'q'跳过...")
        
        try:
            estimator = StaticPostureIdentifier(camera_rotation=angle)
            pose = estimator.recognize_posture(
                camera_index=0, 
                timeout=10, 
                stable_duration=2.0, 
                display=True
            )
            if pose:
                print(f"在{angle}度角度下识别到姿势: {pose}")
            else:
                print(f"在{angle}度角度下未识别到姿势")
        except Exception as e:
            print(f"测试{angle}度时出错: {e}")

if __name__ == "__main__":
    print("欢迎使用改进的姿势识别系统！")
    print("1 - 启动交互式识别")
    print("2 - 测试所有旋转角度")
    
    choice = input("请选择模式 (1-2): ").strip()
    
    if choice == "2":
        test_rotation_angles()
    else:
        main()
