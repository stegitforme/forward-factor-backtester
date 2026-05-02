"""
Interactive HTML dashboard for the Forward Factor backtest.

Renders all the comparison plots and tables into a single self-contained
HTML file using Plotly. The dashboard answers the question:

  "Should I allocate to Forward Factor at the proposed sizing?"

Sections:
  1. Headline summary table (CAGR, Sharpe, Max DD per strategy)
  2. Equity curves overlay (FF cells + ensemble + benchmarks)
  3. Cross-cell correlation matrix
  4. Drawdown overlay
  5. Regime-segmented returns
  6. Per-cell trade stats

The output is written to OUTPUT_DIR/DASHBOARD_FILENAME (default
output/comparison_dashboard.html). Open in any browser — no server needed.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from src.metrics import (
    REGIMES,
    compare_strategies,
    compute_metrics,
    compute_regime_metrics,
    compute_returns,
    correlation_matrix,
)


log = logging.getLogger(__name__)


def _format_metric(value, fmt="pct"):
    """Format a metric for display."""
    if value is None or pd.isna(value):
        return "—"
    if fmt == "pct":
        return f"{value * 100:+.2f}%"
    if fmt == "ratio":
        return f"{value:.2f}"
    if fmt == "int":
        return f"{int(value):,}"
    return str(value)


def _build_summary_html(comparison_df: pd.DataFrame) -> str:
    """Build the headline summary table."""
    rows = []
    for strategy_name, row in comparison_df.iterrows():
        rows.append(f"""
            <tr>
                <td><strong>{strategy_name}</strong></td>
                <td>{_format_metric(row.get('cagr'), 'pct')}</td>
                <td>{_format_metric(row.get('total_return'), 'pct')}</td>
                <td>{_format_metric(row.get('volatility'), 'pct')}</td>
                <td>{_format_metric(row.get('sharpe'), 'ratio')}</td>
                <td>{_format_metric(row.get('sortino'), 'ratio')}</td>
                <td>{_format_metric(row.get('max_drawdown'), 'pct')}</td>
                <td>{_format_metric(row.get('calmar'), 'ratio')}</td>
                <td>{_format_metric(row.get('n_trades'), 'int')}</td>
                <td>{_format_metric(row.get('win_rate'), 'pct')}</td>
            </tr>
        """)
    rows_html = "\n".join(rows)

    return f"""
    <table class="summary">
        <thead>
            <tr>
                <th>Strategy</th>
                <th>CAGR</th>
                <th>Total Return</th>
                <th>Volatility</th>
                <th>Sharpe</th>
                <th>Sortino</th>
                <th>Max DD</th>
                <th>Calmar</th>
                <th>Trades</th>
                <th>Win Rate</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """


def _build_decision_panel(ensemble_metrics, cell_metrics: dict, criteria: dict = None) -> str:
    """
    Build the capital allocation decision panel based on our criteria.
    Returns HTML showing pass/fail for each criterion.
    """
    if criteria is None:
        criteria = {
            "ensemble_cagr_min": 0.15,
            "worst_cell_sharpe_min": 1.0,
            "win_rate_min": 0.50,
            "win_rate_max": 0.70,
            "max_dd_max": 0.25,
        }

    # Compute checks
    ensemble_cagr = ensemble_metrics.cagr if ensemble_metrics else 0.0
    worst_sharpe = min(
        (m.sharpe for m in cell_metrics.values()),
        default=0.0
    ) if cell_metrics else 0.0
    ensemble_dd = abs(ensemble_metrics.max_drawdown) if ensemble_metrics else 0.0
    ensemble_winrate = ensemble_metrics.win_rate if ensemble_metrics else 0.0

    checks = [
        {
            "name": "Ensemble CAGR ≥ 15%",
            "actual": _format_metric(ensemble_cagr, "pct"),
            "passed": ensemble_cagr >= criteria["ensemble_cagr_min"],
        },
        {
            "name": "Worst single cell Sharpe ≥ 1.0",
            "actual": _format_metric(worst_sharpe, "ratio"),
            "passed": worst_sharpe >= criteria["worst_cell_sharpe_min"],
        },
        {
            "name": "Win rate 50-70%",
            "actual": _format_metric(ensemble_winrate, "pct"),
            "passed": criteria["win_rate_min"] <= ensemble_winrate <= criteria["win_rate_max"],
        },
        {
            "name": "Max DD ≤ 25%",
            "actual": _format_metric(-ensemble_dd, "pct"),
            "passed": ensemble_dd <= criteria["max_dd_max"],
        },
    ]

    rows_html = ""
    all_passed = all(c["passed"] for c in checks)
    for c in checks:
        icon = "✅" if c["passed"] else "❌"
        rows_html += f"""
            <tr>
                <td>{icon}</td>
                <td>{c['name']}</td>
                <td>{c['actual']}</td>
            </tr>
        """

    verdict = "ALLOCATE — 10-15% of liquid net worth at quarter Kelly" if all_passed \
        else "DO NOT ALLOCATE — strategy fails decision criteria"
    verdict_class = "pass" if all_passed else "fail"

    return f"""
    <div class="decision-panel">
        <h2>Capital Allocation Decision</h2>
        <table class="decision-table">
            <thead><tr><th></th><th>Criterion</th><th>Actual</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <div class="verdict {verdict_class}">{verdict}</div>
    </div>
    """


def _build_equity_curves_div(strategy_curves: dict[str, pd.Series]) -> str:
    """Plotly equity curve overlay."""
    import json
    traces = []
    for name, curve in strategy_curves.items():
        if len(curve) == 0:
            continue
        traces.append({
            "x": [t.isoformat() if hasattr(t, "isoformat") else str(t) for t in curve.index],
            "y": [float(v) for v in curve.values],
            "type": "scatter",
            "mode": "lines",
            "name": name,
        })
    fig = {
        "data": traces,
        "layout": {
            "title": "Equity Curves",
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "Equity ($)", "tickformat": ",.0f"},
            "hovermode": "x unified",
            "height": 500,
        },
    }
    return f'<div id="equity-curves"></div><script>Plotly.newPlot("equity-curves", {json.dumps(fig["data"])}, {json.dumps(fig["layout"])});</script>'


def _build_correlation_div(corr_df: pd.DataFrame) -> str:
    """Plotly heatmap of cross-cell correlations."""
    import json
    if corr_df.empty:
        return "<p>No correlation data.</p>"
    fig = {
        "data": [{
            "z": corr_df.values.tolist(),
            "x": list(corr_df.columns),
            "y": list(corr_df.index),
            "type": "heatmap",
            "colorscale": "RdBu",
            "zmin": -1, "zmax": 1,
            "text": [[f"{v:.2f}" for v in row] for row in corr_df.values.tolist()],
            "texttemplate": "%{text}",
        }],
        "layout": {
            "title": "Cross-Strategy Correlation Matrix",
            "height": 400,
            "width": 600,
        },
    }
    return f'<div id="correlation"></div><script>Plotly.newPlot("correlation", {json.dumps(fig["data"])}, {json.dumps(fig["layout"])});</script>'


def _build_regime_table(regime_metrics: dict[str, dict]) -> str:
    """Build a table of regime-segmented returns."""
    if not regime_metrics:
        return "<p>No regime data available.</p>"

    # Get all strategies and regimes
    all_strategies = set()
    for regime, strat_metrics in regime_metrics.items():
        all_strategies.update(strat_metrics.keys())
    all_strategies = sorted(all_strategies)
    all_regimes = sorted(regime_metrics.keys())

    header = "<tr><th>Regime</th>" + "".join(f"<th>{s}</th>" for s in all_strategies) + "</tr>"
    rows = ""
    for regime in all_regimes:
        cells = ""
        for strat in all_strategies:
            metrics = regime_metrics[regime].get(strat)
            if metrics:
                cells += f"<td>{_format_metric(metrics.cagr, 'pct')}</td>"
            else:
                cells += "<td>—</td>"
        rows += f"<tr><td><strong>{regime}</strong></td>{cells}</tr>"

    return f"""
    <table class="summary">
        <thead>{header}</thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_dashboard(
    strategy_curves: dict[str, pd.Series],
    cell_metrics: dict,
    ensemble_metrics,
    correlation: pd.DataFrame,
    trade_logs: Optional[dict[str, pd.DataFrame]] = None,
    regime_metrics: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Render the full dashboard to HTML and write to disk.

    Returns the file path written.
    """
    if output_path is None:
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(settings.OUTPUT_DIR, settings.DASHBOARD_FILENAME)

    comparison_df = compare_strategies(strategy_curves, trade_logs)
    summary_html = _build_summary_html(comparison_df)
    equity_html = _build_equity_curves_div(strategy_curves)
    correlation_html = _build_correlation_div(correlation)
    decision_html = _build_decision_panel(ensemble_metrics, cell_metrics)
    regime_html = _build_regime_table(regime_metrics) if regime_metrics else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Forward Factor Backtest — Comparison Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 24px; color: #1f2937; background: #f9fafb; }}
  h1 {{ font-size: 28px; margin-bottom: 8px; }}
  h2 {{ font-size: 22px; margin-top: 36px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
  .meta {{ color: #6b7280; font-size: 14px; margin-bottom: 24px; }}
  table.summary, table.decision-table {{ width: 100%; border-collapse: collapse; margin: 16px 0;
                    background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  table.summary th, table.summary td, table.decision-table th, table.decision-table td {{
    padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 14px;
  }}
  table.summary thead, table.decision-table thead {{ background: #f3f4f6; font-weight: 600; }}
  .decision-panel {{ background: white; padding: 24px; border-radius: 8px;
                     margin: 24px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .verdict {{ margin-top: 16px; padding: 16px; border-radius: 6px; font-weight: 600;
              font-size: 16px; text-align: center; }}
  .verdict.pass {{ background: #d1fae5; color: #065f46; }}
  .verdict.fail {{ background: #fee2e2; color: #991b1b; }}
  #equity-curves, #correlation {{ background: white; padding: 16px;
                                  border-radius: 8px; margin: 16px 0;
                                  box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
</style>
</head>
<body>

<h1>Forward Factor Backtest — Comparison Dashboard</h1>
<div class="meta">Generated {date.today().isoformat()} | Window: {settings.BACKTEST_START_DATE} to {settings.BACKTEST_END_DATE} | Initial capital: ${settings.INITIAL_CAPITAL:,.0f}</div>

{decision_html}

<h2>Strategy Comparison</h2>
{summary_html}

<h2>Equity Curves</h2>
{equity_html}

<h2>Cross-Strategy Correlations</h2>
{correlation_html}

{f'<h2>Regime-Segmented Returns (CAGR)</h2>{regime_html}' if regime_html else ''}

<h2>Methodology</h2>
<ul>
  <li><strong>Forward Factor (FF)</strong>: (front IV − forward IV) / forward IV. Threshold: ≥ {settings.FF_THRESHOLD}.</li>
  <li><strong>Universe</strong>: Top {settings.UNIVERSE_MAX_TICKERS} most liquid optionable names by 20-day avg option volume (>{settings.UNIVERSE_MIN_DAILY_OPTION_VOLUME:,}).</li>
  <li><strong>Sizing</strong>: {settings.RISK_PER_TRADE * 100:.0f}% per-trade × {settings.KELLY_FRACTION:.2f} Kelly = {settings.RISK_PER_TRADE * settings.KELLY_FRACTION * 100:.1f}% effective. Max {settings.MAX_CONCURRENT_POSITIONS} concurrent.</li>
  <li><strong>Execution</strong>: {settings.SLIPPAGE_PCT * 100:.0f}% slippage on debit, ${settings.COMMISSION_PER_CONTRACT:.2f}/contract commission, exit T-{settings.EXIT_DAYS_BEFORE_FRONT_EXPIRY} day(s) before front expiry.</li>
  <li><strong>Earnings filter</strong>: Skip any trade with earnings between entry and back expiry (+{settings.EARNINGS_BUFFER_DAYS} day buffer).</li>
</ul>

</body>
</html>
"""
    with open(output_path, "w") as f:
        f.write(html)
    log.info("Dashboard written to %s", output_path)
    return output_path
