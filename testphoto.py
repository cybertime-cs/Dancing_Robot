from datetime import datetime
from pathlib import Path
import time

import cv2


BASE_DIR = Path(__file__).resolve().parent
SAVE_DIR = BASE_DIR / "camera_photos"

CAMERA_INDEX = 0
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720

# 要保存的画面旋转角度
SAVE_ANGLES = (0, 90, 180, 270)


def rotate_frame(frame, angle: int):
    """
    将画面顺时针旋转指定角度。
    支持 0、90、180、270。
    """
    angle = angle % 360

    if angle == 0:
        return frame.copy()

    if angle == 90:
        return cv2.rotate(
            frame,
            cv2.ROTATE_90_CLOCKWISE,
        )

    if angle == 180:
        return cv2.rotate(
            frame,
            cv2.ROTATE_180,
        )

    if angle == 270:
        return cv2.rotate(
            frame,
            cv2.ROTATE_90_COUNTERCLOCKWISE,
        )

    raise ValueError(
        f"不支持角度 {angle}，"
        "只支持 0、90、180、270"
    )


def capture_clear_frame(cap, warmup_frames: int = 15):
    """
    丢弃摄像头启动时的前几帧，
    等待曝光和白平衡稳定后再拍照。
    """
    frame = None

    for _ in range(warmup_frames):
        success, current_frame = cap.read()

        if success and current_frame is not None:
            frame = current_frame

        time.sleep(0.03)

    if frame is None:
        raise RuntimeError("无法从摄像头读取画面")

    return frame


def save_camera_angles(
    camera_index: int = CAMERA_INDEX,
    angles: tuple[int, ...] = SAVE_ANGLES,
) -> list[Path]:
    """
    拍摄一张照片，并保存不同旋转方向的版本。

    返回所有成功保存的文件路径。
    """
    SAVE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cap = cv2.VideoCapture(
        camera_index,
        cv2.CAP_V4L2,
    )

    if not cap.isOpened():
        raise RuntimeError(
            f"无法打开摄像头：/dev/video{camera_index}"
        )

    try:
        cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            IMAGE_WIDTH,
        )
        cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            IMAGE_HEIGHT,
        )

        frame = capture_clear_frame(cap)

    finally:
        cap.release()

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    saved_files: list[Path] = []

    for angle in angles:
        rotated_frame = rotate_frame(
            frame,
            angle,
        )

        output_file = (
            SAVE_DIR
            / f"camera_{timestamp}_{angle}deg.jpg"
        )

        success = cv2.imwrite(
            str(output_file),
            rotated_frame,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                95,
            ],
        )

        if not success:
            print(f"保存失败：{output_file}")
            continue

        saved_files.append(output_file)
        print(f"已保存：{output_file}")

    return saved_files


if __name__ == "__main__":
    try:
        files = save_camera_angles()

        print(f"\n共保存 {len(files)} 张照片")

    except KeyboardInterrupt:
        print("\n用户终止拍照")

    except Exception as error:
        print(f"拍照失败：{error}")