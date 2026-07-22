#!/usr/bin/env python3
"""Render the AQI Intelligence architecture diagram with Graphviz."""

from pathlib import Path
import shutil
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture.png"

DOT = r'''
digraph Architecture {
  graph [rankdir=TB, splines=ortho, nodesep=0.42, ranksep=0.5, pad=0.1,
         margin=0.1, size="16,10!", dpi=100, bgcolor="#F8FAFC"];
  node [shape=box, style="rounded,filled", fontname="Arial", fontsize=14,
        margin="0.20,0.13", color="#CBD5E1", penwidth=1.3, fontcolor="#0F172A"];
  edge [color="#64748B", penwidth=1.7, arrowsize=0.8];

  subgraph cluster_sources {
    label="DATA SOURCES"; labelloc="t"; fontsize=16; fontname="Arial Bold";
    color="#BFDBFE"; style="rounded,filled"; fillcolor="#EFF6FF";
    caaqms [label="CAAQMS\nAQI observations", fillcolor="#DBEAFE"];
    weather [label="OpenWeather\nweather signals", fillcolor="#DBEAFE"];
    firms [label="NASA FIRMS\nthermal anomalies", fillcolor="#DBEAFE"];
    osm [label="OSM landuse / traffic\ncontextual signals", fillcolor="#DBEAFE"];
    { rank=same; caaqms; weather; firms; osm; }
  }

  ingestion [label="INGESTION LAYER\nclients • validation • caching", fillcolor="#E0E7FF", color="#A5B4FC"];
  features [label="FEATURE PIPELINE\nmaster_table\njoins • lags • rolling features", fillcolor="#DCFCE7", color="#86EFAC"];

  subgraph cluster_agents {
    label="DECISION AGENTS"; labelloc="t"; fontsize=16; fontname="Arial Bold";
    color="#C4B5FD"; style="rounded,filled"; fillcolor="#F5F3FF";
    forecast [label="Forecasting\nXGBoost / Prophet\n1–72h AQI", fillcolor="#EDE9FE", color="#C4B5FD"];
    attribution [label="Attribution\nNNLS regression\nsource confidence", fillcolor="#EDE9FE", color="#C4B5FD"];
    enforcement [label="Enforcement\npriority scoring\ninspect queue", fillcolor="#EDE9FE", color="#C4B5FD"];
    { rank=same; forecast; attribution; enforcement; }
  }

  api [label="FASTAPI REST LAYER\n/forecast • /attribution • /enforcement • /advisory", fillcolor="#FFEDD5", color="#FDBA74"];
  dashboard [label="REACT DASHBOARD\nmap • forecast • attribution\nenforcement panels", fillcolor="#CCFBF1", color="#5EEAD4"];
  advisory [label="CITIZEN ADVISORY\nmultilingual guidance", fillcolor="#FCE7F3", color="#F9A8D4"];
  anthropic [label="Anthropic API\ngeneration", fillcolor="#FDF2F8", color="#F9A8D4"];

  { rank=same; dashboard; advisory; }

  caaqms -> ingestion; weather -> ingestion; firms -> ingestion; osm -> ingestion;
  ingestion -> features;
  features -> forecast; features -> attribution; features -> enforcement;
  forecast -> api; attribution -> api; enforcement -> api;
  api -> dashboard;
  api -> advisory;
  advisory -> anthropic [color="#DB2777"];
}
'''


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        if image.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Graphviz did not create a PNG")
        image.read(8)
        return struct.unpack(">II", image.read(8))


def main() -> None:
    if shutil.which("dot") is None:
        raise SystemExit("Graphviz is required: install it so the 'dot' command is on PATH.")
    if shutil.which("sips") is None:
        raise SystemExit("macOS 'sips' is required to place the Graphviz diagram on a 1600x1000 canvas.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = OUTPUT.with_name("architecture.render.png")
    subprocess.run(["dot", "-Tpng", "-o", str(rendered)], input=DOT, text=True, check=True)
    subprocess.run(
        ["sips", "--padToHeightWidth", "1000", "1600", "--padColor", "F8FAFC", str(rendered), "--out", str(OUTPUT)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    rendered.unlink(missing_ok=True)
    width, height = png_dimensions(OUTPUT)
    if (width, height) != (1600, 1000):
        raise SystemExit(f"Expected 1600x1000 PNG, got {width}x{height}: {OUTPUT}")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({width}x{height})")


if __name__ == "__main__":
    main()
