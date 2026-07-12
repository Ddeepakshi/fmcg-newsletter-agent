"""Deliverable writers: CSV, JSON, Word, Excel, PowerPoint (spec section 11).

Each writer takes the final structured deal records (+ newsletter text where
relevant) and produces one deliverable file. Kept separate from pipeline.py
so any single output format can be regenerated without re-running the
pipeline.
"""
import json
import logging
import re

import pandas as pd
from docx import Document
from docx.shared import Pt
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.util import Inches, Pt as PptPt

from src.schema import CSV_COLUMN_ORDER

logger = logging.getLogger(__name__)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _markdown_to_plain(line: str) -> str:
    line = _LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", line)
    line = _BOLD_RE.sub(lambda m: m.group(1), line)
    return line


def to_dataframe(records: list) -> pd.DataFrame:
    df = pd.DataFrame(records)
    for col in CSV_COLUMN_ORDER:
        if col not in df.columns:
            df[col] = None
    return df[CSV_COLUMN_ORDER]


def write_csv(records: list, path: str) -> None:
    to_dataframe(records).to_csv(path, index=False)
    logger.info("Wrote CSV: %s (%d rows)", path, len(records))


def write_json(records: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Wrote JSON: %s (%d rows)", path, len(records))


def write_xlsx(records: list, path: str, newsletter_markdown: str = None) -> None:
    """Writes the structured deal table, plus a second "Newsletter" sheet with
    the actual newsletter text (one line per row) when provided — so the
    Excel deliverable carries the newsletter content itself, not just the
    raw data table behind it.
    """
    df = to_dataframe(records)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Deals")
        worksheet = writer.sheets["Deals"]
        for i, col in enumerate(df.columns, start=1):
            max_len = max([len(str(col))] + [len(str(v)) for v in df[col].fillna("")])
            worksheet.column_dimensions[get_column_letter(i)].width = min(max_len + 2, 60)

        if newsletter_markdown:
            plain_lines = [_markdown_to_plain(line) for line in newsletter_markdown.splitlines()]
            newsletter_df = pd.DataFrame({"Newsletter": plain_lines})
            newsletter_df.to_excel(writer, index=False, sheet_name="Newsletter")
            writer.sheets["Newsletter"].column_dimensions["A"].width = 100

    logger.info(
        "Wrote Excel: %s (%d deal rows%s)",
        path, len(records), ", + Newsletter sheet" if newsletter_markdown else "",
    )


def write_docx(newsletter_markdown: str, path: str) -> None:
    doc = Document()
    for raw_line in newsletter_markdown.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            doc.add_paragraph("")
            continue

        if line.startswith("# "):
            doc.add_heading(_markdown_to_plain(line[2:]), level=1)
        elif line.startswith("## "):
            doc.add_heading(_markdown_to_plain(line[3:]), level=2)
        elif line.startswith("### "):
            doc.add_heading(_markdown_to_plain(line[4:]), level=3)
        elif line.strip().startswith("- "):
            doc.add_paragraph(_markdown_to_plain(line.strip()[2:]), style="List Bullet")
        elif line.strip().startswith("*") and line.strip().endswith("*"):
            p = doc.add_paragraph()
            run = p.add_run(_markdown_to_plain(line.strip().strip("*")))
            run.italic = True
            run.font.size = Pt(9)
        else:
            doc.add_paragraph(_markdown_to_plain(line))

    doc.save(path)
    logger.info("Wrote Word doc: %s", path)


def write_pptx(records: list, path: str, top_n: int = 10, title: str = "FMCG Deal Intelligence") -> None:
    prs = Presentation()

    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = title
    title_slide.placeholders[1].text = "Recent M&A, Investment & Funding Activity"

    ranked = sorted(records, key=lambda r: r.get("credibility_score") or 0, reverse=True)[:top_n]

    bullet_slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(bullet_slide_layout)
    slide.shapes.title.text = "Top Deals"
    body = slide.placeholders[1].text_frame
    body.clear()

    if not ranked:
        body.text = "No qualifying deals found in this window."
    else:
        for i, r in enumerate(ranked):
            text = r.get("title", "Untitled")
            deal_type = r.get("deal_type")
            value = r.get("deal_value")
            currency = r.get("currency") or ""
            suffix = []
            if deal_type:
                suffix.append(deal_type)
            if value:
                suffix.append(f"{currency} {value}")
            line = f"{text}" + (f" ({', '.join(suffix)})" if suffix else "")

            if i == 0:
                body.text = line
                body.paragraphs[0].font.size = PptPt(16)
            else:
                p = body.add_paragraph()
                p.text = line
                p.font.size = PptPt(16)

    prs.save(path)
    logger.info("Wrote PowerPoint: %s (%d deals)", path, len(ranked))


def write_all_outputs(records: list, newsletter_markdown: str, output_dir) -> dict:
    """Writes csv/json/docx/xlsx/pptx into `output_dir`, returns their paths."""
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "csv": output_dir / "deals.csv",
        "json": output_dir / "deals.json",
        "docx": output_dir / "newsletter.docx",
        "xlsx": output_dir / "deals.xlsx",
        "pptx": output_dir / "newsletter.pptx",
    }

    write_csv(records, str(paths["csv"]))
    write_json(records, str(paths["json"]))
    write_docx(newsletter_markdown, str(paths["docx"]))
    write_xlsx(records, str(paths["xlsx"]), newsletter_markdown=newsletter_markdown)
    write_pptx(records, str(paths["pptx"]))

    return {k: str(v) for k, v in paths.items()}


if __name__ == "__main__":
    import os
    import tempfile

    sample_records = [
        {"title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "Deal expected to close in Q3",
         "source": "Economic Times", "source_tier": 1, "published_date": "2026-07-11T00:00:00+00:00",
         "url": "https://a.com/1", "region": "India", "is_duplicate_of": None, "credibility_score": 0.91,
         "acquirer": "ITC", "target": "Prasuma Foods", "deal_type": "Acquisition", "deal_value": 150,
         "currency": "USD", "relevance_flag": "Relevant"},
    ]
    sample_newsletter = (
        "# FMCG Deal Intelligence Newsletter\n\n## Recent Deal Activity\n\n"
        "- **ITC to acquire Prasuma Foods for $150 million**\n  Source: [Economic Times](https://a.com/1)\n"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        paths = write_all_outputs(sample_records, sample_newsletter, tmp_dir)
        for fmt, path in paths.items():
            size = os.path.getsize(path)
            print(f"{fmt}: {path} ({size} bytes)")
            assert size > 0, f"{fmt} output is empty"

        from openpyxl import load_workbook

        wb = load_workbook(paths["xlsx"])
        assert "Newsletter" in wb.sheetnames, "xlsx should carry a Newsletter sheet, not just raw deal data"

    print("All output writers produced non-empty files.")
