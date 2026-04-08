"""
第一階段篩選模擬引擎（符合實際甄選入學規則）

真實流程：
  Step 1. 檢定門檻 — 各科設定最低標準（頂標/前標/均標/後標/底標/不設），不符合全部刷掉
  Step 2. 志願估算 — 並非所有符合門檻的考生都會報名，以申請率估算實際報名人數
  Step 3. 超額篩選 — 依篩選順序逐科篩選，各科有獨立倍率
      例：第一關 英文×3 → 第二關 國文×5 → 第三關 總級分×7
      每一關都從上一關通過的人中，依該科排名取 quota×倍率 人
  Step 4. 同分超額處理
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field


# ── 115 學年度各科標準（預設，可被使用者覆寫） ──
GRADE_STANDARDS_115 = {
    "english": {"頂標": 13, "前標": 11, "均標": 8, "後標": 5, "底標": 3},
    "chinese": {"頂標": 13, "前標": 12, "均標": 10, "後標": 9, "底標": 7},
    "history": {"頂標": 13, "前標": 12, "均標": 10, "後標": 8, "底標": 7},
    "total":   {"頂標": 52, "前標": 46, "均標": 36, "後標": 28, "底標": 22},  # 近似值
}

STANDARD_LEVELS = ["不設", "頂標", "前標", "均標", "後標", "底標"]


@dataclass
class ScreeningLevel:
    """單一篩選關卡"""
    subject: str        # 篩選科目（單科如 "english"，或組合如 "english+chinese"）
    multiplier: float   # 篩選倍率

    @property
    def subject_list(self) -> List[str]:
        """將 subject 拆成科目列表"""
        return [s.strip() for s in self.subject.split("+")]

    @property
    def is_combination(self) -> bool:
        return "+" in self.subject


@dataclass
class StrategyConfig:
    """完整策略設定"""
    name: str
    quota: int

    # 檢定門檻：{科目: 標準等級}，例如 {"english": "前標", "chinese": "均標"}
    thresholds: Dict[str, str] = field(default_factory=dict)

    # 上限門檻：排除高分不可能報名的考生，例如 {"english": "頂標"} 排除英文 ≥ 頂標者
    upper_thresholds: Dict[str, str] = field(default_factory=dict)

    # 篩選關卡（依序執行）
    screening_levels: List[ScreeningLevel] = field(default_factory=list)

    # 志願申請率（0~1），例如 0.05 表示 5% 的合格考生會報名
    application_rate: Optional[float] = None

    # 直接指定申請人數（優先於 application_rate）
    application_count: Optional[int] = None

    # 各科標準對照表（用於檢定判斷）
    grade_standards: Dict[str, Dict[str, int]] = field(default_factory=lambda: GRADE_STANDARDS_115.copy())

    # 同分參酌順序
    tiebreak_order: Optional[List[str]] = None

    # === 向後相容：舊版 weighted-sum 模式 ===
    screening_multiplier: float = 3.0
    weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class SimulationResult:
    """模擬結果"""
    strategy_name: str
    quota: int

    # 各階段人數
    total_population: int        # 全體考生
    eligible_count: int          # 通過檢定門檻
    applicant_count: int         # 估計報名人數
    screening_details: List[dict] = field(default_factory=list)  # 各關篩選結果
    final_passed_count: int = 0  # 最終通過人數

    # 資料
    passed_df: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    failed_df: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    all_df: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)

    # 向後相容
    selected_count: int = 0
    actual_selected: int = 0
    cutoff_score: float = 0.0
    screening_multiplier: float = 3.0


# ═══════════════════════════════════════
# Step 1：檢定門檻
# ═══════════════════════════════════════

def apply_thresholds(
    df: pd.DataFrame,
    thresholds: Dict[str, str],
    grade_standards: Dict[str, Dict[str, int]],
    upper_thresholds: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    根據檢定門檻過濾考生。

    thresholds: {"english": "前標"} — 下限，各科須達標
    upper_thresholds: {"english": "頂標"} — 上限，超過此分數視為不會報名本系（排除）
    grade_standards: {"english": {"頂標": 13, "前標": 11, ...}, ...}
    """
    mask = pd.Series(True, index=df.index)

    # 下限檢定
    for subject, level in thresholds.items():
        if level == "不設" or level not in grade_standards.get(subject, {}):
            continue
        min_grade = grade_standards[subject][level]
        if subject in df.columns:
            mask &= df[subject] >= min_grade

    # 上限排除（高分考生不會填本系）
    if upper_thresholds:
        for subject, level in upper_thresholds.items():
            if level == "不設" or level not in grade_standards.get(subject, {}):
                continue
            max_grade = grade_standards[subject][level]
            if subject in df.columns:
                mask &= df[subject] < max_grade

    return df[mask].copy()


