"""
116學年度學測分布預測腳本
==============================
1. 解析 111~115 年各科級分分布
2. 分析趨勢（報考人數、各級分佔比）
3. 以線性外推預測 116 年分布
4. 輸出 116 預測聯合分布 CSV（可上傳至 app）
5. 輸出趨勢分析圖表

欄位對應（111-113年 data 工作表）：
  P1=國文, P2=英文, P4=自然, P5=社會, P8=數學A, P9=數學B

已知歷年英文報考人數（近似值，用於百分比→人數轉換）：
  111年 ≈ 119,000 / 112年 ≈ 120,500 / 113年 ≈ 120,000
  114年 = 117,866 (實際值) / 115年 = 118,162 (實際值)
"""

import itertools
import warnings
import xlrd
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ── 設定 ──
SUBJECTS = {"english": "英文", "chinese": "國文", "social": "社會"}

# 已知各年英文報考總人數
TOTAL_APPLICANTS = {
    111: 119_000,
    112: 120_500,
    113: 120_000,
    114: 117_866,
    115: 118_162,
}

# 111-113 年 data 工作表欄位對應
PCOL = {
    "chinese": "P1",
    "english": "P2",
    "social":  "P5",
}

OUTPUT_DIR = Path("sample_data")


# ═══════════════════════════════════════
# 解析函式
# ═══════════════════════════════════════

def parse_111_to_113(year: int) -> dict:
    """
    解析 111-113 年格式（data 工作表，百分比）。
    回傳 {subject: pd.DataFrame(grade, count)}
    """
    wb = xlrd.open_workbook(f"sample_data/ceec_{year}/各科級分分布.xls")
    ws = wb.sheet_by_name("data")

    # 第一列是欄位名稱
    headers = [ws.cell_value(0, c) for c in range(ws.ncols)]

    data = {}
    for r in range(1, ws.nrows):
        grade = ws.cell_value(r, 0)
        row = {headers[c]: ws.cell_value(r, c) for c in range(ws.ncols)}
        data[int(grade)] = row

    total = TOTAL_APPLICANTS[year]
    result = {}
    for subj, pcol in PCOL.items():
        rows = []
        for grade in range(1, 16):
            pct = data.get(grade, {}).get(pcol, 0)
            count = round(pct / 100 * total)
            rows.append({"grade": grade, "count": count})
        result[subj] = pd.DataFrame(rows)

    return result


def parse_114(year: int = 114) -> dict:
    """解析 114 年格式（與 115 相同的累計表格式）"""
    wb = xlrd.open_workbook(f"sample_data/ceec_{year}/各科級分分布.xls")
    ws = wb.sheet_by_index(0)

    def extract(start_row, end_row, col):
        rows = []
        for r in range(start_row, end_row):
            grade = ws.cell_value(r, 0)
            count = ws.cell_value(r, col)
            if grade and str(grade).strip():
                try:
                    g = int(float(str(grade).strip()))
                    c = int(float(count)) if count else 0
                    if 1 <= g <= 15:
                        rows.append({"grade": g, "count": c})
                except:
                    pass
        return pd.DataFrame(rows)

    # 114年 工作表結構同 115（62列，國文欄1，英文欄7，社會欄46-60）
    return {
        "chinese": extract(4, 20, 1),
        "english": extract(4, 20, 7),
        "social":  extract(46, 62, 1),
    }


def parse_115() -> dict:
    """解析 115 年（已在前一步驟完成，直接讀取）"""
    files = {
        "chinese": "sample_data/ceec_115/chinese_dist.csv",
        "english": "sample_data/ceec_115/english_dist.csv",
        "social":  "sample_data/ceec_115/social_dist.csv",
    }
    result = {}
    for subj, fp in files.items():
        df = pd.read_csv(fp)
        df.columns = ["grade", "count"]
        result[subj] = df
    return result


def parse_standards(year: int) -> dict:
    """解析各科成績標準（頂標/前標/均標/後標/底標）"""
    wb = xlrd.open_workbook(f"sample_data/ceec_{year}/各科成績標準.xls")
    ws = wb.sheet_by_index(0)

    standards = {}
    std_names = ["頂標", "前標", "均標", "後標", "底標"]
    std_idx = 0

    for r in range(ws.nrows):
        v0 = str(ws.cell_value(r, 0)).strip()
        v1 = str(ws.cell_value(r, 1)).strip()

        # 找到當年的資料行（有年份數字的行）
        try:
            y = int(float(v0))
            if y == year:
                std_idx = 0
        except:
            pass

        # 解析 頂標/前標/均標/後標/底標
        if v1 in std_names and std_idx < len(std_names):
            try:
                chinese_grade = float(ws.cell_value(r, 2))
                english_grade = float(ws.cell_value(r, 4))
                social_grade_raw = ws.cell_value(r, 6)
                social_grade = float(social_grade_raw) if str(social_grade_raw).strip() not in ["--", ""] else None

                label = std_names[std_idx]
                standards[label] = {
                    "chinese": chinese_grade,
                    "english": english_grade,
                    "social":  social_grade,
                }
                std_idx += 1
            except:
                pass

    return standards


