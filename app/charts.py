"""Tres visualizaciones Plotly; la conversión a float ocurre solo para presentar."""

from decimal import Decimal
import math

import plotly.graph_objects as go


GREEN, GOLD, BLUE = "#137568", "#bb852e", "#496b96"


def chart_number(value: Decimal | None) -> float | None:
    """Rechaza extremos no representables en vez de convertirlos en gráficos vacíos."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Un indicador excede el rango de presentación del gráfico.")
    return number


def style_figure(figure: go.Figure, ylabel: str) -> go.Figure:
    """Estilo común y ejes con unidad explícita."""
    figure.update_layout(template="plotly_white", height=370, margin=dict(l=20, r=20, t=20, b=20),
                         font=dict(family="Arial", size=13, color="#243d37"),
                         legend=dict(orientation="h", y=1.13, x=0), hovermode="x unified",
                         xaxis_title="Mes", yaxis_title=ylabel)
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="#e6ece8", zerolinecolor="#aabbb3")
    return figure


def index_chart(rows: list[dict]) -> go.Figure:
    figure = go.Figure()
    for field, name, color in (("usd_index", "Precio internacional · USD/t", BLUE),
                                ("mxn_index", "Referencia · MXN/t", GREEN)):
        figure.add_trace(go.Scatter(x=[row["month"] for row in rows], y=[chart_number(row[field]) for row in rows],
                                    name=name, mode="lines", line=dict(color=color, width=3)))
    return style_figure(figure, "Índice · primer mes visible = 100")


def contribution_chart(rows: list[dict], *, percentage_points: bool = True) -> go.Figure:
    figure = go.Figure()
    suffix = "pp" if percentage_points else "mxn"
    for factor, name, color in (("grain", "Precio internacional", GREEN), ("fx", "Tipo de cambio FIX", GOLD)):
        figure.add_trace(go.Bar(x=[row["month"] for row in rows],
                                y=[chart_number(row[f"{factor}_contribution_{suffix}"]) for row in rows],
                                name=name, marker_color=color))
    figure.update_layout(barmode="relative")
    return style_figure(figure, "Contribución · puntos porcentuales" if percentage_points else "Contribución · MXN/t")


def comparison_chart(summary: list[dict]) -> go.Figure:
    figure = go.Figure(go.Bar(x=[row["name"] for row in summary],
                              y=[chart_number(row["cumulative_pct"]) for row in summary],
                              marker_color=[GREEN, GOLD, BLUE], text=[f"{row['cumulative_pct']:+.1f}%" for row in summary],
                              textposition="outside", cliponaxis=False))
    figure = style_figure(figure, "Variación acumulada · %")
    figure.update_layout(xaxis_title="Grano", height=330)
    return figure
