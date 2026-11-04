"""Interfaz: python -m streamlit run app/streamlit_app.py desde la raíz del proyecto."""

import os
from pathlib import Path

import psycopg
import streamlit as st

from app.analytics import build_analysis, describe_findings
from app.charts import chart_number, comparison_chart, contribution_chart, index_chart
from app.queries import read_dashboard_snapshot
from grain_pipeline.common.config import load_dashboard_database_url


def render_dashboard(snapshot: dict) -> None:
    """Presenta solo meses confirmados por el watermark, con filtros mensuales."""
    publication = snapshot["publication"]
    if publication is None:
        st.info("Todavía no hay un histórico publicado. Ejecuta la carga inicial para consultar el análisis.")
        return
    rows = snapshot["rows"]
    months = sorted({row["month"] for row in rows})
    st.sidebar.header("Explorar el periodo")
    start = st.sidebar.selectbox("Mes inicial", months, format_func=lambda month: month.strftime("%Y-%m"), key="start_month")
    ends = [month for month in months if month >= start]
    end = st.sidebar.selectbox("Mes final", ends, index=len(ends) - 1, format_func=lambda month: month.strftime("%Y-%m"), key="end_month")
    names = {row["series_code"]: row["name"] for row in rows}
    code = st.sidebar.selectbox("Grano", list(names), format_func=names.get, key="grain")
    st.sidebar.button("Actualizar desde PostgreSQL", help="Cada interacción consulta una instantánea nueva de la publicación.")
    st.sidebar.caption(f"Publicado: {publication['start_month']:%Y-%m} → {publication['published_through_month']:%Y-%m}")
    st.sidebar.caption(f"Última confirmación: {publication['updated_at']:%Y-%m-%d %H:%M} UTC")
    analysis = build_analysis(rows, start, end)
    selected = [row for row in analysis["rows"] if row["series_code"] == code]
    latest = selected[-1]
    summary = next(row for row in analysis["summary"] if row["series_code"] == code)
    st.caption(f"PERIODO COMÚN  {start:%Y-%m} — {end:%Y-%m}  ·  {len(selected)} meses  ·  {names[code]}")
    a, b, c = st.columns(3)
    a.metric("Referencia del último mes", f"${latest['reference_mxn_t']:,.2f}", "MXN por tonelada", delta_color="off")
    b.metric("FIX promedio del último mes", f"{latest['average_fix_mxn_usd']:,.4f}", "MXN por USD", delta_color="off")
    c.metric("Cambio en el periodo", f"{summary['cumulative_pct']:+.2f}%", "Referencia nominal MXN/t", delta_color="off")
    st.subheader("1. Precio internacional y referencia en pesos")
    st.caption("Base 100 en el primer mes seleccionado. Permite comparar cambios entre unidades distintas.")
    st.plotly_chart(index_chart(selected), width="stretch", key="indices")
    st.subheader("2. ¿Qué parte del cambio corresponde a cada factor?")
    unit = st.radio("Unidad de contribución", ("Puntos porcentuales", "MXN/t"), horizontal=True)
    if any(row["grain_contribution_mxn"] is not None for row in selected):
        st.plotly_chart(contribution_chart(selected, percentage_points=unit == "Puntos porcentuales"), width="stretch", key="contributions")
    else:
        st.info("No hay un mes anterior publicado para calcular contribuciones en esta selección.")
    st.caption("Cada mes se compara con el mes calendario anterior publicado, aunque esté fuera del filtro. Un valor negativo reduce la referencia; uno positivo la aumenta.")
    st.subheader("3. Comparación entre granos")
    st.plotly_chart(comparison_chart(analysis["summary"]), width="stretch", key="comparison")
    for finding in describe_findings(analysis):
        st.write(finding)
    st.caption("Ahorro cancelado: el precio USD/t baja frente al mes previo y la referencia MXN/t no baja. La frecuencia utiliza solo meses comparables con caída internacional.")
    st.dataframe([{"Grano": row["name"], "Caídas internacionales": row["international_declines"],
                   "Ahorros cancelados": row["cancelled_declines"], "Frecuencia (%)": chart_number(row["cancelled_pct"]),
                   "Meses sin comparación": row["excluded_months"]} for row in analysis["summary"]], hide_index=True, width="stretch")
    with st.expander("Ver datos y cobertura mensual"):
        st.dataframe([{"Mes": row["month"].strftime("%Y-%m"), "Precio USD/t": chart_number(row["grain_price_usd_t"]),
                       "FIX MXN/USD": chart_number(row["average_fix_mxn_usd"]), "Referencia MXN/t": chart_number(row["reference_mxn_t"]),
                       "MoM (%)": chart_number(row["mom_change_pct"]), "YoY (%)": chart_number(row["yoy_change_pct"]),
                       "Días FIX recibidos": row["observed_days"], "Días esperados": row["expected_days"]}
                      for row in selected], hide_index=True, width="stretch")
    with st.expander("Método y alcance"):
        st.write("Referencia mensual = precio internacional USD/t × promedio de los FIX diarios del mes. Solo se muestran meses publicados con cobertura certificada.")
        st.latex(r"\Delta(PF) = (P_t-P_{t-1})\frac{F_t+F_{t-1}}{2} + (F_t-F_{t-1})\frac{P_t+P_{t-1}}{2}")
        st.write("La atribución divide por igual la interacción entre ambos factores. Describe una identidad matemática y no demuestra causalidad económica.")
        st.write("Referencia nominal: excluye fletes, seguros, aranceles, calidad y condiciones comerciales. La frecuencia de ahorro cancelado queda sin valor cuando no hay caídas internacionales comparables.")
    st.caption("Fuentes: FMI vía FRED · FIX de determinación de Banco de México. Datos consultados desde PostgreSQL.")
    st.markdown("[Maíz](https://fred.stlouisfed.org/series/PMAIZMTUSDM) · [Trigo](https://fred.stlouisfed.org/series/PWHEAMTUSDM) · [Soya](https://fred.stlouisfed.org/series/PSOYBUSDM) · [Banxico](https://www.banxico.org.mx/SieAPIRest/service/v1/doc/consultaSeries)")
    st.caption("This product uses the FRED API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.")


def main() -> None:
    st.set_page_config(page_title="Granos y FIX | Referencias en pesos", page_icon="🌾", layout="wide")
    st.title("Granos y FIX: del precio internacional a pesos")
    st.write("Explora cómo cambian las referencias de maíz, trigo y soya al combinar su precio internacional con el tipo de cambio.")
    try:
        env_file = Path(os.environ.get("GRAIN_ENV_FILE", ".env"))
        snapshot = read_dashboard_snapshot(load_dashboard_database_url(env_file))
        render_dashboard(snapshot)
    except (psycopg.Error, RuntimeError):
        st.error("No se pudo consultar la publicación. Revisa la conexión, los permisos y la preparación de PostgreSQL.")
    except ValueError as error:
        st.error(str(error))
    except OSError:
        st.error("No se pudo leer la configuración privada del dashboard.")


if __name__ == "__main__":
    main()