# ═══════════════════════════════════════
# 趨勢分析
# ═══════════════════════════════════════

def compute_weighted_mean(df: pd.DataFrame) -> float:
    """計算加權平均級分"""
    total = df["count"].sum()
    if total == 0:
        return 0
    return (df["grade"] * df["count"]).sum() / total


def compute_percentile_grade(df: pd.DataFrame, pct: float) -> float:
    """計算第 pct 百分位數對應的級分（0~100）"""
    sorted_df = df.sort_values("grade")
    cumsum = sorted_df["count"].cumsum()
    total = sorted_df["count"].sum()
    threshold = pct / 100 * total
    for i, row in sorted_df.iterrows():
        if cumsum[i] >= threshold:
            return row["grade"]
    return sorted_df["grade"].max()


def build_trend_table(all_data: dict) -> pd.DataFrame:
    """建立各年趨勢表"""
    rows = []
    years = sorted(all_data.keys())

    for year in years:
        row = {"year": year}
        for subj in ["english", "chinese", "social"]:
            df = all_data[year].get(subj)
            if df is not None and len(df) > 0:
                row[f"{subj}_total"] = df["count"].sum()
                row[f"{subj}_mean"] = round(compute_weighted_mean(df), 3)
                row[f"{subj}_p50"]  = compute_percentile_grade(df, 50)
                row[f"{subj}_p75"]  = compute_percentile_grade(df, 75)
                row[f"{subj}_p88"]  = compute_percentile_grade(df, 88)
        rows.append(row)

    return pd.DataFrame(rows)


def project_116(trend_df: pd.DataFrame, all_data: dict) -> dict:
    """
    以線性迴歸外推 116 年各科各級分的預測人數。
    策略：
      1. 對每個科目的每個級分，用 111-115 年人數做線性迴歸
      2. 外推至 116 年
      3. 確保總人數與預測報考人數一致（依人口下降趨勢估算）
    """
    years = np.array(sorted(all_data.keys()))

    # 預測 116 年報考人數（基於 111-115 趨勢）
    english_totals = np.array([
        all_data[y]["english"]["count"].sum() for y in years
    ])
    # 線性外推
    coef = np.polyfit(years, english_totals, 1)
    predicted_total_116 = max(int(np.polyval(coef, 116)), 80_000)
    print(f"\n預測 116年 英文報考人數：{predicted_total_116:,} 人")
    print(f"  （基礎：{dict(zip(years.tolist(), english_totals.tolist()))}）")

    result = {}
    for subj in ["english", "chinese", "social"]:
        rows = []
        for grade in range(1, 16):
            counts_by_year = []
            for y in years:
                df = all_data[y].get(subj)
                if df is not None:
                    match = df[df["grade"] == grade]["count"]
                    counts_by_year.append(match.values[0] if len(match) > 0 else 0)
                else:
                    counts_by_year.append(0)

            c = np.array(counts_by_year, dtype=float)
            coef_g = np.polyfit(years, c, 1)
            pred = max(0, int(np.polyval(coef_g, 116)))
            rows.append({"grade": grade, "count": pred})

        df_pred = pd.DataFrame(rows)

        # 等比例調整使總人數吻合預測值
        cur_total = df_pred["count"].sum()
        if cur_total > 0 and subj == "english":
            scale = predicted_total_116 / cur_total
            df_pred["count"] = (df_pred["count"] * scale).round().astype(int)

        result[subj] = df_pred

    return result, predicted_total_116


def build_joint_distribution(pred_data: dict, base_n: int) -> pd.DataFrame:
    """從邊際分布建立聯合分布（獨立假設）"""
    probs = {}
    grades = {}
    for subj, df in pred_data.items():
        total = df["count"].sum()
        probs[subj] = (df["count"] / total).values
        grades[subj] = df["grade"].values

    rows = []
    for combo in itertools.product(range(15), repeat=3):
        e_g = grades["english"][combo[0]]
        c_g = grades["chinese"][combo[1]]
        s_g = grades["social"][combo[2]]
        joint_prob = probs["english"][combo[0]] * probs["chinese"][combo[1]] * probs["social"][combo[2]]
        cnt = round(joint_prob * base_n)
        if cnt > 0:
            rows.append({
                "english": e_g, "chinese": c_g, "social": s_g,
                "total": e_g + c_g + s_g,
                "count": cnt
            })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════
# 圖表
# ═══════════════════════════════════════

