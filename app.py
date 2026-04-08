"""
淡江英文系招生策略估算 App (MVP)

使用 Streamlit 建置，模擬真實甄選入學第一階段篩選流程：
  檢定門檻 → 志願申請率 → 逐科超額篩選
"""
import os
import streamlit as st
import pandas as pd

from modules.data_loader import (
    load_csv, detect_data_mode, normalize_to_applicants,
    get_data_summary, generate_sample_applicants,
)
from modules.simulator import (
    StrategyConfig, ScreeningLevel, SimulationResult,
    GRADE_STANDARDS_115, STANDARD_LEVELS,
    run_simulation, run_comparison,
)
from modules.metrics import compute_result_metrics, build_comparison_table
from modules.charts import (
    plot_pass_fail_bar, plot_score_distribution,
    plot_cutoff_comparison, plot_selected_count_comparison,
    plot_subject_avg_comparison,
)
from modules.utils import (
    DEFAULT_SUBJECTS, DEFAULT_WEIGHTS, DEFAULT_QUOTA,
    DEFAULT_SCREENING_MULTIPLIER, DEFAULT_TIEBREAK_ORDER,
    validate_weights, get_subject_display_name,
)
from modules.historical import (
    HISTORICAL_DATA, get_historical_table,
    estimate_application_count, get_avg_passed_count,
)

# ── 頁面設定 ──
st.set_page_config(page_title="淡江英文系招生策略估算", page_icon="🎓", layout="wide")
st.title("淡江英文系招生策略估算系統")
st.caption("第一階段篩選模擬工具 — 內部行政使用")

SUBJECT_OPTIONS = list(DEFAULT_SUBJECTS.keys())
SUBJECT_NAMES = DEFAULT_SUBJECTS


# ══════════════════════════════════════════
# Sidebar：完整招生規則設定
# ══════════════════════════════════════════

st.sidebar.header("一、基本設定")
quota = st.sidebar.number_input("招生名額", min_value=1, value=DEFAULT_QUOTA, step=1)

# ── 檢定門檻 ──
st.sidebar.header("二、檢定門檻")
st.sidebar.caption("考生必須各科都達標才能進入篩選")

thresholds = {}
for subj_key, subj_name in SUBJECT_NAMES.items():
    thresholds[subj_key] = st.sidebar.selectbox(
        f"{subj_name} 最低標準",
        STANDARD_LEVELS,
        index=0,  # 預設「不設」
        key=f"thresh_{subj_key}",
    )

# ── 上限門檻（排除高分、不會填本系的考生） ──
with st.sidebar.expander("🔺 上限門檻（排除不可能報名者）", expanded=False):
    st.caption("高分考生不會填淡江英文系，可設上限排除。例：英文設「頂標」可排除英文 13 分的考生。")
    upper_thresholds = {}
    for subj_key, subj_name in SUBJECT_NAMES.items():
        upper_thresholds[subj_key] = st.selectbox(
            f"{subj_name} 最高上限",
            ["不設"] + STANDARD_LEVELS[1:],  # 不設、頂標、前標...
            index=0,
            key=f"upper_{subj_key}",
        )

# ── 篩選關卡 ──
st.sidebar.header("三、超額篩選")
st.sidebar.caption("依序篩選，可選單科或組合（加總）")

# 預先建立組合選項
SCREEN_OPTIONS = list(SUBJECT_OPTIONS)  # 單科
SCREEN_OPTIONS += [
    "english+chinese", "english+history", "chinese+history",
    "english+chinese+history",
]
def format_screen_option(x):
    parts = x.split("+")
    return "+".join(SUBJECT_NAMES.get(p, p) for p in parts)

