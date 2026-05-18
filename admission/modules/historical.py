"""
淡江英文系歷年個人申請篩選資料

資料來源：
  - 甄選會 (cac.edu.tw) 各年度篩選通過名單 — 通過人數
  - 甄選會篩選標準一覽表 (PNG) — 報名人數（需手動查閱）
  - 交叉查榜 (swissvoice.com) — 通過人數近似值
  - University TW (university-tw.ldkrsi.men) — 篩選倍率

注意：報名人數需從甄選會 PNG 圖檔手動抄錄。
     通過人數已從甄選會或交叉查榜取得。
     若你有更精確的數據，請直接修改此檔案。
"""

# 歷年資料字典：年份 → 各項數據
HISTORICAL_DATA = {
    111: {
        "招生名額": 55,
        "報名人數": None,     # 待從甄選會 PNG 抄錄
        "通過人數": 209,      # 交叉查榜
        "篩選科目": "英文、國文",
        "篩選倍率": "英文3, 國文5",
        "篩選結果": {},
        "備註": "",
    },
    112: {
        "招生名額": 53,
        "報名人數": None,     # 待從甄選會 PNG 抄錄
        "通過人數": 164,      # 交叉查榜
        "篩選科目": "英文、國文",
        "篩選倍率": "英文3, 國文5",
        "篩選結果": {},
        "備註": "",
    },
    113: {
        "招生名額": 51,
        "報名人數": None,     # 待從甄選會 PNG 抄錄
        "通過人數": 198,      # 交叉查榜
        "篩選科目": "英文、國文",
        "篩選倍率": "英文6, 國文3",
        "篩選結果": {},
        "備註": "",
    },
    114: {
        "招生名額": 51,
        "報名人數": None,     # 待從甄選會 PNG 抄錄
        "通過人數": 171,      # 甄選會通過名單 (confirmed)
        "篩選科目": "英文、國文",
        "篩選倍率": "英文6, 國文3",
        "篩選結果": {"english": 8, "chinese": 10},
        "備註": "有超額篩選",
    },
    115: {
        "招生名額": 50,
        "報名人數": None,     # 待從甄選會 PNG 抄錄
        "通過人數": 164,      # 甄選會通過名單 (confirmed)，超篩14人
        "篩選科目": "英文、國文、國英相加",
        "篩選倍率": "英文6, 國文5, 國英相加3",
        "篩選結果": {},
        "備註": "超篩14人（共164通過）",
    },
}


def get_historical_table():
    """回傳歷年資料的 DataFrame，用於顯示"""
    import pandas as pd
    rows = []
    for year, data in sorted(HISTORICAL_DATA.items()):
        rows.append({
            "學年度": year,
            "招生名額": data["招生名額"],
            "報名人數": data["報名人數"] or "—",
            "通過人數": data["通過人數"] or "—",
            "篩選倍率": data["篩選倍率"],
            "備註": data["備註"],
        })
    return pd.DataFrame(rows)


def get_avg_passed_count():
    """取得歷年平均通過人數"""
    counts = [d["通過人數"] for d in HISTORICAL_DATA.values() if d["通過人數"]]
    return int(sum(counts) / len(counts)) if counts else 180


def estimate_application_count():
    """
    估算報名人數。

    邏輯：
      - 若有手動輸入的報名人數，取平均
      - 否則根據通過人數推估：報名人數 ≈ 通過人數 × 1.3~1.5
        （因為有部分考生未通過篩選）
    """
    known_app = [d["報名人數"] for d in HISTORICAL_DATA.values()
                 if d["報名人數"] is not None and d["報名人數"] > 0]
    if known_app:
        return int(sum(known_app) / len(known_app))

    # 用通過人數推估
    avg_passed = get_avg_passed_count()
    # 報名人數通常比通過人數高 30%~50%（部分被篩掉）
    return int(avg_passed * 1.3)


def get_reference_info():
    """回傳參考資訊字串"""
    avg_passed = get_avg_passed_count()
    return f"""
**已取得的資料：**
- 通過篩選人數：111年 209人、112年 164人、113年 198人、114年 171人、115年 164人
- 平均通過人數：約 **{avg_passed}** 人
- 來源：甄選會通過名單 + 交叉查榜

**尚需補充：報名人數**

報名人數 > 通過人數（部分考生被篩掉）。甄選會「各校系篩選標準一覽表」有報名人數，
但資料以 PNG 圖檔呈現，需手動查閱：

1. 前往 [甄選會歷年統計](https://www.cac.edu.tw/apply115/history_statistics.php)
2. 選擇年度 → 篩選標準一覽表
3. 找到 **(014) 淡江大學** → 英文學系 (014082)
4. 記錄「報名人數」欄位

取得後，在上方手動輸入即可。
"""
