import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v8_7.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, target_date TEXT, books TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 student_id INTEGER, date TEXT, session_num INTEGER,
                 progress TEXT, hw_result_rate INTEGER, 
                 next_hw TEXT, feedback TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

def get_date_str(date_obj):
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f"{date_obj.month}월 {date_obj.day}일 ({days[date_obj.weekday()]})"

# --- [2. 사이드바] ---
with st.sidebar:
    st.title("📑 Tutor Management v8.7")
    
    with st.expander("👤 신규 학생 등록"):
        new_student = st.text_input("학생 이름 입력")
        if st.button("등록하기"):
            if new_student:
                c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_student, json.dumps([])))
                conn.commit()
                st.rerun()

    st_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not st_df.empty:
        sel_name = st.selectbox("관리할 학생 선택", st_df['name'])
        s_data = st_df[st_df['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        s_books = json.loads(s_data['books']) if s_data['books'] else []
        
        if st.button("❌ 선택된 학생 삭제"):
            c.execute(f"DELETE FROM students WHERE id={s_id}")
            c.execute(f"DELETE FROM sessions WHERE student_id={s_id}")
            conn.commit(); st.rerun()
    else:
        st.warning("먼저 학생을 등록해 주세요."); st.stop()

# --- [3. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

if 'edit_id' not in st.session_state: st.session_state.edit_id = None
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
if 'check_rows' not in st.session_state: st.session_state.check_rows = 1

# --- TAB 1: 수업 기록 및 수정 ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ {st.session_state.edit_session_num}회차 수정 모드")
        if st.button("수정 취소"): st.session_state.edit_id = None; st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록 및 채점")
    
    all_sessions = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    with st.expander("📥 지난 숙제 내역 불러오기", expanded=True):
        if not all_sessions.empty:
            hw_options = {f"{r['session_num']}회차 ({get_date_str(r['date'])})": r['next_hw'] for _, r in all_sessions.iterrows()}
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
        else: st.info("이전 기록 없음")

    st.write("### ✍️ 지난 숙제 채점")
    
    # 누적 문항수를 계산하기 위한 변수 초기화
    accumulated_total_q = 0
    accumulated_done_q = 0
    
    for i in range(st.session_state.check_rows):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        if f"cb_{i}" not in st.session_state: st.session_state[f"cb_{i}"] = s_books[0] if s_books else "미등록"
        if f"cr_{i}" not in st.session_state: st.session_state[f"cr_{i}"] = ""
        
        cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], key=f"cb_{i}")
        cr = c2.text_input(f"범위 {i+1}", key=f"cr_{i}")
        ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
        cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
        
        # 각 항목의 문항수를 전체 합계에 누적
        accumulated_total_q += ct
        accumulated_done_q += cd
    
    col_c1, col_c2 = st.columns(2)
    if col_c1.button("➕ 채점 칸 추가"): st.session_state.check_rows += 1; st.rerun()
    if col_c2.button("➖ 채점 칸 삭제") and st.session_state.check_rows > 1: st.session_state.check_rows -= 1; st.rerun()

    # 합산된 문항수로 최종 이행률 계산
    final_rate = int((accumulated_done_q / accumulated_total_q * 100)) if accumulated_total_q > 0 else 100
    st.info(f"💡 전체 숙제 합산 이행률: **{final_rate}%** (총 {accumulated_done_q}/{accumulated_total_q} 문항)")

    st.divider()

    with st.form("lesson_form"):
        col_d, col_n = st.columns(2)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_val = st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)
        date_input = col_d.date_input("날짜", d_val)
        sess_num = col_n.number_input("회차", value=int(n_val))

        st.write("📖 **오늘의 진도**")
        p_list = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            e_pb, e_pr = "", ""
            if st.session_state.edit_id and 'edit_progress' in st.session_state:
                items = st.session_state.edit_progress.split(" | ")
                if i < len(items) and ":" in items[i]: e_pb, e_pr = items[i].split(":", 1)
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(e_pb.strip()) if e_pb.strip() in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", value=e_pr.strip(), key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 **다음 숙제**")
        h_list = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            e_hb, e_hr = "", ""
            if st.session_state.edit_id and 'edit_next_hw' in st.session_state:
                items = st.session_state.edit_next_hw.split(" | ")
                if i < len(items) and ":" in items[i]: e_hb, e_hr = items[i].split(":", 1)
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(e_hb.strip()) if e_hb.strip() in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", value=e_hr.strip(), key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        feedback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""))
        
        if st.form_submit_button("💾 데이터 저장"):
            p_str, h_str = " | ".join(p_list), " | ".join(h_list)
            if st.session_state.edit_id:
                c.execute("UPDATE sessions SET date=?, session_num=?, progress=?, hw_result_rate=?, next_hw=?, feedback=? WHERE id=?",
                          (date_input.strftime("%Y-%m-%d"), sess_num, p_str, final_rate, h_str, feedback, st.session_state.edit_id))
                st.session_state.edit_id = None
            else:
                c.execute("INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) VALUES (?,?,?,?,?,?,?)",
                          (s_id, date_input.strftime("%Y-%m-%d"), sess_num, p_str, final_rate, h_str, feedback))
            conn.commit(); st.rerun()

    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    if col_b1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
    if col_b2.button("➖ 진도 삭제") and st.session_state.p_rows > 1: st.session_state.p_rows -= 1; st.rerun()
    if col_b3.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
    if col_b4.button("➖ 숙제 삭제") and st.session_state.h_rows > 1: st.session_state.h_rows -= 1; st.rerun()

