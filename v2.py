import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화 및 관리] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v2.db', check_same_thread=False)
    c = conn.cursor()
    # 학생: 이름, 목표일, 교재리스트(JSON)
    c.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, target_date TEXT, books TEXT)')
    # 수업: 지난숙제이행도 포함
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 student_id INTEGER, date TEXT, session_num INTEGER,
                 progress TEXT, hw_result_rate INTEGER, 
                 next_hw TEXT, feedback TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- [2. 사이드바: 학생 및 교재 관리] ---
with st.sidebar:
    st.title("🎓 과외 관리 Pro v2")
    
    # 1. 학생 등록/삭제
    with st.expander("👤 학생 및 교재 설정"):
        mode = st.radio("작업 선택", ["등록", "수정/삭제"])
        if mode == "등록":
            new_name = st.text_input("학생 이름")
            t_date = st.date_input("시험 날짜", datetime.now())
            if st.button("신규 학생 등록"):
                c.execute("INSERT INTO students (name, target_date, books) VALUES (?, ?, ?)", 
                          (new_name, t_date.strftime("%Y-%m-%d"), json.dumps([])))
                conn.commit()
                st.rerun()
        else:
            st.caption("학생 삭제 시 모든 기록이 삭제됩니다.")
            all_st = pd.read_sql_query("SELECT id, name FROM students", conn)
            if not all_st.empty:
                del_target = st.selectbox("대상 학생", all_st['name'])
                target_id = all_st[all_st['name'] == del_target]['id'].values[0]
                
                # 교재 관리
                curr_books = json.loads(pd.read_sql_query(f"SELECT books FROM students WHERE id={target_id}", conn).iloc[0]['books'])
                new_book = st.text_input("새 교재 추가")
                if st.button("교재 추가"):
                    curr_books.append(new_book)
                    c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(curr_books), int(target_id)))
                    conn.commit()
                    st.rerun()
                
                st.write(f"현재 교재: {', '.join(curr_books) if curr_books else '없음'}")
                if st.button("❌ 학생 기록 전체 삭제", type="secondary"):
                    c.execute(f"DELETE FROM students WHERE id={target_id}")
                    c.execute(f"DELETE FROM sessions WHERE student_id={target_id}")
                    conn.commit()
                    st.rerun()

    # 학생 선택
    students = pd.read_sql_query("SELECT * FROM students", conn)
    if not students.empty:
        sel_student = st.selectbox("관리할 학생 선택", students['name'])
        s_info = students[students['name'] == sel_student].iloc[0]
        s_id = int(s_info['id'])
        s_books = json.loads(s_info['books'])
        
        target = datetime.strptime(s_info['target_date'], "%Y-%m-%d")
        d_day = (target - datetime.now()).days
        st.metric("📅 시험 D-Day", f"D-{d_day}" if d_day >= 0 else f"D+{abs(d_day)}")
    else:
        st.warning("먼저 학생을 등록해주세요.")
        st.stop()

# --- [3. 메인 기능] ---
tab1, tab2, tab3 = st.tabs(["📝 수업 입력", "📊 성취도 그래프", "📂 히스토리"])

with tab1:
    st.subheader(f"[{sel_student}] 수업 기록")
    
    # [기능] 지난 숙제 내역 불러오기
    last_session = pd.read_sql_query(f"SELECT next_hw, session_num FROM sessions WHERE student_id={s_id} ORDER BY id DESC LIMIT 1", conn)
    
    with st.expander("📌 지난 시간 숙제 확인", expanded=True):
        if not last_session.empty:
            prev_hw = last_session.iloc[0]['next_hw']
            st.info(f"**{last_session.iloc[0]['session_num']}회차 숙제:**\n{prev_hw}")
            
            st.write("✏️ **숙제 성취도 입력**")
            col_a, col_b = st.columns(2)
            total_q = col_a.number_input("전체 문항 수", min_value=0, value=0)
            solved_q = col_b.number_input("푼 문항 수", min_value=0, value=0)
            
            if total_q > 0:
                calc_rate = int((solved_q / total_q) * 100)
                st.write(f"자동 계산된 성취도: **{calc_rate}%**")
            else:
                calc_rate = 100 # 숙제가 없었으면 100%
                st.write("지정된 숙제가 없으므로 **100%**로 기록됩니다.")
        else:
            st.write("첫 수업입니다.")
            calc_rate = 100

    st.divider()

    # 오늘 수업 내용 입력
    with st.form("session_input"):
        col1, col2 = st.columns(2)
        date = col1.date_input("날짜", datetime.now())
        
        # 회차 자동 계산
        current_sess_num = (last_session.iloc[0]['session_num'] + 1) if not last_session.empty else 1
        st.write(f"**현재 회차: {current_sess_num}회차**")
        
        st.write("📖 **오늘 나간 진도**")
        p_book = st.selectbox("교재 선택 (진도)", s_books if s_books else ["등록된 교재 없음"])
        p_detail = st.text_input("상세 범위 (예: p.10~25)")
        progress_str = f"[{p_book}] {p_detail}"

        st.write("📝 **다음 시간 숙제**")
        h_book = st.selectbox("교재 선택 (숙제)", s_books if s_books else ["등록된 교재 없음"])
        h_detail = st.text_input("상세 범위 (예: 연습문제 1~20번)")
        next_hw_str = f"[{h_book}] {h_detail}"
        
        feedback = st.text_area("학부모 피드백")

        if st.form_submit_button("기록 저장하기"):
            c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                      (s_id, date.strftime("%Y-%m-%d"), current_sess_num, progress_str, calc_rate, next_hw_str, feedback))
            conn.commit()
            st.success("기록이 완료되었습니다!")
            st.rerun()

with tab2:
    st.subheader("📊 학습 성취도 분석")
    df = pd.read_sql_query(f"SELECT date, hw_result_rate FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        fig = px.line(df, x='date', y='hw_result_rate', title='숙제 이행률 추이', markers=True)
        fig.update_layout(yaxis_range=[0, 105])
        st.plotly_chart(fig, use_container_width=True)
        st.metric("평균 성취도", f"{round(df['hw_result_rate'].mean(), 1)}%")
    else:
        st.info("기록이 없습니다.")

with tab3:
    st.subheader("📂 전체 수업 로그")
    history = pd.read_sql_query(f"SELECT date, session_num, progress, hw_result_rate, next_hw, feedback FROM sessions WHERE student_id={s_id} ORDER BY id DESC", conn)
    if not history.empty:
        history.columns = ['날짜', '회차', '진도', '숙제이행도(%)', '내준숙제', '피드백']
        st.dataframe(history, use_container_width=True, hide_index=True)
    else:
        st.info("기록이 없습니다.")
