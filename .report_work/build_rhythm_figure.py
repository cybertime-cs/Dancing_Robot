from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "韵律识别模型优化"
OUT.mkdir(parents=True, exist_ok=True)
TARGET = OUT / "韵律识别方法对比.png"

W, H = 2200, 1630
im = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(im)
font = r"C:\Windows\Fonts\msyh.ttc"
bold = r"C:\Windows\Fonts\msyhbd.ttc"
f_title = ImageFont.truetype(bold, 62)
f_section = ImageFont.truetype(bold, 43)
f_box = ImageFont.truetype(font, 35)
f_small = ImageFont.truetype(font, 31)
f_note = ImageFont.truetype(font, 28)

ink = "#18324A"
blue = "#286F9D"
blue_fill = "#E9F3F9"
gray = "#68727B"
gray_fill = "#F1F3F5"
line = "#C7D2DB"

def text_center(lines, xy, face=f_box, color=ink, gap=8):
    if isinstance(lines, str):
        lines = lines.split("\n")
    x0, y0, x1, y1 = xy
    heights = [d.textbbox((0, 0), s, font=face)[3] for s in lines]
    y = (y0 + y1 - sum(heights) - gap * (len(lines)-1)) / 2
    for s, h in zip(lines, heights):
        width = d.textlength(s, font=face)
        d.text(((x0+x1-width)/2, y), s, font=face, fill=color)
        y += h + gap

def box(xy, lines, old=False, face=f_box):
    d.rounded_rectangle(xy, radius=19, fill=gray_fill if old else blue_fill,
                        outline=gray if old else blue, width=4)
    text_center(lines, xy, face=face)

def arrow(x0, y0, x1, y1, old=False):
    color = gray if old else blue
    d.line([(x0,y0),(x1,y1)], fill=color, width=5)
    import math
    a = math.atan2(y1-y0, x1-x0)
    pts = [(x1,y1)]
    for da in (2.55,-2.55):
        pts.append((x1 + 20*math.cos(a+da), y1 + 20*math.sin(a+da)))
    d.polygon(pts, fill=color)

d.text((88, 45), "韵律识别方法对比", font=f_title, fill=ink)
d.text((90, 172), "选拔赛方案", font=f_section, fill=gray)

old_boxes = [
    ((90, 250, 395, 415), "录音输入"),
    ((520, 250, 825, 415), "提取节拍点"),
    ((950, 250, 1255, 415), "节拍帧序列\n计算 delta"),
    ((1380, 250, 1685, 415), "计算 DTW 距离"),
    ((1810, 250, 2115, 415), "输出距离\n最小的类别"),
]
for coords, label in old_boxes:
    x0, y0, x1, y1 = coords
    box((x0,y0,x1,y1), label, old=True)
for a, b in zip(old_boxes, old_boxes[1:]):
    arrow(a[0][2], 332, b[0][0]-18, 332, old=True)

d.line([(88,485),(2112,485)], fill=line, width=3)
d.text((90, 525), "本阶段方案", font=f_section, fill=blue)
d.text((90, 630), "建库", font=f_section, fill=ink)

train = [
    ((260, 605, 645, 760), "约 15 秒\n参考 WAV"),
    ((805, 605, 1190, 760), "四频段能量\n变化特征"),
    ((1350, 605, 1735, 760), "压缩特征库\n.npz"),
]
for coords, label in train:
    box(coords, label)
for a,b in zip(train,train[1:]):
    arrow(a[0][2],682,b[0][0]-18,682)

d.text((90, 853), "识别", font=f_section, fill=ink)
infer = [
    ((260, 820, 600, 995), "现场录音"),
    ((690, 820, 1030, 995), "同样的四频段\n特征提取"),
    ((1120, 820, 1460, 995), "8 秒窗口\n滑动相关匹配"),
    ((1550, 820, 1890, 995), "最高分及\n领先差距判定"),
]
for coords, label in infer:
    box(coords, label, face=f_small)
for a,b in zip(infer,infer[1:]):
    arrow(a[0][2],907,b[0][0]-18,907)
box((1550, 1050, 1890, 1170), "类别 / 未识别", face=f_small)
arrow(1720,995,1720,1033)
d.line([(1542,760),(1542,790),(1290,790),(1290,802)], fill=blue, width=5)
arrow(1290,802,1290,820)

d.line([(88,1240),(2112,1240)], fill=line, width=3)
d.text((90, 1280), "当前音频验证", font=f_section, fill=ink)
d.text((90, 1360), "5 段约 15 秒音频：原始输入 5/5，模拟扰动输入 20/20，合计 25/25 正确。", font=f_small, fill=ink)
d.text((90, 1435), "choice.wav 超过 15 秒，本轮未纳入。测试使用同源音频，实机录音效果仍需验证。", font=f_note, fill=gray)

im.save(TARGET, dpi=(300,300))
print(TARGET)
