# 淡江英文系招生策略估算系統 (MVP)

第一階段篩選模擬工具，供系上內部行政人員模擬不同招生策略（篩選倍數、科目權重）對篩選結果的影響。

## 功能

- **招生規則設定**：招生名額、篩選倍數、各科權重
- **資料匯入**：支援個別考生資料 (模式 A) 與分布統計資料 (模式 B)
- **單一策略模擬**：計算 cutoff、通過人數、分數分布
- **多策略比較**：同時比較 2~4 組策略的差異
- **篩選倍數敏感度分析**：觀察不同倍數對結果的影響
- **結果下載**：匯出模擬結果 CSV

## 安裝與執行

### 1. 安裝 Python

請先安裝 Python 3.9 以上版本。建議從 [python.org](https://www.python.org/downloads/) 下載安裝。

### 2. 安裝套件

```bash
pip install -r requirements.txt
```

### 3. 啟動應用程式

```bash
streamlit run app.py
```

瀏覽器會自動開啟 `http://localhost:8501`。

## 資料格式

### 模式 A：個別考生資料

| applicant_id | english | chinese | social | total |
|---|---|---|---|---|
| 1 | 15 | 12 | 10 | 52 |
| 2 | 14 | 11 | 13 | 55 |

### 模式 B：分布統計資料

| english | chinese | social | total | count |
|---|---|---|---|---|
| 15 | 15 | 15 | 60 | 12 |
| 15 | 14 | 14 | 58 | 15 |

範例檔案位於 `sample_data/` 資料夾。

## 檔案結構

```
├── app.py                  # Streamlit 主程式
├── modules/
│   ├── data_loader.py      # 資料載入與格式轉換
│   ├── simulator.py        # 篩選模擬引擎
│   ├── metrics.py          # 統計指標計算
│   ├── charts.py           # 圖表繪製 (Plotly)
│   └── utils.py            # 共用工具
├── sample_data/
│   ├── sample_applicants.csv
│   └── sample_distribution.csv
├── requirements.txt
└── README.md
```

## 計算邏輯

- **篩選分數** = Σ (科目分數 × 科目權重)
- **通過人數** = 招生名額 × 篩選倍數
- **Cutoff** = 第 N 名的篩選分數（同分皆通過）

## 未來擴充方向

- 第二階段書審/面試分數模擬
- 到場率與備取遞補模擬
- 歷年資料比較
- PDF 報表匯出
- 登入權限管理
