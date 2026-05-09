import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_advanced_v4.db', check_same_thread=False)
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
    st.title("🎓 Tutor Advanced")
    
    with st.expander("👤 학생 관리"):
        mode = st.radio("작업", ["등록", "삭제"])
        if mode == "등록":
            new_st = st.text_input("학생 이름")
            if st.button("등록"):
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

# --- [3. 메인 탭 구성] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 입력", "📊 데이터 분석", "📅 설정", "📂 전체 로그"])

# --- TAB 1: 수업 입력 (회차 선택 기능 추가) ---
with tab1:
    st.subheader(f"[{sel_student}] 수업 기록")
    
    # D-Day 노출
    if s_info['target_date']:
        target = datetime.strptime(s_info['target_date'], "%Y-%m-%d")
        d_day = (target - datetime.now()).days
        if d_day >= 0: st.info(f"🚩 시험까지 **D-{d_day}**")

    # 지난 숙제 불러오기
    last_sess_data = pd.read_sql_query(f"SELECT next_hw, session_num FROM sessions WHERE student_id={s_id} ORDER BY id DESC LIMIT 1", conn)
    
    with st.expander("📌 숙제 성취도 체크", expanded=True):
        if not last_sess_data.empty:
            st.caption(f"이전 숙제: {last_sess_data.iloc[0]['next_hw']}")
            c1, c2 = st.columns(2)
            total = c1.number_input("총 문항", min_value=0, step=1)
            done = c2.number_input("푼 문항", min_value=0, step=1)
            calc_rate = int((done/total)*100) if total > 0 else 100
            st.write(f"성취도: **{calc_rate}%**")
        else:
            st.write("첫 기록입니다.")
            calc_rate = 100

    st.divider()

    with st.form("session_entry"):
        col1, col2 = st.columns(2)
        date = col1.date_input("날짜", datetime.now())
        
        # 회차 선택 기능: 자동 제안하되 수정 가능하게 함
        suggested_num = (last_sess_data.iloc[0]['session_num'] + 1) if not last_sess_data.empty else 1
        sess_num = col2.number_input("회차 선택", min_value=1, value=suggested_num)
        
        p_book = st.selectbox("진도 교재", s_books if s_books else ["미등록"])
        p_range = st.text_input("진도 범위")
        
        h_book = st.selectbox("숙제 교재", s_books if s_books else ["미등록"])
        h_range = st.text_input("숙제 범위")
        
        feedback = st.text_area("피드백")
        
        if st.form_submit_button("💾 저장"):
            c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (s_id, date.strftime("%Y-%m-%d"), sess_num, f"[{p_book}] {p_range}", calc_rate, f"[{h_book}] {h_range}", feedback))
            conn.commit()
            st.success("기록되었습니다!")
            st.rerun()

# --- TAB 2: 데이터 분석 (주별/월별 성취도) ---
with tab2:
    st.subheader(f"📊 {sel_student} 학습 데이터 분석")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id}", conn)
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 주별/월별 데이터 생성
        df['Week'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)
        df['Month'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time)

        analysis_mode = st.radio("분석 단위", ["전체 회차", "주별 평균", "월별 평균"], horizontal=True)

        if analysis_mode == "전체 회차":
            fig = px.line(df, x='date', y='hw_result_rate', title="회차별 성취도 추이", markers=True)
        elif analysis_mode == "주별 평균":
            week_df = df.groupby('Week')['hw_result_rate'].mean().reset_index()
            fig = px.bar(week_df, x='Week', y='hw_result_rate', title="주차별 평균 성취도", text_auto='.1f')
        else:
            month_df = df.groupby('Month')['hw_result_rate'].mean().reset_index()
            fig = px.bar(month_df, x='Month', y='hw_result_rate', title="월별 평균 성취도", text_auto='.1f')

        fig.update_layout(yaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)
        
        # 학습량 통계
        st.write("📈 **누적 통계**")
        c1, c2, c3 = st.columns(3)
        c1.metric("총 수업 횟수", f"{len(df)}회")
        c2.metric("최근 성취도", f"{df.iloc[-1]['hw_result_rate']}%")
        c3.metric("전체 평균", f"{round(df['hw_result_rate'].mean(), 1)}%")
    else:
        st.info("데이터가 없습니다.")

# --- TAB 3: 설정 ---
with tab3:
    st.subheader("⚙️ 시험 및 교재 설정")
    
    # 시험 날짜
    cur_t = s_info['target_date']
    new_t = st.date_input("시험 날짜", value=datetime.strptime(cur_t, "%Y-%m-%d") if cur_t else datetime.now())
    if st.button("시험 날짜 저장"):
        c.execute("UPDATE students SET target_date=? WHERE id=?", (new_t.strftime("%Y-%m-%d"), s_id))
        conn.commit(); st.rerun()

    st.divider()
    
    # 교재 관리
    st.write("📚 **교재 리스트**")
    new_book = st.text_input("새 교재 추가")
    if st.button("추가") and new_book:
        s_books.append(new_book)
        c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
        conn.commit(); st.rerun()
    
    for i, b in enumerate(s_books):
        col_b1, col_b2 = st.columns([4, 1])
        col_b1.write(f"- {b}")
        if col_b2.button("삭제", key=f"b_del_{i}"):
            s_books.pop(i)
            c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
            conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 수업 히스토리")
    log_df = pd.read_sql_query(f"SELECT date, session_num, progress, hw_result_rate, next_hw, feedback FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    if not log_df.empty:
        log_df.columns = ['날짜', '회차', '진도', '성취도(%)', '다음숙제', '피드백']
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("기록 없음")
