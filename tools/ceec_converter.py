"""
考招中心 (CEEC) 資料轉換工具
=========================================
將大學入學考試中心公布的學測級分分布資料，
轉換為招生策略估算 app 所需的 CSV 格式。

支援兩種輸入格式：
  1. 各科「邊際分布」（每科分開的級分人數，考招中心最常見格式）
  2. 已有聯合分布的 Excel/CSV

輸出：
  - sample_distribution.csv（模式 B，適合 app 匯入）
  - 可選：sample_applicants.csv（模式 A，以聯合分布抽樣模擬個別考生）

使用方式：
  python tools/ceec_converter.py --help
  python tools/ceec_converter.py marginal --english english.csv --chinese chinese.csv --social social.csv
  python tools/ceec_converter.py joint --input joint_dist.xlsx
  python tools/ceec_converter.py sample --input sample_dist.csv --n 5000
"""

import argparse
import sys
import itertools
import pandas as pd
import numpy as np
from pathlib import Path

# ── 常數設定 ──
SUBJECT_COLS = ["english", "chinese", "social", "total"]
MAX_GRADE = 15       # 學測單科最高級分
MIN_GRADE = 1        # 學測單科最低級分 (0 = 缺考，通常不納入計算)
MAX_TOTAL = 75       # 五科總級分上限（若只算三科則為 45）

OUTPUT_DIR = Path("sample_data")


# ═══════════════════════════════════════════════════════
# 工具函式
# ═══════════════════════════════════════════════════════

