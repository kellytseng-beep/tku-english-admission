"""
統計指標計算模組
"""
import pandas as pd
from typing import List, Dict
from modules.simulator import SimulationResult
from modules.utils import DEFAULT_SUBJECTS


def compute_result_metrics(result: SimulationResult) -> Dict:
    """計算單一模擬結果的統計指標"""
    passed = result.passed_df
    metrics = {
        "策略名稱": result.strategy_name,
        "招生名額": result.quota,
        "全體考生": result.total_population,
        "通過檢定": result.eligible_count,
        "估計報名": result.applicant_count,
        "最終通過": result.final_passed_count,
    }

    # 各關篩選結果
    for d in result.screening_details:
        label = f"第{d['關卡']}關 {d['科目']}×{d['倍率']}"
        metrics[f"{label} cutoff"] = d["cutoff"]
        metrics[f"{label} 通過"] = d["篩選後"]

    # 通過者各科平均
    for subj_key, subj_name in DEFAULT_SUBJECTS.items():
        if subj_key in passed.columns and len(passed) > 0:
            metrics[f"通過者{subj_name}平均"] = round(passed[subj_key].mean(), 2)

    return metrics


def build_comparison_table(results: List[SimulationResult]) -> pd.DataFrame:
    """建立多策略比較表（轉置：指標為列，策略為欄）"""
    rows = [compute_result_metrics(r) for r in results]
    df = pd.DataFrame(rows)
    # 轉置：策略名稱當欄位
    df = df.set_index("策略名稱").T.reset_index()
    df = df.rename(columns={"index": "指標"})
    return df


def compute_score_distribution(
    df: pd.DataFrame,
    score_col: str = "screening_score",
    bins: int = 20,
) -> pd.DataFrame:
    """計算分數分布"""
    if score_col not in df.columns or len(df) == 0:
        return pd.DataFrame(columns=["分數區間", "人數"])

    cut = pd.cut(df[score_col], bins=bins)
    dist = cut.value_counts().sort_index().reset_index()
    dist.columns = ["分數區間", "人數"]
    dist["分數區間"] = dist["分數區間"].astype(str)
    return dist
