import argparse
from pathlib import Path
import copy
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", default=str(Path(__file__).resolve().parent))
args = parser.parse_args()
ROOT = Path(args.work_dir).resolve()
source = ROOT / "source-pgm.xml"
out = ROOT / "candidate-v1.xml"
tree = ET.parse(source)
slide = tree.getroot()
ns = slide.tag[1:].split("}")[0]
ET.register_namespace("", ns)

def local(el):
    return el.tag.split("}")[-1]

def set_shape_text(shape_id, lines):
    shape = next(e for e in slide.iter() if local(e) == "shape" and e.get("id") == shape_id)
    content = next(e for e in shape if local(e) == "content")
    for child in list(content):
        content.remove(child)
    for line in lines:
        p = ET.SubElement(content, f"{{{ns}}}p")
        p.text = line

shape_text = {
    "bTRW": ["12/12 + 21/21 · VERIFIED"],
    "bTRQ": ["RK02 · FIXED-GFP OBSERVED-R1 STRUCTURE"],
    "bTRB": ["观测 R1 MFE 未显示已验证的开发集增量"],
    "bTRz": [
        "152 R1 variants · 5-fold OOF · ridge alpha = 1 · 300 nt full / 48 nt-window MFE",
        "20,000 paired bootstrap + 20,000 sign flips · Holm across 2 primary endpoints",
    ],
    "bTMm": ["SIMPLE · OOF SPEARMAN"],
    "bTRx": ["+0.413234"],
    "bTRI": ["RMSE 1.383987 · MSE 1.915421"],
    "bTMG": ["+ OBSERVED R1 MFE"],
    "bTRc": ["+0.408983"],
    "bTRV": ["RMSE 1.382025 · MSE 1.909992"],
    "bTMD": ["FROZEN DECISION"],
    "bTRo": ["NO-GO"],
    "bTRZ": ["development only · both CIs cross zero"],
    "bTRg": ["OOF REFERENCES + PRIMARY TREATMENT-MINUS-SIMPLE EFFECTS"],
    "bTMM": ["FROZEN DESIGN + INDEPENDENCE"],
    "bTRm": [
        "simple = log depth + GC + GC3 + CpG + CAI",
        "+structure = full MFE + 48 nt min / mean",
        "folds 31 / 31 / 30 / 30 / 30 · no tuning",
        "feature max abs diff = 2.78e-16",
        "prediction max abs diff = 1.07e-14",
        "paper update 38/38 PASS",
    ],
    "bTRq": [
        "结论 · 两个主终点均未通过方向门禁",
        "区间跨零 · 微小 MSE 下降不确定",
    ],
    "bTRG": [
        "边界 · 仅限固定 GFP observed-R1 development",
        "非完整 CDS · 非蛋白 OOD · 非普遍结构证伪",
    ],
    "bTRd": ["Evidence: independent 12/12 · finalization 21/21 · paper 38/38 · GitHub 1388ac627f23"],
    "bTRe": ["RK02 · 2026-11-19"],
}
for shape_id, lines in shape_text.items():
    set_shape_text(shape_id, lines)

# Turn the decision card from positive green to cautious amber.
for element_id, color in {
    "bTRH": "rgba(255, 247, 237, 1)",
}.items():
    shape = next(e for e in slide.iter() if e.get("id") == element_id)
    fill_color = next(e for e in shape.iter() if local(e) == "fillColor")
    fill_color.set("color", color)
    border = next(e for e in shape if local(e) == "border")
    border.set("color", "rgba(253, 186, 116, 1)")
for element_id in ("bTRo",):
    shape = next(e for e in slide.iter() if e.get("id") == element_id)
    content = next(e for e in shape if local(e) == "content")
    content.set("color", "rgba(154, 52, 18, 1)")

# Table: preserve the existing visual system, replace only the authorized content.
table = next(e for e in slide.iter() if local(e) == "table" and e.get("id") == "bTMO")
widths = [80, 88, 105, 156, 115]
for col, width in zip(next(e for e in table if local(e) == "colgroup"), widths):
    col.set("width", str(width))
