from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)
PDF = OUT / "机器人语音人机交互流程技术验证报告.pdf"
FIG = OUT / "人机交互技术流程图.png"
pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))

page_w, page_h = A4
body = ParagraphStyle("body", fontName="SimHei", fontSize=9.6, leading=16.5, spaceAfter=7, textColor=colors.HexColor("#222222"))
title = ParagraphStyle("title", parent=body, fontSize=18, leading=27, spaceAfter=15, textColor=colors.black)
h1 = ParagraphStyle("h1", parent=body, fontSize=12.5, leading=20, spaceBefore=14, spaceAfter=8, textColor=colors.black)
caption = ParagraphStyle("caption", parent=body, fontSize=8.5, leading=13, alignment=TA_CENTER, spaceBefore=4)
cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=12, spaceAfter=0)
headcell = ParagraphStyle("headcell", parent=cell, textColor=colors.black)

def P(text, style=body):
    return Paragraph(text, style)

story = []
story.append(P("机器人语音人机交互流程技术验证报告", title))
story.append(P("<b>验证对象：</b>机器人程序中的语音问答流程，重点检查 interaction_zh.py 及其入口调用。"))
story.append(P("<b>结论：</b>代码已形成“语音识别—本地模型生成—语音播报”的处理链。静态检查和隔离测试通过；当前环境未连接机器人及其 Ollama 服务，整机运行效果仍需现场验证。"))
story.append(P("一  流程范围", h1))
story.append(P("主程序通过 Snowboy 检测唤醒词，随后用 Vosk 把语音转成文字。action_neo.py 根据 speech_train.json 匹配“交互”指令，进入连续提问。用户说“结束”或“退出”时离开该模式。"))
story.append(P("二  技术流程图", h1))
story.append(Image(str(FIG), width=490, height=490*1770/2000))
story.append(P("流程图依据当前代码绘制，箭头表示实际调用顺序", caption))
story.append(PageBreak())

story.append(P("三  关键环节说明", h1))
items = [
    ("入口和分流", "snowboydecoder.py 在检测到唤醒词后调用 robot_process()，先执行 speech_recog()，再交由 action_neo() 匹配关键词。action_neo() 会先读取 speech_train.json 并初始化串口，然后进入 interaction_mode 分支。"),
    ("语音转写", "speech_recog.py 使用名为 snowboy_mic 的输入设备，以 16 kHz、单声道、16 位采集音频，保存为临时 WAV 文件，再交给本地 Vosk 模型识别。代码传入的录音参数为 3；按每次读取 2000 帧、循环 30 次计算，理论采样时长约 3.75 秒，实际耗时还受设备读入影响。"),
    ("模型请求", "interaction_zh.py 创建指向 127.0.0.1:11434 的 Ollama 客户端，调用 chat 接口，模型名为 qwen:0.5b，开启流式返回。每次请求只发送本轮问题，没有附带历史消息。num_predict 为 128，temperature 为 0.7，num_ctx 为 512，num_thread 为 2。"),
    ("输出与播报", "收到数据块后，程序从 message.content 读取文本并拼接成完整回复。播报前只去除 * 和 #；当新块含句末标点或换行，或者缓冲文本超过 30 字时，调用 espeak 中文语音播报。播报为同步执行，完成后才继续读取后续数据块。流结束后还会播报剩余文本。"),
    ("退出和异常", "交互循环在识别文本包含“结束”或“退出”时退出。Ollama 请求建立失败时函数返回错误文字；流迭代中断时会打印错误，播报已有缓冲并返回已收到的内容。上层打印的 len(response) 是字符数，不是模型 token 数。"),
]
for head, text in items:
    story.append(P(f"<b>{head}。</b>{text}"))

story.append(P("四  验证记录", h1))
data = [
    ("检查项", "方法", "结果"),
    ("代码及词表可解析", "编译检查 4 个 Python 文件，解析 speech_train.json", "通过"),
    ("模型请求参数", "隔离 Ollama 客户端，检查地址、模型、单轮消息和流式标志", "通过"),
    ("流式处理", "输入两段模拟回复，检查原文拼接、标记清理和剩余文本播报", "通过"),
    ("流中断", "模拟已收到一段内容后抛出异常", "返回部分内容，并播报缓冲"),
    ("整机语音交互", "需在机器人上连同麦克风、串口、Ollama 和 espeak 测试", "未执行"),
]
tdata = [[P(v, headcell if i == 0 else cell) for v in row] for i, row in enumerate(data)]
table = Table(tdata, colWidths=[105, 306, 80], repeatRows=1, hAlign="LEFT")
table.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#DCEAF2")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F7FAFC")]),
    ("GRID",(0,0),(-1,-1),0.45,colors.HexColor("#D9D9D9")),
    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ("LEFTPADDING",(0,0),(-1,-1),7),
    ("RIGHTPADDING",(0,0),(-1,-1),7),
    ("TOPPADDING",(0,0),(-1,-1),6),
    ("BOTTOMPADDING",(0,0),(-1,-1),6),
]))
story.append(table)
story.append(P("五  结论和待验证点", h1))
story.append(P("现有代码具备本地语音问答的基本链路，隔离测试覆盖了 Ollama 调用格式和流式回复处理。交付前仍需在目标机器人上完成端到端测试，记录唤醒、首句播报、连续提问、退出和再次唤醒的实际结果及耗时。"))
story.append(P("当前实现还需重点核对三处：一是进入交互模式前必须成功打开串口；二是 Snowboy 的输入流在唤醒后被关闭，代码未见重新打开，退出交互后能否再次唤醒需现场确认；三是机器人入口没有加入命令行测试中的“红莲”角色说明，模型回答不保证带有该身份设定。"))

def footer(canvas, doc):
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawRightString(page_w-52, 32, str(doc.page))

pdf = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=52, rightMargin=52, topMargin=50, bottomMargin=48)
pdf.build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)