num_levels = st.sidebar.selectbox("篩選關卡數", [1, 2, 3], index=1)
screening_levels = []
for i in range(num_levels):
    st.sidebar.markdown(f"**第 {i+1} 關**")
    col_s, col_m = st.sidebar.columns(2)
    with col_s:
        subj = st.selectbox(
            "科目", SCREEN_OPTIONS,
            index=min(i, len(SCREEN_OPTIONS)-1),
            format_func=format_screen_option,
            key=f"screen_subj_{i}",
        )
    with col_m:
        mult = st.number_input(
            "倍率", min_value=1.0, max_value=20.0,
            value=float(3 + i * 2), step=0.5,
            key=f"screen_mult_{i}",
        )
    screening_levels.append(ScreeningLevel(subject=subj, multiplier=mult))

# ── 志願申請率 ──
st.sidebar.header("四、志願申請率")
st.sidebar.caption("並非所有達標考生都會報名本系")

# 提供歷年參考
estimated_app = estimate_application_count()

app_mode = st.sidebar.radio(
    "估算方式",
    ["全部合格考生", "指定申請人數", "指定申請率"],
    index=1,
    key="app_mode",
    help=f"參考值：歷年約 {estimated_app} 人報名",
)

application_rate = None
application_count = None
if app_mode == "指定申請人數":
    application_count = st.sidebar.number_input(
        "申請人數", min_value=1, value=estimated_app, step=10,
        help="可參考下方「歷年篩選資料」中的報名人數",
    )
elif app_mode == "指定申請率":
    application_rate = st.sidebar.slider(
        "申請率 (%)", min_value=0.1, max_value=100.0, value=5.0, step=0.1,
    ) / 100

# ── 同分參酌 ──
st.sidebar.header("五、同分參酌順序")
st.sidebar.caption("預設：英文 > 國文 > 社會 > 總級分")
tiebreak_order = DEFAULT_TIEBREAK_ORDER


# ── Session State ──
if "applicant_data" not in st.session_state:
    st.session_state.applicant_data = None
if "data_mode" not in st.session_state:
    st.session_state.data_mode = None


# ══════════════════════════════════════════
# 共用函式：建立策略 config
# ══════════════════════════════════════════

def make_config(name: str, custom_thresholds=None, custom_levels=None,
                custom_app_rate=None, custom_app_count=None,
                custom_upper=None) -> StrategyConfig:
    """建立策略設定，使用 sidebar 值或自訂覆寫"""
    return StrategyConfig(
        name=name,
        quota=quota,
        thresholds=custom_thresholds or thresholds,
        upper_thresholds=custom_upper if custom_upper is not None else upper_thresholds,
        screening_levels=custom_levels or screening_levels,
        application_rate=custom_app_rate if custom_app_rate is not None else application_rate,
        application_count=custom_app_count if custom_app_count is not None else application_count,
        grade_standards=GRADE_STANDARDS_115,
        tiebreak_order=tiebreak_order,
        weights=DEFAULT_WEIGHTS,
    )


# ══════════════════════════════════════════
# Tabs
# ══════════════════════════════════════════

tab_upload, tab_single, tab_compare, tab_history, tab_download = st.tabs([
    "📁 資料上傳", "🔍 單一策略模擬", "⚖️ 多策略比較", "📋 歷年資料", "📥 結果下載",
])