def plot_trends(trend_df: pd.DataFrame, pred_data: dict) -> go.Figure:
    """繪製歷年趨勢 + 116 預測圖"""
    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=[
            "英文 加權平均級分", "國文 加權平均級分", "社會 加權平均級分",
            "英文 級分分布比較", "國文 級分分布比較", "社會 級分分布比較",
        ]
    )

    colors = {111: "#BDBDBD", 112: "#90CAF9", 113: "#64B5F6",
              114: "#1976D2", 115: "#0D47A1", 116: "#FF5722"}
    subj_col = {"english": 1, "chinese": 2, "social": 3}
    subj_name = {"english": "英文", "chinese": "國文", "social": "社會"}

    years_hist = sorted(trend_df["year"].tolist())

    # 上排：各科平均級分趨勢折線
    for subj, col in subj_col.items():
        vals = trend_df[f"{subj}_mean"].tolist()
        yrs  = trend_df["year"].tolist()
        pred_mean = (pred_data[subj]["grade"] * pred_data[subj]["count"]).sum() / pred_data[subj]["count"].sum()
        all_yrs  = yrs  + [116]
        all_vals = vals + [round(pred_mean, 3)]

        fig.add_trace(go.Scatter(
            x=all_yrs[:-1], y=all_vals[:-1],
            mode="lines+markers", name=f"{subj_name[subj]}歷年",
            line=dict(color="#1976D2"), marker=dict(size=8),
            showlegend=(col == 1),
        ), row=1, col=col)

        fig.add_trace(go.Scatter(
            x=[116], y=[all_vals[-1]],
            mode="markers", name="116預測",
            marker=dict(color="#FF5722", size=12, symbol="star"),
            showlegend=(col == 1),
        ), row=1, col=col)

    # 下排：115 vs 116 預測分布比較
    all_data_for_plot = {}
    for year in [114, 115]:
        if year == 114:
            all_data_for_plot[year] = parse_114()
        else:
            all_data_for_plot[year] = parse_115()

    for subj, col in subj_col.items():
        for year, c in [(115, "#1976D2"), (116, "#FF5722")]:
            if year == 116:
                df = pred_data[subj]
            else:
                df = all_data_for_plot[year][subj]

            total = df["count"].sum()
            pct = (df["count"] / total * 100).round(2).tolist() if total > 0 else [0] * 15

            fig.add_trace(go.Bar(
                x=df["grade"].tolist(), y=pct,
                name=f"{year}年",
                marker_color=c,
                opacity=0.7,
                showlegend=(col == 1),
            ), row=2, col=col)

    fig.update_layout(
        title_text="115→116 學測分布趨勢與預測",
        height=700,
        barmode="overlay",
    )
    for col in [1, 2, 3]:
        fig.update_xaxes(title_text="級分", row=2, col=col)
        fig.update_yaxes(title_text="平均級分", row=1, col=col)
        fig.update_yaxes(title_text="佔比(%)", row=2, col=col)

    return fig


# ═══════════════════════════════════════
# 主程式
# ═══════════════════════════════════════

def main():
    print("=== 載入歷年資料 ===")
    all_data = {}

    for year in [111, 112, 113]:
        print(f"  解析 {year}年...")
        all_data[year] = parse_111_to_113(year)

    print(f"  解析 114年...")
    all_data[114] = parse_114()

    print(f"  解析 115年...")
    all_data[115] = parse_115()

    # 各科均標趨勢
    print("\n=== 各科加權平均級分趨勢 ===")
    trend_df = build_trend_table(all_data)
    print(trend_df[["year", "english_mean", "chinese_mean", "social_mean",
                     "english_p50", "english_p88"]].to_string(index=False))

    # 116 預測
    print("\n=== 預測 116 年分布 ===")
    pred_data, pred_total = project_116(trend_df, all_data)

    for subj in ["english", "chinese", "social"]:
        df = pred_data[subj]
        mean = compute_weighted_mean(df)
        p50  = compute_percentile_grade(df, 50)
        p88  = compute_percentile_grade(df, 88)
        print(f"  {SUBJECTS[subj]}: 總人數={df['count'].sum():,}  均值={mean:.2f}  均標(p50)={p50}  前標(p88)={p88}")

    # 建立聯合分布
    print("\n=== 建立 116 年聯合分布 ===")
    joint_df = build_joint_distribution(pred_data, pred_total)
    out_path = OUTPUT_DIR / "ceec_116_predicted_distribution.csv"
    joint_df.to_csv(out_path, index=False)
    print(f"  已存出：{out_path}")
    print(f"  {len(joint_df)} 種分數組合，共 {joint_df['count'].sum():,} 人")

    # 趨勢圖
    print("\n=== 繪製趨勢圖 ===")
    fig = plot_trends(trend_df, pred_data)
    fig_path = OUTPUT_DIR / "trend_116_prediction.html"
    fig.write_html(str(fig_path))
    print(f"  已存出：{fig_path}（用瀏覽器開啟）")

    # 趨勢摘要表
    print("\n=== 歷年各科均標（p50）===")
    for subj, name in SUBJECTS.items():
        vals = [f"{all_data[y][subj]['grade'][all_data[y][subj]['count'].cumsum() >= all_data[y][subj]['count'].sum()*0.5].iloc[0]}級" for y in sorted(all_data.keys())]
        pred_p50 = compute_percentile_grade(pred_data[subj], 50)
        print(f"  {name}: {dict(zip(sorted(all_data.keys()), vals))} → 116預測: {pred_p50}級")

    print("\n完成！請將 ceec_116_predicted_distribution.csv 上傳至 app 進行模擬。")


if __name__ == "__main__":
    main()