# --- TAB 2: 데이터 분석 ---
with tab2:
    st.subheader("📊 학습 분석 리포트")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        mode = st.radio("분석 단위", ["회차별", "주별 평균", "월별 평균"], horizontal=True)
        if mode == "회차별":
            df['display_x'] = df['date'].apply(get_date_str)
            plot_df, y_col = df, 'hw_result_rate'
        elif mode == "주별 평균":
            df['week'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)
            plot_df = df.groupby('week')['hw_result_rate'].mean().reset_index()
            plot_df['display_x'] = plot_df['week'].dt.strftime('%m/%d 주차')
            y_col = 'hw_result_rate'
        else:
            df['month'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time)
            plot_df = df.groupby('month')['hw_result_rate'].mean().reset_index()
            plot_df['display_x'] = plot_df['month'].dt.strftime('%m월')
            y_col = 'hw_result_rate'
        fig = px.line(plot_df, x='display_x', y=y_col, markers=True)
        fig.update_layout(yaxis_range=[-5, 105])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("데이터 없음")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    nb = st.text_input("새 교재")
    if st.button("추가") and nb:
        s_books.append(nb); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()
    for i, b in enumerate(s_books):
        cb1, cb2 = st.columns([5,1])
        cb1.write(f"📖 {b}")
        if cb2.button("삭제", key=f"db_{i}"):
            s_books.pop(i); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 전체 히스토리")
    df_log = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    for _, row in df_log.iterrows():
        d_label = get_date_str(row['date'])
        c_m, c_e, c_d = st.columns([5, 1, 1])
        with c_m:
            with st.expander(f"📌 {row['session_num']}회차 | {d_label} | {row['hw_result_rate']}%"):
                st.write(f"**진도:** {row['progress']}"); st.write(f"**숙제:** {row['next_hw']}"); st.info(f"**피드백:** {row['feedback']}")
        with c_e:
            if st.button("📝 수정", key=f"ed_{row['id']}"):
                st.session_state.edit_id = row['id']; st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = row['session_num']; st.session_state.edit_progress = row['progress']
                st.session_state.edit_next_hw = row['next_hw']; st.session_state.edit_feedback = row['feedback']; st.rerun()
        with c_d:
            if st.button("🗑️ 삭제", key=f"dl_{row['id']}"):
                c.execute(f"DELETE FROM sessions WHERE id={row['id']}"); conn.commit(); st.rerun()
