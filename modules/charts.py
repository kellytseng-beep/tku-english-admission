"""
圖表繪製模組（使用 Plotly）
"""
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import List
from modules.simulator import SimulationResult
from modules.utils import DEFAULT_SUBJECTS


def plot_pass_fail_bar(result: SimulationResult) -> go.Figure:
    """通過/未通過人數長條圖"""
    data = pd.DataFrame({
        "狀態": ["通過", "未通過"],
        "人數": [result.actual_selected, len(result.failed_df)],
    })
    fig = px.bar(
        data, x="狀態", y="人數",
        color="狀態",
        color_discrete_map={"通過": "#2196F3", "未通過": "#BDBDBD"},
        title=f"第一階段篩選結果 — {result.strategy_name}",
    )
    fig.update_layout(showlegend=False)
    return fig


def plot_score_distribution(result: SimulationResult, bins: int = 25) -> go.Figure:
    """通過者與未通過者的分數分布直方圖"""
    all_df = result.all_df.copy()
    all_df["狀態"] = all_df["passed"].map({True: "通過", False: "未通過"})

    fig = px.histogram(
        all_df, x="screening_score", color="狀態",
        nbins=bins,
        barmode="overlay",
        color_discrete_map={"通過": "#2196F3", "未通過": "#BDBDBD"},
        labels={"screening_score": "加權篩選分數"},
        title=f"分數分布 — {result.strategy_name}",
        opacity=0.7,
    )
    # 加 cutoff 線
    fig.add_vline(
        x=result.cutoff_score,
        line_dash="dash", line_color="red",
        annotation_text=f"Cutoff: {result.cutoff_score:.1f}",
    )
    return fig


def plot_cutoff_comparison(results: List[SimulationResult]) -> go.Figure:
    """多策略 cutoff 比較圖"""
    data = pd.DataFrame({
        "策略": [r.strategy_name for r in results],
        "Cutoff 分數": [r.cutoff_score for r in results],
    })
    fig = px.bar(
        data, x="策略", y="Cutoff 分數",
        color="策略",
        title="Cutoff 分數比較",
    )
    fig.update_layout(showlegend=False)
    return fig


def plot_selected_count_comparison(results: List[SimulationResult]) -> go.Figure:
    """多策略通過人數比較圖"""
    data = pd.DataFrame({
        "策略": [r.strategy_name for r in results],
        "預計通過": [r.selected_count for r in results],
        "實際通過（含同分）": [r.actual_selected for r in results],
    })
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=data["策略"], y=data["預計通過"],
        name="預計通過", marker_color="#90CAF9",
    ))
    fig.add_trace(go.Bar(
        x=data["策略"], y=data["實際通過（含同分）"],
        name="實際通過（含同分）", marker_color="#1565C0",
    ))
    fig.update_layout(
        title="通過人數比較",
        barmode="group",
    )
    return fig


def plot_subject_avg_comparison(results: List[SimulationResult]) -> go.Figure:
    """多策略通過者各科平均比較圖"""
    rows = []
    for r in results:
        passed = r.passed_df
        for subj_key, subj_name in DEFAULT_SUBJECTS.items():
            if subj_key in passed.columns and len(passed) > 0:
                rows.append({
                    "策略": r.strategy_name,
                    "科目": subj_name,
                    "平均分數": round(passed[subj_key].mean(), 2),
                })

    if not rows:
        fig = go.Figure()
        fig.update_layout(title="無資料")
        return fig

    data = pd.DataFrame(rows)
    fig = px.bar(
        data, x="科目", y="平均分數", color="策略",
        barmode="group",
        title="通過者各科平均分數比較",
    )
    return fig


def plot_multiplier_sensitivity(
    results_by_multiplier: dict,
) -> go.Figure:
    """篩選倍數敏感度分析圖"""
    data = pd.DataFrame({
        "篩選倍數": list(results_by_multiplier.keys()),
        "通過人數": [r.actual_selected for r in results_by_multiplier.values()],
        "Cutoff": [r.cutoff_score for r in results_by_multiplier.values()],
    })

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=data["篩選倍數"], y=data["通過人數"],
            mode="lines+markers", name="通過人數",
            line=dict(color="#2196F3"),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=data["篩選倍數"], y=data["Cutoff"],
            mode="lines+markers", name="Cutoff 分數",
            line=dict(color="#FF5722"),
        ),
        secondary_y=True,
    )
    fig.update_layout(title="篩選倍數敏感度分析")
    fig.update_xaxes(title_text="篩選倍數")
    fig.update_yaxes(title_text="通過人數", secondary_y=False)
    fig.update_yaxes(title_text="Cutoff 分數", secondary_y=True)
    return fig
