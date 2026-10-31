"""Spreadsheet-safe CSV exports; source records themselves are never changed."""
import unicodedata


def safe_cell(value):
    if isinstance(value, str) and (value.startswith(('\t', '\r', '\n')) or unicodedata.normalize('NFKC', value).lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def export_csv(frame):
    safe = frame.map(safe_cell)
    safe.columns = [safe_cell(name) for name in frame.columns]
    return safe.to_csv(index=False)
