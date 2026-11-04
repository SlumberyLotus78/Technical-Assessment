"""Exporta resultados publicos del producto real mediante consultas de solo lectura."""

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg

from app.analytics import build_analysis
from app.charts import comparison_chart, contribution_chart, index_chart
from app.queries import read_dashboard_snapshot
from grain_pipeline.common.config import load_dashboard_database_url
from grain_pipeline.common.dates import parse_month, shift_month
from grain_pipeline.extraction.raw import write_json


def serialize_value(value):
    """Conserva los decimales como texto en la evidencia JSON."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("Tipo incompatible con la evidencia analitica.")


def export_analysis(env_file: Path, start: date, output_directory: Path) -> dict:
    snapshot = read_dashboard_snapshot(load_dashboard_database_url(env_file))
    if snapshot["publication"] is None:
        raise ValueError("Se necesita un historico publicado para exportar el analisis.")
    publication = snapshot["publication"]
    end = publication["published_through_month"]
    if start < publication["start_month"] or start > end:
        raise ValueError("El inicio analitico debe quedar dentro de la publicacion.")
    analysis = build_analysis(snapshot["rows"], start, end)
    corn = [row for row in analysis["rows"] if row["series_code"] == "PMAIZMTUSDM"]
    recent_start = max(start, shift_month(end, -32))
    fields = ("month", "usd_index", "mxn_index", "grain_contribution_pp", "fx_contribution_pp",
              "grain_contribution_mxn", "fx_contribution_mxn")
    document = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "dataset": "real_project_publication_read_only", "database_written": False, "new_api_requests": False,
                "published_start_month": publication["start_month"], "published_through_month": end,
                "last_run_id": str(publication["last_run_id"]), "publication_updated_at": publication["updated_at"],
                "analysis_start_month": start, "analysis_end_month": end, "analysis_months": len(corn),
                "summary": analysis["summary"], "grain_for_time_charts": "PMAIZMTUSDM",
                "index_rows": [{field: row[field] for field in fields} for row in corn],
                "contribution_start_month": recent_start,
                "contribution_rows": [{field: row[field] for field in fields} for row in corn if row["month"] >= recent_start],
                "units": {"index": "first visible month = 100", "contribution": "percentage points", "reference": "MXN/t"},
                "scope": "Nominal reference. Symmetric arithmetic attribution, without causal inference."}
    document = json.loads(json.dumps(document, default=serialize_value, allow_nan=False))
    output_directory.mkdir(parents=True, exist_ok=True)
    write_json(output_directory / "analisis_real.json", document)
    return document


def chart_figures(document: dict) -> list:
    """Reutiliza exactamente los constructores del dashboard y traduce las etiquetas de entrega."""
    def typed(rows):
        return [{key: date.fromisoformat(value) if key == "month" else Decimal(value) if value is not None else None
                 for key, value in row.items()} for row in rows]
    indexed = index_chart(typed(document["index_rows"]))
    indexed.data[0].name, indexed.data[1].name = "International price (USD/t)", "Reference (MXN/t)"
    indexed.update_layout(xaxis_title="Month", yaxis_title="Index: first visible month = 100")
    contributions = contribution_chart(typed(document["contribution_rows"]))
    contributions.data[0].name, contributions.data[1].name = "International price", "FIX exchange rate"
    contributions.update_layout(xaxis_title="Month", yaxis_title="Monthly contribution (percentage points)")
    names = {"PMAIZMTUSDM": "Corn", "PWHEAMTUSDM": "Wheat", "PSOYBUSDM": "Soybeans"}
    summary = [dict(row, name=names[row["series_code"]], cumulative_pct=Decimal(row["cumulative_pct"])) for row in document["summary"]]
    comparison = comparison_chart(summary)
    comparison.update_layout(xaxis_title="Grain", yaxis_title="Cumulative MXN reference change (%)")
    return [indexed, contributions, comparison]


def render_local_html(edge: Path, html_file: Path, output_png: Path, *, profile: Path,
                       fragment: str = "", width: int = 1400, height: int = 780) -> None:
    """Renderiza un artefacto local en un perfil headless separado, sin tocar el navegador del usuario."""
    profile = profile.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    command = [str(edge), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--disable-background-networking", "--hide-scrollbars", f"--user-data-dir={profile}",
               f"--window-size={width},{height}", "--force-device-scale-factor=1", "--virtual-time-budget=4000",
               f"--screenshot={output_png.resolve()}", html_file.resolve().as_uri() + fragment]
    with (profile.parent / "edge_render.log").open("a", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=60,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
    if result.returncode != 0 or not output_png.is_file():
        raise RuntimeError("No se pudo renderizar el artefacto local.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exporta analisis publicado y tres graficos sin modificar la base.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--start-month", type=parse_month, default=date(2010, 1, 1))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidencias/entrega_final"))
    parser.add_argument("--figures-dir", type=Path, default=Path("docs/figures"))
    parser.add_argument("--edge", type=Path, default=Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))
    args = parser.parse_args(argv)
    try:
        document = export_analysis(args.env_file, args.start_month, args.output_dir)
        scratch = Path("data/verification") / ("charts_" + uuid4().hex)
        scratch.mkdir(parents=True)
        args.figures_dir.mkdir(parents=True, exist_ok=True)
        for index, figure in enumerate(chart_figures(document), 1):
            html_file = scratch / f"chart_{index}.html"
            figure.update_layout(width=1360, height=700)
            figure.write_html(html_file, include_plotlyjs=True, full_html=True, auto_open=False)
            render_local_html(args.edge, html_file, args.figures_dir / f"chart_{index}.png", profile=scratch / "browser_profile")
    except (ValueError, RuntimeError, OSError, psycopg.Error):
        print("No se pudo exportar el analisis publicado; revisar conexion, periodo y renderizador local.", file=sys.stderr)
        return 1
    print(f"Analisis real exportado: {document['analysis_months']} meses y tres graficos, sin escrituras SQL ni consultas nuevas a APIs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
