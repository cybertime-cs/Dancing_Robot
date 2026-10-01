from pathlib import Path
import pypdfium2 as pdfium
import win32com.client

root = Path(__file__).resolve().parents[1]
docx = root / "reports" / "机器人语音人机交互流程技术验证报告.docx"
out = root / ".report_work" / "render"
out.mkdir(exist_ok=True)
pdf = out / "report.pdf"
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    document = word.Documents.Open(str(docx), ReadOnly=True)
    try:
        document.ExportAsFixedFormat(str(pdf), 17)
    finally:
        document.Close(False)
finally:
    word.Quit()

rendered = pdfium.PdfDocument(str(pdf))
for i in range(len(rendered)):
    page = rendered[i]
    image = page.render(scale=2).to_pil()
    image.save(out / f"page-{i+1}.png")
print(f"rendered_pages={len(rendered)}")
