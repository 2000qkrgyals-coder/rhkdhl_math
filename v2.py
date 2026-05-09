import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_multi_book_v5.db', check_same_thread=False)
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

# --- [2. 사이드바 관리] ---
with st.sidebar:
    st.title("🎓 Tutor Pro v5")
    
    # 학생 등록/삭제
    with st.expander("👤 학생 관리"):
        st_mode = st.radio("작업", ["등록", "삭제"])
        if st_mode == "등록":
            new_st = st.text_input("학생 이름")
            if st.button("학생 추가"):
                c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_st, json.dumps([])))
                conn.commit()
                st.rerun()
        else:
            all_st = pd.read_sql_query("SELECT id, name FROM students", conn)
            if not all_st.empty:
                del_name = st.selectbox("삭제할 학생", all_st['name'])
                if st.button("❌ 삭제"):
                    tid = all_st[all_st['name'] == del_name]['id'].values[0]
                    c.execute(f"DELETE FROM students WHERE id={tid}")
                    c.execute(f"DELETE FROM sessions WHERE student_id={tid}")
                    conn.commit()
                    st.rerun()

    students_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not students_df.empty:
        sel_student = st.selectbox("학생 선택", students_df['name'])
        s_info = students_df[students_df['name'] == sel_student].iloc[0]
        s_id = int(s_info['id'])
        s_books = json.loads(s_info['books']) if s_info['books'] else []
    else:
        st.stop()

# --- [3. 메인 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 입력", "📊 데이터 분석", "📅 설정", "📂 전체 로그"])

# --- TAB 1: 수업 입력 (다중 항목 지원) ---
with tab1:
    st.subheader(f"[{sel_student}] 수업 기록")
    
    if s_info['target_date']:
        d_day = (datetime.strptime(s_info['target_date'], "%Y-%m-%d") - datetime.now()).days
        if d_day >= 0: st.info(f"🚩 시험 D-{d_day}")

    # 1. 지난 숙제 체크 (이전 세션 데이터)
    last_data = pd.read_sql_query(f"SELECT next_hw, session_num FROM sessions WHERE student_id={s_id} ORDER BY id DESC LIMIT 1", conn)
    
    with st.expander("📌 지난 숙제 성취도 채점", expanded=True):
        if not last_data.empty:
            st.caption(f"이전 숙제: {last_data.iloc[0]['next_hw']}")
            c1, c2 = st.columns(2)
            total = c1.number_input("총 문항", min_value=0, step=1)
            done = c2.number_input("푼 문항", min_value=0, step=1)
            rate = int((done/total)*100) if total > 0 else 100
            st.write(f"성취도: **{rate}%**")
        else:
            rate = 100

    st.divider()

    # 2. 다중 진도/숙제 입력 (동적 세션 상태 이용)
    if 'prog_rows' not in st.session_state: st.session_state.prog_rows = 1
    if 'hw_rows' not in st.session_state: st.session_state.hw_rows = 1

    with st.form("multi_entry_form"):
        col1, col2 = st.columns(2)
        date = col1.date_input("수업 날짜", datetime.now())
        suggested_num = (last_data.iloc[0]['session_num'] + 1) if not last_data.empty else 1
        sess_num = col2.number_input("회차 선택", min_value=1, value=suggested_num)

        st.write("📖 **오늘 나간 진도**")
        prog_list = []
        for i in range(st.session_state.prog_rows):
            c1, c2 = st.columns([1, 2])
            b = c1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], key=f"pb_{i}")
            r = c2.text_input(f"범위 {i+1}", key=f"pr_{i}")
            if b and r: prog_list.append(f"{b}: {r}")

        st.write("📝 **다음 시간 숙제**")
        hw_list = []
        for i in range(st.session_state.hw_rows):
            c1, c2 = st.columns([1, 2])
            b = c1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], key=f"hb_{i}")
            r = c2.text_input(f"범위 {i+1}", key=f"hr_{i}")
            if b and r: hw_list.append(f"{b}: {r}")

        feedback = st.text_area("수업 피드백")

        if st.form_submit_button("💾 수업 저장"):
            c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (s_id, date.strftime("%Y-%m-%d"), sess_num, " | ".join(prog_list), rate, " | ".join(hw_list), feedback))
            conn.commit()
            st.success("저장 완료!")
            st.rerun()
    
    # 폼 외부에서 항목 개수 조절
    c1, c2 = st.columns(2)
    if c1.button("➕ 진도 항목 추가"): st.session_state.prog_rows += 1; st.rerun()
    if c2.button("➕ 숙제 항목 추가"): st.session_state.hw_rows += 1; st.rerun()

# --- TAB 2: 데이터 분석 (주별/월별) ---
with tab2:
    st.subheader("📊 학습 통계 분석")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id}", conn)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['Week'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)
        df['Month'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time)

        view = st.radio("보기 설정", ["회차별", "주별 평균", "월별 평균"], horizontal=True)
        if view == "회차별":
            fig = px.line(df, x='date', y='hw_result_rate', markers=True, title="성취도 흐름")
        else:
            period = 'Week' if view == "주별 평균" else 'Month'
            p_df = df.groupby(period)['hw_result_rate'].mean().reset_index()
            fig = px.bar(p_df, x=period, y='hw_result_rate', text_auto='.1f', title=f"{view} 성취도")
        
        fig.update_layout(yaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("데이터가 없습니다.")

# --- TAB 3: 설정 ---
with tab3:
    st.subheader("⚙️ 시험 및 교재 설정")
    new_t = st.date_input("시험 날짜 설정", value=datetime.strptime(s_info['target_date'], "%Y-%m-%d") if s_info['target_date'] else datetime.now())
    if st.button("날짜 저장"):
        c.execute("UPDATE students SET target_date=? WHERE id=?", (new_t.strftime("%Y-%m-%d"), s_id))
        conn.commit(); st.rerun()
    
    st.divider()
    new_book = st.text_input("새 교재 추가")
    if st.button("추가") and new_book:
        s_books.append(new_book)
        c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
        conn.commit(); st.rerun()
    
    for i, b in enumerate(s_books):
        cb1, cb2 = st.columns([4, 1])
        cb1.write(f"📚 {b}")
        if cb2.button("삭제", key=f"bdel_{i}"):
            s_books.pop(i); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
            conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    log_df = pd.read_sql_query(f"SELECT date, session_num, progress, hw_result_rate, next_hw, feedback FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    if not log_df.empty:
        log_df.columns = ['날짜', '회차', '진도', '성취도(%)', '숙제', '피드백']
        st.dataframe(log_df, use_container_width=True, hide_index=True)
