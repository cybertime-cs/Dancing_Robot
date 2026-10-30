import cv2
import time

for idx in range(0, 5):
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        continue

    ret, frame = cap.read()
    if ret:
        filename = f"capture_{idx}_{int(time.time())}.jpg"
        cv2.imwrite(filename, frame)
        print(f"成功保存到 {filename}")
        cap.release()
        break
    cap.release()
else:
    print("没有找到可用摄像头")
