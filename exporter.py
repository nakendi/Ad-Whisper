"""Excel and CSV export module for AdWhisper.

Creates reports adhering strictly to requirements:
Columns: Видео | Просмотры | Вариант | Транскрипция | Таймкод | Уверенность
Categories: Вариант №1, Вариант №2, Вариант №3, Ничего не найдено, Недостаточное качество
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config import TARGET_VARIANTS
from database import Database

logger = logging.getLogger(__name__)

class ReportExporter:
    def __init__(self, db: Database, export_dir: str = "data/exports"):
        self.db = db
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _get_variant_display_name(self, variant_code: Optional[str]) -> str:
        if not variant_code or variant_code == "none":
            return "Не найдено"
        if variant_code in TARGET_VARIANTS:
            return TARGET_VARIANTS[variant_code].name
        return variant_code

    def export_csv(self, filename: Optional[str] = None,
                   start_date: Optional[Any] = None,
                   end_date: Optional[Any] = None) -> Path:
        """Exports all results to CSV with utf-8-sig encoding for Russian Excel."""
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tiktok_scanner_report_{ts}.csv"
        file_path = self.export_dir / filename

        rows = self.db.get_results_table_data(start_date=start_date, end_date=end_date)

        headers = ["Видео ID", "Ссылка на TikTok", "Просмотры", "Дата публикации",
                   "Вариант", "Таймкод", "Уверенность (%)", "Транскрипция", "Статус/Заметки"]

        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in rows:
                variant_name = self._get_variant_display_name(r.get("variant"))
                conf_pct = f"{int((r.get('confidence') or 0.0) * 100)}%" if r.get("variant") not in (None, "none") else "-"
                notes = r.get("error_message") or ("Сомнительно" if r.get("is_doubtful") else "ОК")
                
                writer.writerow([
                    r.get("video_id"),
                    r.get("video_url"),
                    r.get("views", 0),
                    r.get("upload_date", ""),
                    variant_name,
                    r.get("timecode", "-"),
                    conf_pct,
                    r.get("transcription", ""),
                    notes
                ])

        logger.info("CSV exported to %s", file_path)
        self.rotate_exports(max_count=15)
        return file_path

    def export_excel(self, filename: Optional[str] = None,
                     start_date: Optional[Any] = None,
                     end_date: Optional[Any] = None) -> Path:
        """Generates a multi-sheet formatted Excel workbook (.xlsx)."""
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tiktok_scanner_report_{ts}.xlsx"
        file_path = self.export_dir / filename

        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        # Style templates
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        border_side = Side(style="thin", color="D9D9D9")
        thin_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        right_align = Alignment(horizontal="right", vertical="center")

        categories = [
            ("Все совпадения", None, "matches_all"),
            ("Вариант №1 (Caser)", "variant_1", "category"),
            ("Вариант №2 (Upgrader)", "variant_2", "category"),
            ("Вариант №3 (DotaGrade)", "variant_3", "category"),
            ("Ничего не найдено", "not_found", "category"),
            ("Ошибки и низкое качество", "poor_quality", "category"),
        ]

        headers = ["Видео", "Просмотры", "Вариант", "Таймкод", "Уверенность", "Транскрипция"]

        for sheet_title, filter_val, mode in categories:
            ws = wb.create_sheet(title=sheet_title)
            ws.views.sheetView[0].showGridLines = True

            # Write header row
            for col_num, h_text in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=h_text)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border
            ws.row_dimensions[1].height = 26

            # Query data
            if mode == "matches_all":
                # Combine variants 1, 2, 3
                raw_rows = self.db.get_results_table_data(variant_filter="all_matches", start_date=start_date, end_date=end_date)
            else:
                raw_rows = self.db.get_results_table_data(variant_filter=filter_val, start_date=start_date, end_date=end_date)

            # Write data rows
            for row_idx, r in enumerate(raw_rows, 2):
                v_url = r.get("video_url", "")
                views = r.get("views", 0)
                variant_name = self._get_variant_display_name(r.get("variant"))
                timecode = r.get("timecode") or "-"
                conf = r.get("confidence") or 0.0
                conf_str = f"{int(conf * 100)}%" if r.get("variant") not in (None, "none") else "-"
                transcription = r.get("transcription", "") or (r.get("error_message") if mode == "poor_quality" else "")

                # Cell 1: Link
                c1 = ws.cell(row=row_idx, column=1, value=v_url)
                if v_url.startswith("http"):
                    c1.hyperlink = v_url
                    c1.font = Font(name="Calibri", color="0563C1", underline="single")
                c1.alignment = left_align
                c1.border = thin_border

                # Cell 2: Views
                c2 = ws.cell(row=row_idx, column=2, value=views)
                c2.number_format = "#,##0"
                c2.alignment = right_align
                c2.border = thin_border

                # Cell 3: Variant
                c3 = ws.cell(row=row_idx, column=3, value=variant_name)
                c3.alignment = center_align
                c3.border = thin_border

                # Cell 4: Timecode
                c4 = ws.cell(row=row_idx, column=4, value=timecode)
                c4.alignment = center_align
                c4.border = thin_border

                # Cell 5: Confidence
                c5 = ws.cell(row=row_idx, column=5, value=conf_str)
                c5.alignment = center_align
                c5.border = thin_border

                # Cell 6: Transcription
                c6 = ws.cell(row=row_idx, column=6, value=transcription)
                c6.alignment = left_align
                c6.border = thin_border

                ws.row_dimensions[row_idx].height = 22

            # Column widths
            ws.column_dimensions["A"].width = 40
            ws.column_dimensions["B"].width = 15
            ws.column_dimensions["C"].width = 30
            ws.column_dimensions["D"].width = 16
            ws.column_dimensions["E"].width = 15
            ws.column_dimensions["F"].width = 65

        # Summary Sheet
        ws_sum = wb.create_sheet(title="Сводка сканирования", index=0)
        ws_sum.views.sheetView[0].showGridLines = True
        stats = self.db.get_summary_stats()

        summary_rows = [
            ("Параметр", "Значение"),
            ("Аккаунт TikTok", "@twitch.clown"),
            ("Дата формирования отчёта", datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
            ("Всего публикаций в базе", stats["total_collected"]),
            ("Отфильтровано по дате", stats["filtered_date"]),
            ("Отфильтровано по просмотрам (<= 2000)", stats["filtered_views"]),
            ("Успешно проанализировано видео", stats["total_analyzed"]),
            ("Найдено: Вариант №1 (Caser)", stats["variant_1"]),
            ("Найдено: Вариант №2 (Upgrader)", stats["variant_2"]),
            ("Найдено: Вариант №3 (DotaGrade)", stats["variant_3"]),
            ("Сомнительных совпадений (требуют Demucs)", stats["doubtful"]),
            ("Видео без рекламы (не найдено)", stats["not_found"]),
            ("Ошибки / недостаточный звук", stats["poor_quality"]),
        ]

        for r_idx, (k, v) in enumerate(summary_rows, 1):
            c_k = ws_sum.cell(row=r_idx, column=1, value=k)
            c_v = ws_sum.cell(row=r_idx, column=2, value=v)
            c_k.border = thin_border
            c_v.border = thin_border
            if r_idx == 1:
                c_k.font = header_font
                c_k.fill = header_fill
                c_v.font = header_font
                c_v.fill = header_fill
            else:
                c_k.font = Font(name="Calibri", bold=(r_idx in (4, 7, 8, 9, 10)))
                c_v.font = Font(name="Calibri", bold=(r_idx in (4, 7, 8, 9, 10)))

        ws_sum.column_dimensions["A"].width = 42
        ws_sum.column_dimensions["B"].width = 25

        wb.save(file_path)
        self.rotate_exports(max_count=15)
        logger.info("Excel report exported to %s", file_path)
        return file_path

    def rotate_exports(self, max_count: int = 15) -> None:
        """Keeps only the most recent export files in data/exports, cleaning up older ones."""
        try:
            reports = sorted(
                list(self.export_dir.glob("tiktok_scanner_report_*.*")),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if len(reports) > max_count:
                for old_f in reports[max_count:]:
                    try:
                        old_f.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Export rotation notice: %s", e)