rows = [e for e in table if local(e) == "tr"]
values = [
    ["Analysis", "Endpoint", "Estimate", "95% CI / RMSE", "Holm p"],
    ["OOF simple", "Spearman", "+0.413234", "RMSE 1.383987", "reference"],
    ["OOF +MFE", "Spearman", "+0.408983", "RMSE 1.382025", "compare"],
    ["Primary delta", "Spearman", "−0.004251", "[−0.055205, +0.046336]", "1.0"],
    ["Primary delta", "MSE", "−0.005429", "[−0.089604, +0.076766]", "1.0"],
    ["Verification", "independent", "12/12", "final 21/21", "PASS"],
]
assert len(rows) == len(values) == 6
for tr, row_values in zip(rows, values):
    cells = [e for e in tr if local(e) == "td"]
    assert len(cells) == 5
    for td, value in zip(cells, row_values):
        content = next(e for e in td if local(e) == "content")
        for child in list(content):
            content.remove(child)
        p = ET.SubElement(content, f"{{{ns}}}p")
        p.text = value

note = next(e for e in slide if local(e) == "note")
note_content = next(e for e in note if local(e) == "content")
for child in list(note_content):
    note_content.remove(child)
notes = [
    "这一页只报告固定 GFP 的 152 个观测 R1 变体上的 development-only 结构增量分析。simple 与 simple-plus-structure 的 OOF Spearman 分别为 0.4132340981007251 和 0.4089831122410623。",
    "treatment-minus-simple 的 Spearman 增量为 -0.00425098585966277，95% CI 为 [-0.05520539205719149, 0.04633584918114156]，Holm p 为 1.0；MSE 增量为 -0.005428627465626112，95% CI 为 [-0.08960370674454726, 0.07676584869175301]，Holm p 也为 1.0。",
    "独立复算 12/12 通过，科学 finalization 21/21 通过，论文精确增量核验 38/38 通过。两项区间跨零且未满足方向门禁，因此结论为 development no-go；微小 MSE 下降不确定。",
    "结论仅限观测 300 nt R1 的 full MFE 与连续 48 nt 窗口 MFE min/mean，不是完整 CDS、蛋白 OOD、独立确认性检验或普遍 RNA 结构证伪；RK-G1 仍为 false，也不授权生成器训练。",
]
for text in notes:
    p = ET.SubElement(note_content, f"{{{ns}}}p")
    p.text = text

# New-page IDs are assigned by the server; never reuse IDs from the source page.
for element in slide.iter():
    element.attrib.pop("id", None)

ET.ElementTree(slide).write(out, encoding="utf-8", xml_declaration=False)

# Offline structural and content checks; online acceptance is performed separately.
check = ET.parse(out).getroot()
assert local(check) == "slide"
assert check.get("id") is None
assert any(local(e) == "note" for e in check)
text = " ".join(t.strip() for t in check.itertext() if t.strip())
required = [
    "+0.413234", "+0.408983", "−0.004251", "−0.005429",
    "[−0.055205, +0.046336]", "[−0.089604, +0.076766]",
    "12/12", "21/21", "38/38", "NO-GO", "非普遍结构证伪",
]
for item in required:
    assert item in text, item
for forbidden in ["18/18 + 8/8", "GC3 rho range", "简单序列代理并非无信号"]:
    assert forbidden not in text, forbidden
for el in check.iter():
    if local(el) in {"shape", "table", "img", "icon", "embed"}:
        x = float(el.get("topLeftX", "0")); y = float(el.get("topLeftY", "0"))
        w = float(el.get("width", "0")); h = float(el.get("height", "0"))
        assert x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540, (local(el), x, y, w, h)
assert len([e for e in check.iter() if local(e) == "tr"]) == 6
print(f"candidate={out.name} bytes={out.stat().st_size} offline_checks=PASS")
