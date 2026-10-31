from io import StringIO
import csv
import pandas as pd
from frontend.exports import export_csv


def test_csv_neutralizes_formula_text_and_headers_without_changing_data():
    frame = pd.DataFrame({'=heading': ['=1+1', '+SUM(A1)', '-2', '@SUM(A1)', '  =1', '\t1', 'ordinary'], 'number': [-2, 2, 3, 4, 5, 6, 7]})
    rows = list(csv.reader(StringIO(export_csv(frame))))
    assert rows[0][0] == "'=heading"
    assert all(row[0].startswith("'") for row in rows[1:7])
    assert rows[-1][0] == 'ordinary' and rows[1][1] == '-2'
    assert frame.iloc[0, 0] == '=1+1' and frame.columns[0] == '=heading'