# ═══════════════════════════════════════
# Tab 1: 資料上傳
# ═══════════════════════════════════════
with tab_upload:
    st.header("資料上傳")

    st.subheader("載入歷年學測資料")

    CEEC_FILES = {
        "111學年度（實際）": "sample_data/ceec_111_distribution.csv",
        "112學年度（實際）": "sample_data/ceec_112_distribution.csv",
        "113學年度（實際）": "sample_data/ceec_113_distribution.csv",
        "114學年度（實際）": "sample_data/ceec_114_distribution.csv",
        "115學年度（實際）": "sample_data/ceec_115_distribution.csv",
        "116學年度（預測）": "sample_data/ceec_116_predicted_distribution.csv",
    }

    available = {k: v for k, v in CEEC_FILES.items() if os.path.exists(v)}

    if available:
        ceec_col1, ceec_col2 = st.columns([2, 1])
        with ceec_col1:
            selected_year = st.selectbox(
                "選擇年份", list(available.keys()),
                index=len(available) - 1,
                help="已從考招中心下載的歷年真實資料（116 為統計外推預測）",
            )
        # 116年才顯示人數調整
        is_116 = "116" in selected_year
        if is_116:
            target_total = st.number_input(
                "調整總考生人數（預測值 117,767，請依實際情況修正）",
                min_value=50000, max_value=150000,
                value=105000, step=1000,
                help="116年預測值因線性回歸偏高，建議依少子化趨勢下調至 10~11 萬",
            )

        with ceec_col2:
            st.write(""); st.write("")
            if st.button("載入選擇年份", type="primary"):
                try:
                    raw_df = pd.read_csv(available[selected_year])
                    # 116年：按目標人數縮放 count 欄
                    if is_116 and "count" in raw_df.columns:
                        current_total = raw_df["count"].sum()
                        raw_df["count"] = (raw_df["count"] * target_total / current_total).round().astype(int)
                    mode = detect_data_mode(raw_df)
                    df = normalize_to_applicants(raw_df, mode)
                    st.session_state.applicant_data = df
                    st.session_state.data_mode = mode
                    st.session_state.loaded_year = selected_year
                    st.success(f"已載入 {selected_year}，共 {len(df):,} 筆考生資料")
                except Exception as e:
                    st.error(f"載入失敗：{e}")

        with st.expander("📊 各年份關鍵指標比較"):
            summary_rows = []
            for label, path in available.items():
                if os.path.exists(path):
                    try:
                        d = pd.read_csv(path)
                        w = d.get("count", pd.Series([1]*len(d)))
                        total = w.sum()
                        def wmean(col, _d=d, _w=w, _t=total):
                            return round((_d[col] * _w).sum() / _t, 2) if col in _d.columns else "-"
                        summary_rows.append({
                            "年份": label,
                            "模擬考生數": f"{total:,}",
                            "英文均值": wmean("english"),
                            "國文均值": wmean("chinese"),
                            "歷史均值": wmean("history"),
                        })
                    except:
                        pass
            if summary_rows:
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.divider()

    col_upload, col_sample = st.columns(2)
    with col_upload:
        st.subheader("上傳自訂 CSV")
        uploaded_file = st.file_uploader("選擇 CSV 檔案", type=["csv"])
        if uploaded_file is not None:
            try:
                raw_df = load_csv(uploaded_file)
                mode = detect_data_mode(raw_df)
                df = normalize_to_applicants(raw_df, mode)
                st.session_state.applicant_data = df
                st.session_state.data_mode = mode
                st.success(f"載入成功，共 {len(df)} 筆考生資料")
            except Exception as e:
                st.error(f"載入失敗：{e}")

    with col_sample:
        st.subheader("生成隨機範例")
        sample_size = st.number_input("考生人數", min_value=50, max_value=5000, value=500, step=50)
        if st.button("生成", type="secondary"):
            df = generate_sample_applicants(n=sample_size)
            st.session_state.applicant_data = df
            st.session_state.data_mode = "A"
            st.success(f"已生成 {len(df)} 筆")

    if st.session_state.applicant_data is not None:
        st.divider()
        st.subheader("資料摘要")
        df = st.session_state.applicant_data
        summary = get_data_summary(df)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("考生總人數", f"{summary['total_applicants']:,}")
            for subj_key, stats in summary["subjects"].items():
                st.metric(f"{get_subject_display_name(subj_key)}平均", stats["mean"])
        with col2:
            st.dataframe(df.head(20), use_container_width=True, height=280)
            st.caption("（僅顯示前 20 筆）")


# ═══════════════════════════════════════
# 顯示模擬結果的共用函式
# ═══════════════════════════════════════

