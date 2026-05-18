"""
資料載入與格式轉換模組

支援兩種 CSV 格式：
- 模式 A：個別考生資料（每列一位考生）
- 模式 B：分布統計資料（每列一種分數組合 + 人數）
"""
import pandas as pd
import numpy as np
from typing import Tuple
from modules.utils import DEFAULT_SUBJECTS


def detect_data_mode(df: pd.DataFrame) -> str:
    """
    自動判斷資料格式。

    若含有 'count' 欄位，判定為模式 B（分布統計）；否則為模式 A（個別考生）。
    """
    if "count" in df.columns:
        return "B"
    return "A"


def load_csv(file) -> pd.DataFrame:
    """讀取上傳的 CSV 檔"""
    try:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        raise ValueError(f"CSV 讀取失敗：{e}")


def normalize_to_applicants(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """
    將不同格式的資料統一轉換為個別考生格式。

    模式 A：直接使用
    模式 B：根據 count 欄展開為個別考生列
    """
    subject_cols = [c for c in DEFAULT_SUBJECTS.keys() if c in df.columns]

    if mode == "B":
        if "count" not in df.columns:
            raise ValueError("模式 B 需要 'count' 欄位")

        rows = []
        applicant_id = 1
        for _, row in df.iterrows():
            count = int(row["count"])
            for _ in range(count):
                record = {"applicant_id": applicant_id}
                for col in subject_cols:
                    record[col] = row[col]
                rows.append(record)
                applicant_id += 1
        result = pd.DataFrame(rows)
    else:
        result = df.copy()
        if "applicant_id" not in result.columns:
            result["applicant_id"] = range(1, len(result) + 1)

    # 確保數值型態
    for col in subject_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


def get_data_summary(df: pd.DataFrame) -> dict:
    """取得資料摘要統計"""
    subject_cols = [c for c in DEFAULT_SUBJECTS.keys() if c in df.columns]
    summary = {
        "total_applicants": len(df),
        "subjects": {},
    }
    for col in subject_cols:
        if col in df.columns:
            summary["subjects"][col] = {
                "mean": round(df[col].mean(), 2),
                "median": round(df[col].median(), 2),
                "std": round(df[col].std(), 2),
                "min": df[col].min(),
                "max": df[col].max(),
            }
    return summary


def generate_sample_applicants(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """生成範例考生資料（供測試用）"""
    rng = np.random.default_rng(seed)

    english = rng.integers(5, 16, size=n)
    chinese = rng.integers(5, 16, size=n)
    social = rng.integers(5, 16, size=n)
    # 總級分 = 各科加總再加上其他未列出科目的隨機分數
    others = rng.integers(10, 31, size=n)
    total = english + chinese + social + others

    df = pd.DataFrame({
        "applicant_id": range(1, n + 1),
        "english": english,
        "chinese": chinese,
        "social": social,
        "total": total,
    })
    return df
