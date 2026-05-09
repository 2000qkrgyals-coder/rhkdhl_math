import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_final_v3.db', check_same_thread=False)
    c = conn.cursor()
    # 학생 테이블: 목표일(D-Day)은 초기에는 NULL 가능
    c.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, target_date TEXT, books TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 student_id INTEGER, date TEXT, session_num INTEGER,
                 progress TEXT, hw_result_rate INTEGER, 
                 next_hw TEXT, feedback TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- [2. 사이드바: 학생 선택 및 기본 관리] ---
with st.sidebar:
    st.title("🎓 Tutor Management")
    
    # 학생 등록 및 삭제 (기본 관리)
    with st.expander("👤 학생 기본 관리"):
        mode = st.radio("작업", ["학생 등록", "학생 삭제"])
        if mode == "학생 등록":
            new_st = st.text_input("새 학생 이름")
            if st.button("등록"):
                c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_st, json.dumps([])))
                conn.commit()
                st.rerun()
        else:
            all_st = pd.read_sql_query("SELECT id, name FROM students", conn)
            if not all_st.empty:
                del_name = st.selectbox("삭제할 학생", all_st['name'])
                if st.button("❌ 선택 학생 삭제"):
                    target_id = all_st[all_st['name'] == del_name]['id'].values[0]
                    c.execute(f"DELETE FROM students WHERE id={target_id}")
                    c.execute(f"DELETE FROM sessions WHERE student_id={target_id}")
                    conn.commit()
                    st.rerun()

    # 현재 작업 학생 선택
    students_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not students_df.empty:
        sel_student = st.selectbox("관리 학생 선택", students_df['name'])
        s_info = students_df[students_df['name'] == sel_student].iloc[0]
        s_id = int(s_info['id'])
        s_books = json.loads(s_info['books']) if s_info['books'] else []
    else:
        st.stop()

# --- [3. 메인 화면 탭 구성] ---
# 요청하신 대로 '📅 시험/교재 설정' 탭을 별도로 분리했습니다.
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 입력", "📊 분석", "📅 시험/교재 설정", "📂 히스토리"])

# --- TAB 1: 수업 입력 ---
with tab1:
    st.subheader(f"[{sel_student}] 수업 기록")
    
    # D-Day 표시 (설정 탭에서 날짜를 입력했을 때만 상단에 작게 표시)
    if s_info['target_date']:
        target = datetime.strptime(s_info['target_date'], "%Y-%m-%d")
        d_day = (target - datetime.now()).days
        if d_day >= 0:
            st.caption(f"🚩 시험까지 **D-{d_day}**일 남았습니다.")

    # 1. 지난 숙제 자동 불러오기 및 성취도 계산
    last_session = pd.read_sql_query(f"SELECT next_hw, session_num FROM sessions WHERE student_id={s_id} ORDER BY id DESC LIMIT 1", conn)
    
    with st.expander("📌 지난 숙제 채점 및 이행도", expanded=True):
        if not last_session.empty:
            st.info(f"**지난 숙제:** {last_session.iloc[0]['next_hw']}")
            c1, c2 = st.columns(2)
            total = c1.number_input("총 문항 수", min_value=0, step=1, key="total_q")
            done = c2.number_input("푼 문항 수", min_value=0, step=1, key="done_q")
            
            if total > 0:
                calc_rate = int((done / total) * 100)
                st.write(f"📊 숙제 이행률: **{calc_rate}%**")
            else:
                calc_rate = 100
                st.write("✅ 숙제 없음 (성취도 100% 처리)")
        else:
            st.write("첫 수업 기록입니다.")
            calc_rate = 100

    st.divider()

    # 2. 오늘 수업 입력
    with st.form("session_entry"):
        col1, col2 = st.columns(2)
        date = col1.date_input("수업 날짜", datetime.now())
        sess_num = (last_session.iloc[0]['session_num'] + 1) if not last_session.empty else 1
        col2.write(f"**현재 회차: {sess_num}회차**")
        
        st.write("📖 **오늘의 진도**")
        p_book = st.selectbox("교재 선택", s_books if s_books else ["설정에서 교재를 먼저 등록하세요"], key="p_book")
        p_range = st.text_input("진도 범위", placeholder="예: p.10 ~ p.20")
        
        st.write("📝 **다음 숙제**")
        h_book = st.selectbox("교재 선택", s_books if s_books else ["설정에서 교재를 먼저 등록하세요"], key="h_book")
        h_range = st.text_input("숙제 범위", placeholder="예: 단원 종합문제 1~15번")
        
        feedback = st.text_area("피드백/특이사항")
        
        if st.form_submit_button("💾 수업 저장"):
            prog_str = f"[{p_book}] {p_range}"
            next_str = f"[{h_book}] {h_range}"
            c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (s_id, date.strftime("%Y-%m-%d"), sess_num, prog_str, calc_rate, next_str, feedback))
            conn.commit()
            st.success("기록 완료!")
            st.rerun()

# --- TAB 2: 분석 ---
with tab2:
    st.subheader(f"📈 {sel_student} 성취도 리포트")
    df = pd.read_sql_query(f"SELECT date, hw_result_rate FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        fig = px.line(df, x='date', y='hw_result_rate', title='숙제 이행도 변화', markers=True)
        fig.update_layout(yaxis_range=[-5, 105])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("기록이 아직 없습니다.")

# --- TAB 3: 시험/교재 설정 (요청하신 기능) ---
with tab3:
    st.subheader("⚙️ 학생별 상세 설정")
    
    # 1. 시험 D-Day 설정
    st.write("📅 **시험 일정 관리**")
    current_target = s_info['target_date'] if s_info['target_date'] else None
    new_target = st.date_input("시험 날짜 설정", value=datetime.strptime(current_target, "%Y-%m-%d") if current_target else datetime.now())
    if st.button("시험 날짜 업데이트"):
        c.execute("UPDATE students SET target_date=? WHERE id=?", (new_target.strftime("%Y-%m-%d"), s_id))
        conn.commit()
        st.success("시험 날짜가 저장되었습니다. 이제 수업 입력 탭에 D-Day가 나타납니다.")
        st.rerun()

    st.divider()

    # 2. 교재 관리
    st.write("📚 **교재 리스트 관리**")
    col_in, col_btn = st.columns([3, 1])
    add_book = col_in.text_input("새 교재 이름 입력")
    if col_btn.button("추가") and add_book:
        s_books.append(add_book)
        c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
        conn.commit()
        st.rerun()
    
    if s_books:
        st.write("현재 등록된 교재:")
        for i, b in enumerate(s_books):
            c1, c2 = st.columns([4, 1])
            c1.write(f"- {b}")
            if c2.button("삭제", key=f"del_{i}"):
                s_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
                conn.commit()
                st.rerun()

# --- TAB 4: 히스토리 ---
with tab4:
    st.subheader("📂 수업 히스토리")
    history = pd.read_sql_query(f"SELECT date, session_num, progress, hw_result_rate, next_hw, feedback FROM sessions WHERE student_id={s_id} ORDER BY id DESC", conn)
    if not history.empty:
        history.columns = ['날짜', '회차', '진도', '이행률(%)', '내준 숙제', '피드백']
        st.dataframe(history, use_container_width=True, hide_index=True)
    else:
        st.info("기록 없음")
