import cv2

# 打开默认摄像头
cap = cv2.VideoCapture(0)

# 检查摄像头是否成功打开
if not cap.isOpened():
    print("错误：无法访问摄像头")
    exit()

print("摄像头已开启 - 按 'q' 键退出")

while True:
    # 读取一帧画面
    ret, frame = cap.read()
    
    # 检查是否成功读取帧
    if not ret:
        print("错误：无法获取画面")
        break
    
    # 显示实时画面
    cv2.imshow('Camera Feed', frame)
    
    # 按'q'键退出循环
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头资源
cap.release()
# 关闭所有OpenCV窗口
cv2.destroyAllWindows()