def show_simulation_result(result: SimulationResult):
    """顯示完整模擬結果"""
    metrics = compute_result_metrics(result)

    # ── 漏斗圖（人數流程） ──
    st.subheader("篩選流程")

    funnel_cols = st.columns(4)
    funnel_cols[0].metric("全體考生", f"{result.total_population:,}")
    funnel_cols[1].metric("通過檢定", f"{result.eligible_count:,}",
                          delta=f"-{result.total_population - result.eligible_count:,}",
                          delta_color="inverse")
    funnel_cols[2].metric("估計報名", f"{result.applicant_count:,}",
                          delta=f"-{result.eligible_count - result.applicant_count:,}" if result.eligible_count != result.applicant_count else "全部",
                          delta_color="inverse")
    funnel_cols[3].metric("最終通過", f"{result.final_passed_count:,}",
                          delta=f"-{result.applicant_count - result.final_passed_count:,}",
                          delta_color="inverse")

    # ── 各關篩選細節 ──
    if result.screening_details:
        st.subheader("各關篩選結果")
        details_df = pd.DataFrame(result.screening_details)
        # 欄位名稱轉中文
        col_rename = {"科目": "科目", "倍率": "倍率", "目標人數": "目標人數",
                      "篩選前": "篩選前人數", "篩選後": "篩選後人數", "cutoff": "Cutoff 級分", "備註": "備註"}
        for old, new in col_rename.items():
            if old in details_df.columns and old != new:
                details_df = details_df.rename(columns={old: new})

        # 替換科目代碼為中文（支援組合）
        if "科目" in details_df.columns:
            details_df["科目"] = details_df["科目"].map(format_screen_option)

        st.dataframe(details_df, use_container_width=True, hide_index=True)

    # ── 通過者統計 ──
    if result.final_passed_count > 0:
        st.subheader("通過者各科統計")
        passed = result.passed_df
        stat_cols = st.columns(len(DEFAULT_SUBJECTS))
        for i, (subj_key, subj_name) in enumerate(DEFAULT_SUBJECTS.items()):
            if subj_key in passed.columns:
                with stat_cols[i]:
                    st.metric(f"{subj_name}平均", round(passed[subj_key].mean(), 2))
                    st.caption(f"最高 {passed[subj_key].max()} / 最低 {passed[subj_key].min()}")

        # 圖表
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(plot_pass_fail_bar(result), use_container_width=True)
        with chart_col2:
            if "screening_score" in result.all_df.columns:
                st.plotly_chart(plot_score_distribution(result), use_container_width=True)

        with st.expander("查看通過者名單"):
            st.dataframe(result.passed_df, use_container_width=True)


# ═══════════════════════════════════════
# Tab 2: 單一策略模擬
# ═══════════════════════════════════════
with tab_single:
    st.header("單一策略模擬")

    if st.session_state.applicant_data is None:
        st.warning("請先在「資料上傳」頁面載入考生資料。")
    else:
        df = st.session_state.applicant_data

        # 顯示目前設定摘要
        thresh_desc = "、".join(
            f"{SUBJECT_NAMES[s]}{t}" for s, t in thresholds.items() if t != "不設"
        ) or "無"
        level_desc = " → ".join(
            f"{format_screen_option(l.subject)}×{l.multiplier}" for l in screening_levels
        )
        app_desc = (f"{application_count} 人" if application_count
                    else f"{application_rate*100:.1f}%" if application_rate
                    else "全部合格者")

        st.info(
            f"**名額** {quota} 人 | "
            f"**檢定** {thresh_desc} | "
            f"**篩選** {level_desc} | "
            f"**志願** {app_desc}"
        )

        if st.button("開始模擬", type="primary", key="btn_single_sim"):
            config = make_config("目前策略")
            result = run_simulation(df, config)
            st.session_state.single_result = result

        if "single_result" in st.session_state and st.session_state.single_result is not None:
            show_simulation_result(st.session_state.single_result)


