"""Shared AskDB wordmark: a speaking database, animated with lightweight CSS."""
from pathlib import Path

MARK_PATH = Path(__file__).with_name('static') / 'askdb-mark.svg'
_mark = MARK_PATH.read_text().replace('<svg ', '<svg class="askdb-mark" aria-hidden="true" ')
# Expose the eyes and database rows for independent animation without SVG IDs.
_mark = _mark.replace('<g fill="#20342b">', '<g class="askdb-eyes" fill="#20342b">')
_mark = _mark.replace('<path d="M21 40', '<path class="askdb-row row-one" d="M21 40')


def logo(compact=False):
    name = '' if compact else '<span class="askdb-name">Ask<span>DB</span></span>'
    return f'<span class="askdb-logo" role="img" aria-label="AskDB — Your data. Just ask.">{_mark}{name}</span>'
