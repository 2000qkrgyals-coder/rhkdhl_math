import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import plotly.express as px
import json

# --- [1. 구글 시트 연결 설정] ---
# Streamlit Cloud의 Secrets에 등록된 URL을 통해 연결합니다.
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl="0s") # 실시간 반영을 위해 캐시(ttl)를 0으로 설정

def save_data(df, worksheet_name):
    conn.update(worksheet=worksheet_name, data=df)
    st.cache_data.clear()

# 초기 데이터 구조 생성 (시트가 비어있을 경우 대비)
def init_sheets():
    try:
        df_st = load_data("students")
    except:
        df_st = pd.DataFrame(columns=['id', 'name', 'target_date', 'books'])
        save_data(df_st, "students")
    
    try:
        df_se = load_data("sessions")
    except:
        df_se = pd.DataFrame(columns=['id', 'student_id', 'date', 'session_num', 'progress', 'hw_result_rate', 'next_hw', 'feedback'])
        save_data(df_se, "sessions")

init_sheets()

# --- [공통 함수] ---
def get_date_str(date_obj):
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f"{date_obj.month}월 {date_obj.day}일 ({days[date_obj.weekday()]})"

# --- [2. 사이드바] ---
with st.sidebar:
    st.title("📑 Tutor Pro Cloud v8.8")
    
    with st.expander("👤 신규 학생 등록"):
        new_name = st.text_input("학생 이름 입력")
        if st.button("등록하기") and new_name:
            df_st = load_data("students")
            new_id = int(df_st['id'].max() + 1) if not df_st.empty else 1
            new_row = pd.DataFrame([{'id': new_id, 'name': new_name, 'target_date': '', 'books': json.dumps([])}])
            df_st = pd.concat([df_st, new_row], ignore_index=True)
            save_data(df_st, "students")
            st.rerun()

    df_st = load_data("students")
    if not df_st.empty:
        sel_name = st.selectbox("관리할 학생 선택", df_st['name'])
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        s_books = json.loads(s_data['books']) if s_data['books'] else []
        
        if st.button("❌ 학생 기록 전체 삭제"):
            df_st = df_st[df_st['id'] != s_id]
            save_data(df_st, "students")
            df_se = load_data("sessions")
            df_se = df_se[df_se['student_id'] != s_id]
            save_data(df_se, "sessions")
            st.rerun()
    else:
        st.warning("학생을 등록해 주세요."); st.stop()

# --- [3. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

if 'edit_id' not in st.session_state: st.session_state.edit_id = None
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
if 'check_rows' not in st.session_state: st.session_state.check_rows = 1