# ═══════════════════════════════════════
# Tab 3: 多策略比較
# ═══════════════════════════════════════
with tab_compare:
    st.header("多策略比較")

    if st.session_state.applicant_data is None:
        st.warning("請先在「資料上傳」頁面載入考生資料。")
    else:
        df = st.session_state.applicant_data

        st.markdown("比較不同檢定門檻 + 篩選倍率組合的效果。每組策略可獨立設定。")

        num_strategies = st.selectbox("比較策略數量", [2, 3, 4], index=1, key="cmp_num_strategies")
        strategy_configs = []
        cols = st.columns(num_strategies)

        for i in range(num_strategies):
            with cols[i]:
                st.subheader(f"策略 {chr(65 + i)}")

                # 檢定
                st.markdown("**檢定門檻**")
                s_thresh = {}
                for subj_key, subj_name in SUBJECT_NAMES.items():
                    s_thresh[subj_key] = st.selectbox(
                        f"{subj_name}",
                        STANDARD_LEVELS,
                        index=0,
                        key=f"cmp_thresh_{i}_{subj_key}",
                    )

                # 篩選
                st.markdown("**篩選關卡**")
                s_num_levels = st.selectbox("關卡數", [1, 2, 3], index=1, key=f"cmp_num_levels_{i}")
                s_levels = []
                for j in range(s_num_levels):
                    sj = st.selectbox(
                        f"第{j+1}關科目",
                        SCREEN_OPTIONS,
                        index=min(j, len(SCREEN_OPTIONS)-1),
                        format_func=format_screen_option,
                        key=f"cmp_screen_subj_{i}_{j}",
                    )
                    sm = st.number_input(
                        f"第{j+1}關倍率",
                        min_value=1.0, max_value=20.0,
                        value=float(3 + j * 2),
                        step=0.5,
                        key=f"cmp_screen_mult_{i}_{j}",
                    )
                    s_levels.append(ScreeningLevel(subject=sj, multiplier=sm))

                # 上限排除（每個策略用不同 label 避免 expander 衝突）
                with st.expander(f"🔺 排除不可能報名者（策略 {chr(65+i)}）"):
                    s_upper = {}
                    for subj_key, subj_name in SUBJECT_NAMES.items():
                        s_upper[subj_key] = st.selectbox(
                            f"{subj_name} 上限",
                            ["不設"] + STANDARD_LEVELS[1:],
                            index=0,
                            key=f"cmp_upper_{i}_{subj_key}",
                        )

                strategy_configs.append(make_config(
                    f"策略 {chr(65 + i)}",
                    custom_thresholds=s_thresh,
                    custom_levels=s_levels,
                    custom_upper=s_upper,
                ))

        if st.button("開始比較", type="primary", key="btn_compare"):
            try:
                results = run_comparison(df, strategy_configs)
                st.session_state.comparison_results = results
            except Exception as e:
                st.error(f"模擬錯誤：{e}")

        if "comparison_results" in st.session_state and st.session_state.comparison_results:
            results = st.session_state.comparison_results

            st.subheader("策略比較總表")
            comparison_df = build_comparison_table(results)
            st.dataframe(comparison_df, use_container_width=True, hide_index=True)

            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.plotly_chart(plot_cutoff_comparison(results), use_container_width=True)
            with chart_col2:
                st.plotly_chart(plot_selected_count_comparison(results), use_container_width=True)

            st.plotly_chart(plot_subject_avg_comparison(results), use_container_width=True)


