import cv2

cap = cv2.VideoCapture(1)
ret, frame = cap.read()
if ret:
    cv2.imwrite("photo_0.jpg", frame)
    cv2.imwrite("photo_90.jpg", cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE))
    cv2.imwrite("photo_180.jpg", cv2.rotate(frame, cv2.ROTATE_180))
    cv2.imwrite("photo_270.jpg", cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE))
    print("4张照片已保存")
else:
    print("拍照失败")
cap.release()