"""Visualize returned records only; never manufacture totals or missing data."""
from html import escape
import pandas as pd
import streamlit as st


def numeric_columns(frame):
    columns = []
    for name in frame:
        if name.lower() == 'id' or name.lower().endswith('_id') or pd.api.types.is_bool_dtype(frame[name]):
            continue
        values = frame[name].dropna()
        if len(values) and pd.to_numeric(values, errors='coerce').notna().all():
            columns.append(name)
    return columns


def render_charts(frame, key):
    numbers = numeric_columns(frame)
    if not numbers or len(frame) < 2:
        st.caption('Charts need at least two comparable records. See this record in Data.' if len(frame) == 1 else 'This result has no numeric measures to chart. Explore the records in Data.')
        return
    dimensions = [c for c in frame if c not in numbers and c.lower() != 'id' and not c.lower().endswith('_id')]
    kinds = ['Bar', 'Line', 'Donut'] if dimensions else ['Scatter'] if len(numbers) > 1 else ['Bar']
    kind_col, measure_col, group_col = st.columns([1, 1, 1])
    kind = kind_col.selectbox('Chart style', kinds, key=f'chart_kind_{key}')
    measure = measure_col.selectbox('Measure', numbers, key=f'chart_measure_{key}')
    groups = dimensions if dimensions else [n for n in numbers if n != measure] if kind == 'Scatter' else numbers
    group = group_col.selectbox('Group / X axis', groups, key=f'chart_group_{key}')
    values = pd.to_numeric(frame[measure], errors='coerce').replace([float('inf'), -float('inf')], float('nan'))
    if dimensions:
        plotted = pd.DataFrame({'label': frame[group].fillna('(missing)').astype(str), 'value': values}).groupby('label', sort=False, as_index=False)['value'].sum(min_count=1).dropna()
        st.caption(f'Sum of {measure.replace("_", " ")} by {group.replace("_", " ")}, using only the returned rows. Repeated labels are combined.')
    else:
        plotted = pd.DataFrame({'label': [f'Row {i+1}' for i in range(len(frame))], 'value': values}).dropna()
        st.caption('Values from the returned rows; row numbers are display positions, not dates.')
    if plotted.empty:
        st.info('No non-empty numeric values to plot.')
        return
    if kind == 'Donut' and ((plotted.value < 0).any() or plotted.value.sum() <= 0):
        st.info('Donut charts require non-negative values with a positive total. Choose Bar or Line for this result.')
        return
    if kind == 'Bar' and len(plotted) <= 20 and (plotted.value >= 0).all():
        maximum = max(float(plotted.value.max()), 1e-12)
        bars = ''.join(f'<div class="picture-row" style="--delay:{min(i*.045,.6):.3f}s"><span class="picture-label">{escape(str(row.label))}</span><div class="picture-track"><div class="picture-bar" style="width:{float(row.value)/maximum*100:.4f}%"></div></div><b>{float(row.value):,.4g}</b></div>' for i, row in plotted.iterrows())
        st.markdown(f'<div class="data-picture" role="img" aria-label="Bar chart of {escape(measure, quote=True)} by {escape(group, quote=True)}">{bars}</div>', unsafe_allow_html=True)
        st.caption('Bars share a zero baseline. Largest displayed value fills the scale.')
        return
    encoding = {'tooltip': [{'field': 'label', 'type': 'nominal'}, {'field': 'value', 'type': 'quantitative'}]}
    light = st.session_state.get('light_mode', False)
    ink, muted, grid = ('#171b2d', '#645a37', '#d8cfb4') if light else ('#fffaf0', '#ddd4bc', '#566079')
    accent = '#007eff' if light else '#ffbf00'
    spec = {'height': 320, 'background': 'transparent', 'config': {'view': {'stroke': None}, 'axis': {'labelColor': muted, 'titleColor': ink, 'gridColor': grid}, 'legend': {'labelColor': muted, 'titleColor': ink}, 'range': {'category': ['#ffbf00', '#807040', '#007eff', '#2400ff', '#171b2d']}}}
    if kind == 'Donut':
        spec['mark'] = {'type': 'arc', 'innerRadius': 85, 'cornerRadius': 0, 'stroke': '#000000', 'strokeWidth': 2}
        encoding.update(theta={'field': 'value', 'type': 'quantitative'}, color={'field': 'label', 'type': 'nominal', 'title': group, 'legend': {'orient': 'bottom', 'columns': 2, 'labelLimit': 90, 'titleLimit': 180}})
        st.caption('Share of the selected measure across returned rows; use only for additive measures.')
    elif kind == 'Scatter':
        x_values = pd.to_numeric(frame[group], errors='coerce').replace([float('inf'), -float('inf')], float('nan'))
        plotted = pd.DataFrame({'label': x_values, 'value': values}).dropna()
        spec['mark'] = {'type': 'circle', 'color': accent, 'stroke': ink, 'strokeWidth': 1, 'size': 85}
        encoding.update(x={'field': 'label', 'type': 'quantitative', 'title': group}, y={'field': 'value', 'type': 'quantitative', 'title': measure})
    else:
        if kind == 'Line':
            plotted = plotted.sort_values('label')
            st.caption('Labels sorted in ascending order. Use Line for an ordered series, not unrelated categories.')
        spec['mark'] = {'type': 'line', 'point': True, 'color': accent} if kind == 'Line' else {'type': 'bar', 'color': accent, 'cornerRadiusEnd': 0}
        encoding.update(x={'field': 'label', 'type': 'ordinal', 'title': group, 'sort': None}, y={'field': 'value', 'type': 'quantitative', 'title': measure})
    spec['encoding'] = encoding
    st.vega_lite_chart(plotted, spec, width='stretch', theme=None)