# ═══════════════════════════════════════
# Tab 4: 歷年篩選資料
# ═══════════════════════════════════════
with tab_history:
    st.header("淡江英文系歷年個人申請篩選資料")
    st.caption("校系代碼：014082")

    # 歷年資料表格
    hist_df = get_historical_table()
    st.dataframe(hist_df, use_container_width=True, hide_index=True)

    # 手動更新報名人數
    st.subheader("更新報名人數")
    st.caption("從甄選會篩選標準一覽表中取得報名人數後，在此輸入以提升模擬準確度")

    update_cols = st.columns(len(HISTORICAL_DATA))
    updated = False
    for i, (year, data) in enumerate(sorted(HISTORICAL_DATA.items())):
        with update_cols[i]:
            current_val = data["報名人數"] or 0
            new_val = st.number_input(
                f"{year}年",
                min_value=0,
                value=current_val,
                step=10,
                key=f"hist_app_{year}",
                help=f"招生名額: {data['招生名額']}",
            )
            if new_val > 0 and new_val != current_val:
                HISTORICAL_DATA[year]["報名人數"] = new_val
                updated = True

    if updated:
        st.success("已更新！志願申請率的預設估算值也會隨之調整。")

    # 通過人數趨勢
    st.subheader("通過篩選人數趨勢")
    passed_data = {
        y: d["通過人數"] for y, d in sorted(HISTORICAL_DATA.items()) if d["通過人數"]
    }
    if passed_data:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[str(y) for y in passed_data.keys()],
            y=list(passed_data.values()),
            text=list(passed_data.values()),
            textposition="outside",
            marker_color=["#4CAF50" if y >= 114 else "#2196F3" for y in passed_data.keys()],
        ))
        quotas = {y: HISTORICAL_DATA[y]["招生名額"] for y in passed_data.keys()}
        fig.add_trace(go.Scatter(
            x=[str(y) for y in quotas.keys()],
            y=list(quotas.values()),
            mode="lines+markers+text",
            name="招生名額",
            text=[str(v) for v in quotas.values()],
            textposition="top center",
            line=dict(color="red", dash="dash"),
        ))
        fig.update_layout(
            title="歷年通過篩選人數 vs 招生名額",
            xaxis_title="學年度",
            yaxis_title="人數",
            showlegend=True,
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

        avg_passed = get_avg_passed_count()
        st.info(f"平均通過篩選人數：**{avg_passed}** 人 / 平均招生名額：**{int(sum(quotas.values())/len(quotas))}** 人 → 平均約 **{avg_passed/int(sum(quotas.values())/len(quotas)):.1f}** 倍")

    st.markdown("*綠色 = 甄選會官方資料 / 藍色 = 交叉查榜*")

    # 已知篩選設定
    st.subheader("已知篩選設定")

    col_114, col_115 = st.columns(2)
    with col_114:
        st.markdown("**114年**")
        st.markdown("""
        | 科目 | 倍率 | 篩選級分 |
        |------|------|---------|
        | 英文 | ×6 | 8 級分 |
        | 國文 | ×3 | 10 級分 |

        > 有超額篩選、通過 171 人
        """)
    with col_115:
        st.markdown("**115年**")
        st.markdown("""
        | 關卡 | 科目 | 倍率 | 目標 |
        |------|------|------|------|
        | 第一關 | 英文 | ×6 | 300 |
        | 第二關 | 國文 | ×5 | 250 |
        | 第三關 | 國英相加 | ×3 | 150 |

        > 實際通過 **164 人**（超篩 14 人）
        > 前兩關未超額，僅第三關有篩選效果
        """)


# ═══════════════════════════════════════
# Tab 5: 結果下載
# ═══════════════════════════════════════
with tab_download:
    st.header("結果下載")
    has_results = False

    if "single_result" in st.session_state and st.session_state.single_result is not None:
        has_results = True
        result = st.session_state.single_result
        st.subheader("單一策略模擬結果")
        st.download_button("下載全部考生模擬結果 (CSV)",
                           result.all_df.to_csv(index=False).encode("utf-8-sig"),
                           "simulation_all.csv", "text/csv")
        st.download_button("下載通過者名單 (CSV)",
                           result.passed_df.to_csv(index=False).encode("utf-8-sig"),
                           "simulation_passed.csv", "text/csv")

    if "comparison_results" in st.session_state and st.session_state.comparison_results:
        has_results = True
        st.subheader("多策略比較結果")
        comparison_df = build_comparison_table(st.session_state.comparison_results)
        st.download_button("下載策略比較表 (CSV)",
                           comparison_df.to_csv(index=False).encode("utf-8-sig"),
                           "strategy_comparison.csv", "text/csv")
        for r in st.session_state.comparison_results:
            st.download_button(f"下載 {r.strategy_name} 通過者 (CSV)",
                               r.passed_df.to_csv(index=False).encode("utf-8-sig"),
                               f"passed_{r.strategy_name}.csv", "text/csv")

    if not has_results:
        st.info("尚未執行模擬，請先到「單一策略模擬」或「多策略比較」頁面進行模擬。")


# ── Footer ──
st.divider()
st.caption("淡江大學英文系 — 招生策略估算系統 | 僅供內部行政使用")