# --- TAB 1: 기록 및 수정 (합산 채점 반영) ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ 수정 모드 활성화 중")
        if st.button("수정 취소"): st.session_state.edit_id = None; st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")
    
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)

    with st.expander("📥 지난 숙제 내역 불러오기", expanded=True):
        if not all_sessions.empty:
            hw_options = {f"{int(r['session_num'])}회차 ({get_date_str(r['date'])})": r['next_hw'] for _, r in all_sessions.iterrows()}
            selected_hw_key = st.selectbox("회차 선택", hw_options.keys())
            if st.button("채점 칸에 적용"):
                items = hw_options[selected_hw_key].split(" | ")
                st.session_state.check_rows = len(items)
                for idx, item in enumerate(items):
                    if ":" in item:
                        b, r = item.split(":", 1)
                        st.session_state[f"cb_{idx}"] = b.strip()
                        st.session_state[f"cr_{idx}"] = r.strip()
                st.rerun()

    st.write("### ✍️ 숙제 채점 (전체 합산)")
    acc_total, acc_done = 0, 0
    for i in range(st.session_state.check_rows):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        if f"cb_{i}" not in st.session_state: st.session_state[f"cb_{i}"] = s_books[0] if s_books else "미등록"
        if f"cr_{i}" not in st.session_state: st.session_state[f"cr_{i}"] = ""
        cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], key=f"cb_{i}")
        cr = c2.text_input(f"범위 {i+1}", key=f"cr_{i}")
        ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
        cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
        acc_total += ct; acc_done += cd
    
    if st.button("➕ 채점 칸 추가"): st.session_state.check_rows += 1; st.rerun()

    final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
    st.info(f"💡 합산 이행률: **{final_rate}%** ({acc_done}/{acc_total})")

    st.divider()

    with st.form("lesson_form"):
        col_d, col_n = st.columns(2)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_val = st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)
        date_in = col_d.date_input("날짜", d_val)
        sess_num = col_n.number_input("회차", value=int(n_val))

        p_list, h_list = [], []
        st.write("📖 진도"); 
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 다음 숙제"); 
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""))
        
        if st.form_submit_button("💾 구글 시트에 저장"):
            df_se = load_data("sessions")
            p_s, h_s = " | ".join(p_list), " | ".join(h_list)
            if st.session_state.edit_id:
                df_se.loc[df_se['id'] == st.session_state.edit_id, ['date', 'session_num', 'progress', 'hw_result_rate', 'next_hw', 'feedback']] = \
                    [date_in.strftime("%Y-%m-%d"), sess_num, p_s, final_rate, h_s, fback]
                st.session_state.edit_id = None
            else:
                new_id = int(df_se['id'].max() + 1) if not df_se.empty else 1
                new_row = pd.DataFrame([{'id': new_id, 'student_id': s_id, 'date': date_in.strftime("%Y-%m-%d"), 
                                         'session_num': sess_num, 'progress': p_s, 'hw_result_rate': final_rate, 
                                         'next_hw': h_s, 'feedback': fback}])
                df_se = pd.concat([df_se, new_row], ignore_index=True)
            save_data(df_se, "sessions")
            st.rerun()

# --- TAB 2, 3, 4 (핵심 로직 유지) ---
with tab2:
    st.subheader("📊 학습 분석")
    df_ana = load_data("sessions")
    df_ana = df_ana[df_ana['student_id'] == s_id].sort_values(by='date')
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        mode = st.radio("단위", ["회차별", "주별", "월별"], horizontal=True)
        if mode == "회차별":
            df_ana['x'] = df_ana['date'].apply(get_date_str)
            plot_df = df_ana
        elif mode == "주별":
            df_ana['w'] = df_ana['date'].dt.to_period('W').apply(lambda r: r.start_time)
            plot_df = df_ana.groupby('w')['hw_result_rate'].mean().reset_index()
            plot_df['x'] = plot_df['w'].dt.strftime('%m/%d 주')
        else:
            df_ana['m'] = df_ana['date'].dt.to_period('M').apply(lambda r: r.start_time)
            plot_df = df_ana.groupby('m')['hw_result_rate'].mean().reset_index()
            plot_df['x'] = plot_df['m'].dt.strftime('%m월')
        st.plotly_chart(px.line(plot_df, x='x', y='hw_result_rate', markers=True).update_layout(yaxis_range=[-5, 105]))

with tab3:
    st.subheader("📚 교재 관리")
    nb = st.text_input("새 교재")
    if st.button("추가") and nb:
        s_books.append(nb); df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books)
        save_data(df_st, "students"); st.rerun()

with tab4:
    st.subheader("📂 전체 로그")
    df_log = load_data("sessions")
    df_log = df_log[df_log['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    for _, row in df_log.iterrows():
        c_m, c_e, c_d = st.columns([5, 1, 1])
        with c_m:
            with st.expander(f"📌 {int(row['session_num'])}회차 | {get_date_str(row['date'])} | {row['hw_result_rate']}%"):
                st.write(f"진도: {row['progress']}"); st.write(f"숙제: {row['next_hw']}")
        with c_e:
            if st.button("📝", key=f"e_{row['id']}"):
                st.session_state.edit_id = row['id']; st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = int(row['session_num']); st.session_state.edit_progress = row['progress']
                st.session_state.edit_next_hw = row['next_hw']; st.session_state.edit_feedback = row['feedback']; st.rerun()
        with c_d:
            if st.button("🗑️", key=f"d_{row['id']}"):
                df_log = df_log[df_log['id'] != row['id']]
                save_data(df_log, "sessions"); st.rerun()
