import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v8.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, target_date TEXT, books TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 student_id INTEGER, date TEXT, session_num INTEGER,
                 progress TEXT, hw_result_rate INTEGER, 
                 next_hw TEXT, feedback TEXT, hw_detail_json TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# 요일 변환 함수
def get_date_str(date_obj):
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f"{date_obj.month}월 {date_obj.day}일 ({days[date_obj.weekday()]})"

# --- [2. 사이드바] ---
with st.sidebar:
    st.title("📑 Tutor Management v8")
    st_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not st_df.empty:
        sel_name = st.selectbox("학생 선택", st_df['name'])
        s_data = st_df[st_df['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        s_books = json.loads(s_data['books']) if s_data['books'] else []
    else:
        st.stop()
    
    st.divider()
    if st.button("❌ 학생 삭제"):
        c.execute(f"DELETE FROM students WHERE id={s_id}")
        c.execute(f"DELETE FROM sessions WHERE student_id={s_id}")
        conn.commit(); st.rerun()

# --- [3. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록", "📊 데이터 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 수업 기록 ---
with tab1:
    st.subheader(f"[{sel_name}] 수업 기록")
    
    # 지난 회차 숙제 데이터 불러오기
    last_sess = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC LIMIT 1", conn)
    parsed_prev_hw = []
    if not last_sess.empty and last_sess.iloc[0]['next_hw']:
        items = last_sess.iloc[0]['next_hw'].split(" | ")
        for it in items:
            if ":" in it:
                b, r = it.split(":", 1)
                parsed_prev_hw.append({"book": b.strip(), "range": r.strip()})

    # 숙제 성취도 채점 섹션
    st.write("### ✍️ 지난 숙제 채점")
    if 'check_rows' not in st.session_state: st.session_state.check_rows = max(1, len(parsed_prev_hw))
    
    hw_scores = []
    total_q_sum = 0
    done_q_sum = 0

    for i in range(st.session_state.check_rows):
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            # 지난 기록에서 교재/범위 자동 로드
            def_b = parsed_prev_hw[i]['book'] if i < len(parsed_prev_hw) else (s_books[0] if s_books else "")
            def_r = parsed_prev_hw[i]['range'] if i < len(parsed_prev_hw) else ""
            
            check_b = c1.selectbox(f"채점 교재 {i+1}", s_books, index=s_books.index(def_b) if def_b in s_books else 0, key=f"cb_{i}")
            check_r = c2.text_input(f"숙제 범위 {i+1}", value=def_r, key=f"cr_{i}")
            q_total = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
            q_done = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
            
            total_q_sum += q_total
            done_q_sum += q_done
    
    col_btn1, col_btn2 = st.columns(2)
    if col_btn1.button("➕ 채점 항목 추가"): st.session_state.check_rows += 1; st.rerun()
    if col_btn2.button("➖ 채점 항목 삭제") and st.session_state.check_rows > 1: st.session_state.check_rows -= 1; st.rerun()

    final_rate = int((done_q_sum / total_q_sum * 100)) if total_q_sum > 0 else 100
    st.info(f"💡 전체 숙제 이행률: **{final_rate}%** ({done_q_sum}/{total_q_sum})")

    st.divider()

    # 오늘 수업 내용 입력
    with st.form("class_form"):
        col_date, col_num = st.columns(2)
        date = col_date.date_input("날짜", datetime.now())
        s_num = col_num.number_input("회차", value=(last_sess.iloc[0]['session_num']+1 if not last_sess.empty else 1))

        st.write("📖 **오늘의 진도**")
        if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
        p_res = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", key=f"pr_{i}")
            if pb and pr: p_res.append(f"{pb}: {pr}")

        st.write("📝 **다음 숙제**")
        if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
        h_res = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", key=f"hr_{i}")
            if hb and hr: h_res.append(f"{hb}: {hr}")

        feedback = st.text_area("피드백")

        if st.form_submit_button("💾 수업 기록 저장"):
            c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (s_id, date.strftime("%Y-%m-%d"), s_num, " | ".join(p_res), final_rate, " | ".join(h_res), feedback))
            conn.commit(); st.rerun()

    c_p1, c_p2, c_h1, c_h2 = st.columns(4)
    if c_p1.button("➕ 진도 칸 추가"): st.session_state.p_rows += 1; st.rerun()
    if c_p2.button("➖ 진도 칸 삭제"): st.session_state.p_rows -= 1; st.rerun()
    if c_h1.button("➕ 숙제 칸 추가"): st.session_state.h_rows += 1; st.rerun()
    if c_h2.button("➖ 숙제 칸 삭제"): st.session_state.h_rows -= 1; st.rerun()

# --- TAB 2: 데이터 분석 ---
with tab2:
    st.subheader("📊 학습 분석 리포트")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        df['dt_obj'] = pd.to_datetime(df['date'])
        df['display_date'] = df['dt_obj'].apply(get_date_str)
        
        fig = px.line(df, x='display_date', y='hw_result_rate', markers=True, title="회차별 숙제 이행률")
        fig.update_layout(yaxis_range=[0, 110], xaxis_title="날짜(요일)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("데이터가 없습니다.")

# --- TAB 3: 교재 관리 (요청하신 기능) ---
with tab3:
    st.subheader(f"📚 {sel_name}의 교재 목록")
    new_b = st.text_input("새 교재 이름")
    if st.button("교재 추가") and new_b:
        s_books.append(new_b)
        c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
        conn.commit(); st.rerun()
    
    st.divider()
    for i, b in enumerate(s_books):
        col_b1, col_b2 = st.columns([5, 1])
        col_b1.write(f"📖 {b}")
        if col_b2.button("삭제", key=f"del_b_{i}"):
            s_books.pop(i)
            c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
            conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 전체 수업 히스토리")
    df_log = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    for _, row in df_log.iterrows():
        date_label = get_date_str(datetime.strptime(row['date'], "%Y-%m-%d"))
        with st.expander(f"📌 {row['session_num']}회차 | {date_label} | 성취도 {row['hw_result_rate']}%"):
            st.write(f"**진도:** {row['progress']}")
            st.write(f"**숙제:** {row['next_hw']}")
            st.info(f"**피드백:** {row['feedback']}")