def read_marginal_csv(filepath: str, subject: str) -> pd.DataFrame:
    """
    讀取單科邊際分布 CSV。

    預期格式（考招中心常見）：
        grade, count
        15, 3241
        14, 12445
        ...
    或只有兩欄（無標題）也可自動偵測。
    """
    df = pd.read_csv(filepath, header=None)

    # 自動偵測欄位
    if df.shape[1] < 2:
        raise ValueError(f"{filepath} 至少需要兩欄（級分、人數）")

    # 若第一列是標題文字，跳過
    first_val = str(df.iloc[0, 0]).strip()
    if not first_val.isdigit():
        df = pd.read_csv(filepath)
        df.columns = [c.strip().lower() for c in df.columns]
        grade_col = [c for c in df.columns if "grade" in c or "級分" in c or "score" in c]
        count_col = [c for c in df.columns if "count" in c or "人數" in c or "num" in c]
        if not grade_col or not count_col:
            raise ValueError(f"無法自動判斷 {filepath} 的欄位，請確認含有級分與人數欄位。")
        df = df[[grade_col[0], count_col[0]]].rename(columns={grade_col[0]: subject, count_col[0]: "count"})
    else:
        df.columns = [subject, "count"]

    df[subject] = pd.to_numeric(df[subject], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df = df.dropna().astype({subject: int, "count": int})

    # 過濾合理範圍
    df = df[(df[subject] >= MIN_GRADE) & (df[subject] <= MAX_GRADE)]
    return df.reset_index(drop=True)


def marginal_to_joint(marginals: dict, method: str = "independent") -> pd.DataFrame:
    """
    將各科邊際分布合併為聯合分布。

    method:
      "independent" — 假設各科獨立，聯合機率 = 各科機率相乘（快速但有偏差）
      "sample"      — 從各科分別抽樣，再隨機配對（保留邊際分布但忽略相關性）

    注意：真實考生各科分數有正相關，independence 假設會高估極端組合的人數。
    若系上有實際的聯合分布資料，請改用 `joint` 子命令直接匯入。
    """
    subjects = list(marginals.keys())

    if method == "independent":
        # 計算各科的機率分布
        probs = {}
        grades = {}
        for subj, df in marginals.items():
            total = df["count"].sum()
            probs[subj] = (df["count"] / total).values
            grades[subj] = df[subj].values

        # 笛卡兒積 × 聯合機率
        rows = []
        total_applicants = sum(marginals[subjects[0]]["count"])  # 以第一科總人數估算

        for combo in itertools.product(*[range(len(grades[s])) for s in subjects]):
            record = {}
            joint_prob = 1.0
            for i, subj in enumerate(subjects):
                record[subj] = grades[subj][combo[i]]
                joint_prob *= probs[subj][combo[i]]

            count = round(joint_prob * total_applicants)
            if count > 0:
                record["count"] = count
                rows.append(record)

        return pd.DataFrame(rows)

    elif method == "sample":
        # 從各科邊際分布抽樣
        n = sum(marginals[subjects[0]]["count"])
        sampled = {}
        for subj, df in marginals.items():
            weights = df["count"] / df["count"].sum()
            sampled[subj] = np.random.choice(df[subj].values, size=n, p=weights)

        df_sample = pd.DataFrame(sampled)
        # 分組計算聯合分布
        group_cols = subjects
        joint = df_sample.groupby(group_cols).size().reset_index(name="count")
        return joint

    else:
        raise ValueError(f"未知的 method: {method}，請用 'independent' 或 'sample'")


def add_total(df: pd.DataFrame, subject_cols: list) -> pd.DataFrame:
    """若沒有 total 欄，自動加總現有科目欄位估算（每科 × 約 1.5 倍以模擬其他科目）"""
    if "total" not in df.columns:
        print("  [提示] 未偵測到 total 欄位，以各科加總估算（僅供參考）")
        existing = [c for c in subject_cols if c != "total" and c in df.columns]
        df["total"] = df[existing].sum(axis=1)
    return df


def joint_dist_to_csv(df: pd.DataFrame, output_path: Path) -> None:
    """存出聯合分布 CSV"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"  [完成] 已存出：{output_path}  ({len(df)} 種分數組合，共 {df['count'].sum()} 位考生)")


def sample_applicants_from_dist(dist_df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """
    從聯合分布抽樣，生成 n 筆個別考生資料。

    用途：當你只有分布統計但需要模式 A（個別考生）格式時使用。
    """
    rng = np.random.default_rng(seed)
    weights = dist_df["count"] / dist_df["count"].sum()
    indices = rng.choice(len(dist_df), size=n, p=weights)

    subject_cols = [c for c in dist_df.columns if c != "count"]
    sampled = dist_df.iloc[indices][subject_cols].reset_index(drop=True)
    sampled.insert(0, "applicant_id", range(1, n + 1))
    return sampled


# ═══════════════════════════════════════════════════════
# 子命令處理
# ═══════════════════════════════════════════════════════

def cmd_marginal(args):
    """
    從各科邊際分布 CSV 合併為聯合分布
    """
    print("\n=== 邊際分布合併模式 ===")
    marginals = {}

    subject_map = {
        "english": args.english,
        "chinese": args.chinese,
        "social": args.social,
    }
    for subj, filepath in subject_map.items():
        if filepath:
            print(f"  載入 {subj}：{filepath}")
            marginals[subj] = read_marginal_csv(filepath, subj)
            print(f"    → 級分範圍 {marginals[subj][subj].min()}~{marginals[subj][subj].max()}，"
                  f"共 {marginals[subj]['count'].sum():,} 人")

    if not marginals:
        print("錯誤：請至少提供一科的分布檔案（--english / --chinese / --social）")
        sys.exit(1)

    print(f"\n  合併方式：{args.method}")
    joint_df = marginal_to_joint(marginals, method=args.method)
    joint_df = add_total(joint_df, list(marginals.keys()))

    output_path = OUTPUT_DIR / args.output
    joint_dist_to_csv(joint_df, output_path)

    if args.sample_n > 0:
        sample_df = sample_applicants_from_dist(joint_df, args.sample_n)
        sample_path = OUTPUT_DIR / "sample_applicants_from_ceec.csv"
        sample_df.to_csv(sample_path, index=False)
        print(f"  [完成] 已存出個別考生抽樣：{sample_path}  ({len(sample_df)} 筆)")


def cmd_joint(args):
    """
    直接讀取已有聯合分布（Excel 或 CSV）並轉換格式
    """
    print("\n=== 聯合分布匯入模式 ===")
    filepath = Path(args.input)

    if filepath.suffix.lower() in [".xlsx", ".xls"]:
        print(f"  載入 Excel：{filepath}（工作表：{args.sheet}）")
        df = pd.read_excel(filepath, sheet_name=args.sheet, header=args.header_row)
    else:
        print(f"  載入 CSV：{filepath}")
        df = pd.read_csv(filepath)

    df.columns = [str(c).strip().lower() for c in df.columns]
    print(f"  偵測欄位：{list(df.columns)}")

    # 欄位對應（中英文）
    rename_map = {
        "英文": "english", "english": "english",
        "國文": "chinese", "chinese": "chinese",
        "社會": "social", "social": "social",
        "總級分": "total", "total": "total",
        "人數": "count", "count": "count",
    }
    df = df.rename(columns=rename_map)

    # 只保留需要的欄位
    keep = [c for c in SUBJECT_COLS + ["count"] if c in df.columns]
    if "count" not in df.columns:
        print("  [警告] 未找到人數欄位，每列視為 1 人")
        df["count"] = 1
        keep.append("count")

    df = df[keep].dropna()

    output_path = OUTPUT_DIR / args.output
    joint_dist_to_csv(df, output_path)

    if args.sample_n > 0:
        sample_df = sample_applicants_from_dist(df, args.sample_n)
        sample_path = OUTPUT_DIR / "sample_applicants_from_ceec.csv"
        sample_df.to_csv(sample_path, index=False)
        print(f"  [完成] 已存出個別考生抽樣：{sample_path}  ({len(sample_df)} 筆)")


def cmd_sample(args):
    """
    從已有的分布 CSV（模式 B）抽樣生成個別考生資料（模式 A）
    """
    print("\n=== 抽樣模式 ===")
    dist_df = pd.read_csv(args.input)
    print(f"  載入分布：{args.input}  ({len(dist_df)} 種組合，{dist_df['count'].sum():,} 人)")

    sample_df = sample_applicants_from_dist(dist_df, args.n, seed=args.seed)
    output_path = OUTPUT_DIR / args.output
    OUTPUT_DIR.mkdir(exist_ok=True)
    sample_df.to_csv(output_path, index=False)
    print(f"  [完成] 已存出：{output_path}  ({len(sample_df)} 筆考生)")


def cmd_demo(args):
    """
    生成模擬的考招中心格式示範檔案（讓使用者了解預期格式）
    """
    print("\n=== 生成考招中心示範格式 ===")
    rng = np.random.default_rng(42)

    demo_dir = Path("tools/demo_input")
    demo_dir.mkdir(exist_ok=True)

    # 模擬各科邊際分布（近似常態分布於高分端）
    for subj, mean, std in [("english", 10.5, 2.5), ("chinese", 9.8, 2.2), ("social", 10.2, 2.4)]:
        grades = list(range(1, 16))
        try:
            from scipy.stats import norm
            probs = np.array([norm.pdf(g, mean, std) for g in grades])
        except ImportError:
            # scipy 不存在時用簡單近似（高斯形狀）
            probs = np.array([np.exp(-0.5 * ((g - mean) / std) ** 2) for g in grades])

        probs /= probs.sum()
        counts = (probs * 120000).astype(int)  # 假設 12 萬人報考

        demo_df = pd.DataFrame({"grade": grades, "count": counts})
        demo_path = demo_dir / f"{subj}_dist.csv"
        demo_df.to_csv(demo_path, index=False)
        print(f"  已生成：{demo_path}")

    print(f"\n  使用方式：")
    print(f"  python tools/ceec_converter.py marginal \\")
    print(f"    --english tools/demo_input/english_dist.csv \\")
    print(f"    --chinese tools/demo_input/chinese_dist.csv \\")
    print(f"    --social  tools/demo_input/social_dist.csv  \\")
    print(f"    --method independent --sample-n 500")


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="考招中心資料轉換工具 → 招生策略估算 app CSV 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 從各科邊際分布合併（獨立假設）
  python tools/ceec_converter.py marginal \\
      --english english_dist.csv \\
      --chinese chinese_dist.csv \\
      --social  social_dist.csv

  # 從各科邊際分布合併，並額外生成 500 筆個別考生（抽樣）
  python tools/ceec_converter.py marginal \\
      --english english_dist.csv --chinese chinese_dist.csv --social social_dist.csv \\
      --sample-n 500

  # 直接匯入已有聯合分布 Excel
  python tools/ceec_converter.py joint --input 歷年分布.xlsx --sheet "113年"

  # 從現有分布 CSV 抽樣生成個別考生
  python tools/ceec_converter.py sample --input sample_data/sample_distribution.csv --n 1000

  # 生成示範輸入格式
  python tools/ceec_converter.py demo
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- marginal --
    p_marginal = subparsers.add_parser("marginal", help="從各科邊際分布合併為聯合分布")
    p_marginal.add_argument("--english", help="英文級分分布 CSV 檔路徑")
    p_marginal.add_argument("--chinese", help="國文級分分布 CSV 檔路徑")
    p_marginal.add_argument("--social",  help="社會級分分布 CSV 檔路徑")
    p_marginal.add_argument("--method", choices=["independent", "sample"], default="independent",
                            help="聯合分布合併方式（預設：independent）")
    p_marginal.add_argument("--sample-n", type=int, default=0, dest="sample_n",
                            help="額外生成 N 筆個別考生模式 A CSV（0 = 不生成）")
    p_marginal.add_argument("--output", default="ceec_distribution.csv",
                            help="輸出檔名（存放於 sample_data/，預設：ceec_distribution.csv）")
    p_marginal.set_defaults(func=cmd_marginal)

    # -- joint --
    p_joint = subparsers.add_parser("joint", help="直接匯入現有聯合分布（Excel/CSV）")
    p_joint.add_argument("--input", required=True, help="輸入檔案路徑（.xlsx 或 .csv）")
    p_joint.add_argument("--sheet", default=0, help="Excel 工作表名稱或索引（預設：第一張）")
    p_joint.add_argument("--header-row", type=int, default=0, dest="header_row",
                         help="標題列位置（0 起算，預設：0）")
    p_joint.add_argument("--sample-n", type=int, default=0, dest="sample_n",
                         help="額外生成 N 筆個別考生模式 A CSV（0 = 不生成）")
    p_joint.add_argument("--output", default="ceec_distribution.csv",
                         help="輸出檔名（存放於 sample_data/，預設：ceec_distribution.csv）")
    p_joint.set_defaults(func=cmd_joint)

    # -- sample --
    p_sample = subparsers.add_parser("sample", help="從分布 CSV 抽樣生成個別考生資料")
    p_sample.add_argument("--input", required=True, help="輸入分布 CSV（模式 B 格式）")
    p_sample.add_argument("--n", type=int, default=500, help="抽樣人數（預設：500）")
    p_sample.add_argument("--seed", type=int, default=42, help="隨機種子（預設：42）")
    p_sample.add_argument("--output", default="ceec_applicants.csv",
                          help="輸出檔名（存放於 sample_data/，預設：ceec_applicants.csv）")
    p_sample.set_defaults(func=cmd_sample)

    # -- demo --
    p_demo = subparsers.add_parser("demo", help="生成示範輸入檔，了解預期格式")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