# ═══════════════════════════════════════
# Step 2：志願申請率估算
# ═══════════════════════════════════════

def estimate_applicants(
    eligible_df: pd.DataFrame,
    application_rate: Optional[float] = None,
    application_count: Optional[int] = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    從合格考生中，依申請率抽樣模擬實際報名者。

    若不指定，直接使用全部合格考生（保守估計上限）。
    """
    if application_count is not None and application_count < len(eligible_df):
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(eligible_df), size=application_count, replace=False)
        return eligible_df.iloc[idx].copy()

    if application_rate is not None and 0 < application_rate < 1:
        n = max(1, int(len(eligible_df) * application_rate))
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(eligible_df), size=n, replace=False)
        return eligible_df.iloc[idx].copy()

    return eligible_df.copy()


# ═══════════════════════════════════════
# Step 3：超額篩選（逐科逐關）
# ═══════════════════════════════════════

def apply_screening_levels(
    df: pd.DataFrame,
    quota: int,
    screening_levels: List[ScreeningLevel],
    tiebreak_order: Optional[List[str]] = None,
) -> tuple:
    """
    依篩選順序逐關篩選。

    每一關：
    1. 依該科排名
    2. 取前 quota × multiplier 名
    3. 同分全部保留
    4. 將結果傳入下一關

    Returns:
        (passed_df, details_list)
    """
    current = df.copy()
    details = []

    for i, level in enumerate(screening_levels):
        before_count = len(current)
        target_count = int(quota * level.multiplier)

        # 組合科目：加總作為篩選分數
        subj_list = level.subject_list
        missing = [s for s in subj_list if s not in current.columns]
        if missing:
            details.append({
                "關卡": i + 1,
                "科目": level.subject,
                "倍率": level.multiplier,
                "目標人數": target_count,
                "篩選前": before_count,
                "篩選後": before_count,
                "cutoff": "-",
                "備註": f"欄位 {', '.join(missing)} 不存在，跳過",
            })
            continue

        # 計算該關的篩選分數（單科直接用，組合則加總）
        score_col = f"_screen_{i}"
        if level.is_combination:
            current[score_col] = sum(current[s].fillna(0) for s in subj_list)
        else:
            current[score_col] = current[subj_list[0]]

        # 排序
        sort_cols = [score_col]
        ascending = [False]
        if tiebreak_order:
            for col in tiebreak_order:
                if col in current.columns and col != score_col:
                    sort_cols.append(col)
                    ascending.append(False)

        current = current.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

        if target_count >= len(current):
            cutoff = current[score_col].min() if len(current) > 0 else 0
            details.append({
                "關卡": i + 1,
                "科目": level.subject,
                "倍率": level.multiplier,
                "目標人數": target_count,
                "篩選前": before_count,
                "篩選後": len(current),
                "cutoff": cutoff,
                "備註": "人數未超額，全部通過",
            })
            continue

        # 找 cutoff
        cutoff = current.iloc[target_count - 1][score_col]

        # 同分全部保留
        current = current[current[score_col] >= cutoff]

        details.append({
            "關卡": i + 1,
            "科目": level.subject,
            "倍率": level.multiplier,
            "目標人數": target_count,
            "篩選前": before_count,
            "篩選後": len(current),
            "cutoff": int(cutoff),
            "備註": f"同分超額 +{len(current) - target_count}" if len(current) > target_count else "",
        })

        # 清理暫時欄位
        current = current.drop(columns=[score_col])

    return current, details


# ═══════════════════════════════════════
# 主模擬函式
# ═══════════════════════════════════════

def run_simulation(
    df: pd.DataFrame,
    config: StrategyConfig,
) -> SimulationResult:
    """
    執行完整第一階段篩選模擬。
    """
    total_population = len(df)

    # ── 判斷使用新版或舊版邏輯 ──
    use_new_logic = len(config.screening_levels) > 0

    if use_new_logic:
        # === 新版：檢定 → 志願 → 逐科篩選 ===

        # Step 1: 檢定（含上限排除）
        eligible = apply_thresholds(
            df, config.thresholds, config.grade_standards,
            upper_thresholds=getattr(config, "upper_thresholds", {}),
        )
        eligible_count = len(eligible)

        # Step 2: 志願申請率
        applicants = estimate_applicants(
            eligible,
            config.application_rate,
            config.application_count,
        )
        applicant_count = len(applicants)

        # Step 3: 超額篩選
        passed, screening_details = apply_screening_levels(
            applicants,
            config.quota,
            config.screening_levels,
            config.tiebreak_order,
        )

        # 計算 screening_score 供圖表使用
        if config.weights:
            for d in [applicants, passed]:
                score = pd.Series(0.0, index=d.index)
                for subj, w in config.weights.items():
                    if subj in d.columns and w > 0:
                        score += d[subj].fillna(0) * w
                d["screening_score"] = score
        elif config.screening_levels:
            # 用第一關科目分數作為 screening_score
            first_subj = config.screening_levels[0].subject
            if first_subj in applicants.columns:
                applicants["screening_score"] = applicants[first_subj]
            if first_subj in passed.columns:
                passed["screening_score"] = passed[first_subj]

        failed = applicants[~applicants.index.isin(passed.index)]

        # 標記
        all_applicants = applicants.copy()
        all_applicants["passed"] = all_applicants.index.isin(passed.index)

        # cutoff（取最後一關的 cutoff）
        cutoff = screening_details[-1]["cutoff"] if screening_details else 0

        return SimulationResult(
            strategy_name=config.name,
            quota=config.quota,
            total_population=total_population,
            eligible_count=eligible_count,
            applicant_count=applicant_count,
            screening_details=screening_details,
            final_passed_count=len(passed),
            passed_df=passed,
            failed_df=failed,
            all_df=all_applicants,
            selected_count=int(config.quota * config.screening_levels[-1].multiplier) if config.screening_levels else 0,
            actual_selected=len(passed),
            cutoff_score=float(cutoff) if isinstance(cutoff, (int, float)) else 0,
            screening_multiplier=config.screening_levels[-1].multiplier if config.screening_levels else 0,
        )

    else:
        # === 舊版相容：加權分數模式 ===
        work_df = df.copy()
        score = pd.Series(0.0, index=work_df.index)
        for subject, weight in config.weights.items():
            if subject in work_df.columns and weight > 0:
                score += work_df[subject].fillna(0) * weight
        work_df["screening_score"] = score

        sort_cols = ["screening_score"]
        ascending = [False]
        if config.tiebreak_order:
            for col in config.tiebreak_order:
                if col in work_df.columns:
                    sort_cols.append(col)
                    ascending.append(False)

        work_df = work_df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
        selected_count = min(int(config.quota * config.screening_multiplier), len(work_df))

        if selected_count > 0:
            cutoff_score = work_df.iloc[selected_count - 1]["screening_score"]
            actual_passed = work_df[work_df["screening_score"] >= cutoff_score]
            actual_failed = work_df[work_df["screening_score"] < cutoff_score]
        else:
            cutoff_score = 0.0
            actual_passed = pd.DataFrame(columns=work_df.columns)
            actual_failed = work_df.copy()

        work_df["passed"] = work_df["screening_score"] >= cutoff_score

        return SimulationResult(
            strategy_name=config.name,
            quota=config.quota,
            total_population=total_population,
            eligible_count=total_population,
            applicant_count=total_population,
            screening_details=[],
            final_passed_count=len(actual_passed),
            passed_df=actual_passed,
            failed_df=actual_failed,
            all_df=work_df,
            selected_count=selected_count,
            actual_selected=len(actual_passed),
            cutoff_score=cutoff_score,
            screening_multiplier=config.screening_multiplier,
        )


def run_comparison(
    df: pd.DataFrame,
    configs: List[StrategyConfig],
) -> List[SimulationResult]:
    """批次執行多策略模擬"""
    return [run_simulation(df, config) for config in configs]
