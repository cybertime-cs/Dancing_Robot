# config.py
pose_identifier = None

def initialize_pose_identifier():
    global pose_identifier
    if pose_identifier is None:
        try:
            from posture_recognition.static_recognition import StaticPostureIdentifier
            print("正在初始化姿态识别器...")
            pose_identifier = StaticPostureIdentifier()
            print("姿态识别器初始化成功")
        except FileNotFoundError as e:
            print(f"姿态识别器初始化失败 - 模型文件缺失: {e}")
            pose_identifier = None
        except Exception as e:
            print(f"姿态识别器初始化失败 - 未知错误: {e}")
            pose_identifier = None
    return pose_identifier