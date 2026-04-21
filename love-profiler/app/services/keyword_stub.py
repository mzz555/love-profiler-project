"""
Keyword stub — placeholder for the emotional case keyword library.

TODO: Replace with real implementation reading the Excel file at:
  C:\\Users\\Admin\\Desktop\\情感案例采集关键词库.xlsx

Usage:
  from app.services.keyword_stub import load_keyword_hints
  hints = load_keyword_hints("separation_anxiety")  # returns [] until implemented
"""


def load_keyword_hints(category: str) -> list[str]:
    """Return keyword hints for the given signal category.

    Returns empty list until the Excel file is wired up.
    To implement: use openpyxl to read rows where column[0] == category.
    """
    # TODO: implement Excel parsing
    # import openpyxl
    # wb = openpyxl.load_workbook(r"C:\Users\Admin\Desktop\情感案例采集关键词库.xlsx")
    # ws = wb.active
    # return [row[1] for row in ws.iter_rows(values_only=True) if row[0] == category]
    return []
