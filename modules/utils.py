"""
共用工具函式模組
"""
import pandas as pd
from typing import List, Dict, Optional


# 預設科目設定
DEFAULT_SUBJECTS = {
    "english": "英文",
    "chinese": "國文",
    "history": "歷史",
    "total": "總級分",
}

# 預設權重
DEFAULT_WEIGHTS = {
    "english": 1.0,
    "chinese": 1.0,
    "history": 1.0,
    "total": 1.0,
}

# 預設招生參數
DEFAULT_QUOTA = 50
DEFAULT_SCREENING_MULTIPLIER = 3.0

# 同分參酌預設順序
DEFAULT_TIEBREAK_ORDER = ["english", "chinese", "history", "total"]


def get_subject_display_name(subject_key: str) -> str:
    """取得科目中文顯示名稱"""
    return DEFAULT_SUBJECTS.get(subject_key, subject_key)


def validate_weights(weights: Dict[str, float]) -> bool:
    """驗證權重是否合理（至少有一科權重 > 0）"""
    return any(w > 0 for w in weights.values())


def validate_quota(quota: int) -> bool:
    """驗證招生名額"""
    return quota > 0


def validate_multiplier(multiplier: float) -> bool:
    """驗證篩選倍數"""
    return multiplier >= 1.0


def validate_dataframe(df: pd.DataFrame, required_cols: Optional[List[str]] = None) -> Dict:
    """
    驗證 DataFrame 結構，回傳驗證結果。

    Returns:
        dict: {"valid": bool, "errors": list[str], "warnings": list[str]}
    """
    result = {"valid": True, "errors": [], "warnings": []}

    if df is None or df.empty:
        result["valid"] = False
        result["errors"].append("資料為空")
        return result

    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            result["valid"] = False
            result["errors"].append(f"缺少必要欄位：{', '.join(missing)}")

    # 檢查數值欄位
    subject_cols = [c for c in DEFAULT_SUBJECTS.keys() if c in df.columns]
    for col in subject_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            result["valid"] = False
            result["errors"].append(f"欄位 '{col}' 應為數值型態")

    return result
