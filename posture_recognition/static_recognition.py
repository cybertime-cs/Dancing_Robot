"""
识别静态图片中的姿势。
从test_dataset文件夹读取图片，识别并显示结果。
"""
import os
import cv2
import glob
import time
import numpy as np
import pickle
import mediapipe as mp
from mediapipe import solutions
from mediapipe.framework.formats import landmark_pb2

class StaticPostureIdentifier:
    """
    用于识别静态图片中姿势的类
    """
    
    def __init__(self, model_path="models/pose_landmarker_heavy.task", camera_rotation=0):
        """
        初始化静态姿势识别器
        
        参数:
        - model_path: 模型文件路径
        - camera_rotation: 摄像头旋转角度，支持0, 90, 180, 270度
        """
        # 设置当前目录和模型路径
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.recognizer_path = os.path.join(self.current_dir, "output", "honglian_pose_recognizer.pickle")
        
        # 设置摄像头旋转角度
        if camera_rotation not in [0, 90, 180, 270]:
            raise ValueError("摄像头旋转角度必须是 0, 90, 180, 270 中的一个")
        self.camera_rotation = camera_rotation
        
        # 加载姿势标记器模型
        BaseOptions = mp.tasks.BaseOptions
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        landmarker_options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=self.current_dir + '/' + model_path),
            running_mode=VisionRunningMode.IMAGE
        )
        self.landmarker = PoseLandmarker.create_from_options(landmarker_options)

        # 加载预训练的姿势分类器和标签编码器
        print(f"从 {self.recognizer_path} 加载识别器...")
        if os.path.exists(self.recognizer_path):
            with open(self.recognizer_path, "rb") as f:
                recognizer_data = pickle.load(f)
                
            # 从组合的pickle文件中提取模型和标签编码器
            self.recognizer = recognizer_data["model"]
            self.label_encoder = recognizer_data["le"]
            print(f"已加载包含 {len(self.label_encoder.classes_)} 个类别的模型: {', '.join(self.label_encoder.classes_)}")
        else:
            print(f"警告：找不到模型文件 {self.recognizer_path}")
            print("请先运行 scripts/extract_keypoints_static.py 和 scripts/train_static_model.py")
            raise FileNotFoundError(f"找不到模型文件: {self.recognizer_path}")

    def _rotate_image(self, image, angle):
        """
        根据指定角度旋转图像
        
        参数:
        - image: 输入图像
        - angle: 旋转角度 (0, 90, 180, 270)
        
        返回:
        - 旋转后的图像
        """
        if angle == 0:
            return image
        elif angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            raise ValueError(f"不支持的旋转角度: {angle}")

    def use(self, frame):
        """识别给定图片中的姿势"""
        # 首先根据摄像头旋转角度旋转图像
        rotated_frame = self._rotate_image(frame, self.camera_rotation)
        
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(rotated_frame, cv2.COLOR_BGR2RGB))
        pose_landmarks_result = self.landmarker.detect(mp_image)
        pose_landmarks_list = pose_landmarks_result.pose_landmarks
        annotated_frame = cv2.cvtColor(np.copy(mp_image.numpy_view()), cv2.COLOR_RGB2BGR)
        
        # 初始化姿势标签
        posture_label = None
        has_posture = len(pose_landmarks_list) > 0

        for pose_landmarks in pose_landmarks_list:
            # 在图片上绘制关键点
            self._draw_landmarks(annotated_frame, pose_landmarks)

            # 展平关键点并预测姿势
            flattened_landmarks = np.array([[landmark.x, landmark.y] for landmark in pose_landmarks]).flatten()
            posture_label, probability = self._predict_posture(flattened_landmarks)

            # 在图片上标注预测的姿势和概率
            annotation_text = f"{posture_label}: {probability * 100:.2f}%"
            cv2.putText(annotated_frame, annotation_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)

        return annotated_frame, has_posture, posture_label

    def _draw_landmarks(self, annotated_frame, pose_landmarks):
        """在给定图片上绘制姿势关键点"""
        pose_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
        pose_landmarks_proto.landmark.extend([
            landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) 
            for landmark in pose_landmarks
        ])
        solutions.drawing_utils.draw_landmarks(
            annotated_frame,
            pose_landmarks_proto,
            solutions.pose.POSE_CONNECTIONS,
            solutions.drawing_styles.get_default_pose_landmarks_style()
        )

    def _predict_posture(self, flattened_landmarks):
        """基于展平的关键点使用预训练的识别器预测姿势"""
        prediction_probs = self.recognizer.predict_proba([flattened_landmarks])[0]
        max_prob_index = np.argmax(prediction_probs)
        posture_label = self.label_encoder.classes_[max_prob_index]
        probability = prediction_probs[max_prob_index]
        
        return posture_label, probability

    def recognize_posture(self, camera_index=0, timeout=30, stable_duration=2.0, display=True, camera_rotation=None):
        """
        打开摄像头识别姿势，并在稳定后返回识别结果
        
        参数:
        - camera_index: 摄像头索引，默认为0
        - timeout: 最大等待时间(秒)，超时后返回None
        - stable_duration: 姿势需要保持稳定的秒数，默认为2.0秒
        - display: 是否显示识别过程窗口
        - camera_rotation: 临时设置摄像头旋转角度，如果为None则使用初始化时的角度
        
        返回:
        - 识别到的姿势名称，如果超时或用户中断则返回None
        """
        # 如果提供了临时旋转角度，保存原始角度并设置新角度
        original_rotation = None
        if camera_rotation is not None:
            if camera_rotation not in [0, 90, 180, 270]:
                raise ValueError("摄像头旋转角度必须是 0, 90, 180, 270 中的一个")
            original_rotation = self.camera_rotation
            self.camera_rotation = camera_rotation
            
        # 初始化摄像头
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print("无法打开摄像头")
            return None
            
        # 初始化变量
        current_posture = None
        start_time = time.time()
        last_detection_time = 0
        
        print("请在摄像头前保持稳定姿势...")
        if self.camera_rotation != 0:
            print(f"摄像头已设置为旋转 {self.camera_rotation} 度")
        
        try:
            while True:
                # 读取摄像头图像
                ret, frame = cap.read()
                if not ret:
                    print("无法获取图像")
                    break
                
                # 识别姿势
                annotated_frame, has_posture, detected_posture = self.use(frame)
                
                current_time = time.time()
                
                # 如果已经超时，退出循环
                if current_time - start_time > timeout:
                    print("识别超时")
                    break
                
                # 如果检测到姿势
                if has_posture and detected_posture is not None:
                    # 如果是第一次检测到姿势或检测到的姿势与当前姿势相同
                    if current_posture is None or current_posture == detected_posture:
                        # 更新当前姿势
                        current_posture = detected_posture
                        
                        # 如果是第一次检测到此姿势，初始化时间戳
                        if last_detection_time == 0:
                            last_detection_time = current_time
                        
                        # 计算该姿势已稳定的时间
                        stable_time = current_time - last_detection_time
                        
                        # 在画面上显示进度
                        progress = min(stable_time / stable_duration * 100, 100)
                        cv2.putText(annotated_frame, f"保持姿势: {progress:.0f}%", (10, 90), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
                        
                        # 如果姿势已经稳定超过指定时间
                        if stable_time >= stable_duration:
                            # 显示识别结果
                            result_text = f"识别结果: {current_posture}"
                            cv2.putText(annotated_frame, result_text, (10, 120), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
                            
                            # 如果需要显示，在返回结果前展示一下
                            if display:
                                cv2.imshow('pose', annotated_frame)
                                cv2.waitKey(1000)  # 显示结果1秒
                            
                            print(f"成功识别姿势: {current_posture}")
                            return current_posture  # 直接返回识别到的姿势
                    else:
                        # 如果检测到的姿势发生变化，重置
                        current_posture = detected_posture
                        last_detection_time = current_time
                        print(f"姿势变化为: {current_posture}，重新计时")
                else:
                    # 如果没有检测到姿势，重置计时但保留当前姿势记录
                    if last_detection_time != 0:
                        last_detection_time = 0
                        print("姿势丢失，请回到摄像头范围内")
                    
                    cv2.putText(annotated_frame, "请保持稳定姿势", (10, 90), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
                
                # 显示图像
                if display:
                    cv2.imshow('frame', annotated_frame)
                    
                    # 按'q'退出
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("用户中断识别")
                        return None
                
        finally:
            # 释放资源
            cap.release()
            if display:
                cv2.destroyAllWindows()
            
            # 恢复原始旋转角度
            if original_rotation is not None:
                self.camera_rotation = original_rotation
        
        # 如果到这里，说明超时或其他原因导致退出循环
        return None

if __name__ == "__main__":
    # 测试代码 - 可以测试不同的旋转角度
    print("测试普通姿势识别（0度）...")
    pose_identifier = StaticPostureIdentifier(camera_rotation=0)
    pose = pose_identifier.recognize_posture(camera_index=0, timeout=15, stable_duration=2.0, display=True)
    if pose:
        print(f"识别到的姿势: {pose}")
    else:
        print("未能识别到姿势或用户中断")
    
    # 如果想测试旋转90度的情况，可以取消注释下面的代码
    # print("\n测试旋转90度姿势识别...")
    # pose_identifier_90 = StaticPostureIdentifier(camera_rotation=90)
    # pose = pose_identifier_90.recognize_posture(camera_index=0, timeout=15, stable_duration=2.0, display=True)
    # if pose:
    #     print(f"识别到的姿势: {pose}")
    # else:
    #     print("未能识别到姿势或用户中断")
