import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_final_v7.db', check_same_thread=False)
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

# 요일 한글 변환 함수
def get_korean_weekday(date_str):
    days = ['월', '화', '수', '목', '금', '토', '일']
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}월 {dt.day}일 ({days[dt.weekday()]})"

# --- [2. 사이드바 관리] ---
with st.sidebar:
    st.title("🚀 Tutor Management v7")
    
    students_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not students_df.empty:
        sel_student = st.selectbox("학생 선택", students_df['name'])
        s_info = students_df[students_df['name'] == sel_student].iloc[0]
        s_id = int(s_info['id'])
        s_books = json.loads(s_info['books']) if s_info['books'] else []
    
    st.divider()
    with st.expander("👤 학생/교재 추가 및 삭제"):
        new_st = st.text_input("신규 학생 이름")
        if st.button("학생 등록"):
            c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_st, json.dumps([])))
            conn.commit(); st.rerun()
        
        if not students_df.empty:
            if st.button("❌ 현재 학생 삭제", type="secondary"):
                c.execute(f"DELETE FROM students WHERE id={s_id}")
                c.execute(f"DELETE FROM sessions WHERE student_id={s_id}")
                conn.commit(); st.rerun()

# --- [3. 메인 화면] ---
if not students_df.empty:
    tab1, tab2, tab3 = st.tabs(["📝 수업 기록/수정", "📊 데이터 분석", "⚙️ 설정"])

    # --- TAB 1: 수업 기록/수정 ---
    with tab1:
        st.subheader(f"[{sel_student}] 수업 관리")
        
        # 지난 세션 데이터 미리 가져오기
        last_sess = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC LIMIT 1", conn)
        
        # 지난 숙제 파싱 (교재와 범위를 분리)
        parsed_prev_hw = []
        if not last_sess.empty and last_sess.iloc[0]['next_hw']:
            hw_items = last_sess.iloc[0]['next_hw'].split(" | ")
            for item in hw_items:
                if ":" in item:
                    b, r = item.split(":", 1)
                    parsed_prev_hw.append({"book": b.strip(), "range": r.strip()})

        # 항목 개수 세션 상태 초기화
        if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
        # 숙제 항목 개수는 지난 숙제 개수에 맞춤
        if 'h_rows' not in st.session_state: st.session_state.h_rows = max(1, len(parsed_prev_hw))

        # 숙제 성취도 입력창
        with st.expander("📌 지난 숙제 성취도 채점", expanded=True):
            if parsed_prev_hw:
                st.caption(f"이전 숙제 내역: {last_sess.iloc[0]['next_hw']}")
            c1, c2 = st.columns(2)
            total = c1.number_input("총 문항", min_value=0, step=1)
            done = c2.number_input("푼 문항", min_value=0, step=1)
            rate = int((done/total)*100) if total > 0 else 100
            st.write(f"계산된 성취도: **{rate}%**")

        st.divider()

        with st.form("session_form"):
            col1, col2 = st.columns(2)
            date = col1.date_input("수업 날짜", datetime.now())
            suggested_num = (last_sess.iloc[0]['session_num'] + 1) if not last_sess.empty else 1
            sess_num = col2.number_input("회차", min_value=1, value=suggested_num)

            st.write("📖 **오늘의 진도**")
            p_list = []
            for i in range(st.session_state.p_rows):
                c1, c2 = st.columns([2, 3])
                b = c1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], key=f"p_b_{i}")
                r = c2.text_input(f"진도 범위 {i+1}", key=f"p_r_{i}")
                if b and r: p_list.append(f"{b}: {r}")

            st.write("📝 **다음 숙제 (지난 숙제가 자동으로 입력됩니다)**")
            h_list = []
            for i in range(st.session_state.h_rows):
                c1, c2 = st.columns([2, 3])
                # 지난 숙제 데이터가 있으면 기본값으로 넣어줌
                default_book = parsed_prev_hw[i]['book'] if i < len(parsed_prev_hw) else (s_books[0] if s_books else "미등록")
                default_range = parsed_prev_hw[i]['range'] if i < len(parsed_prev_hw) else ""
                
                # 교재 선택 (인덱스 매칭)
                b_idx = s_books.index(default_book) if default_book in s_books else 0
                book = c1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], index=b_idx, key=f"h_b_{i}")
                rng = c2.text_input(f"숙제 범위 {i+1}", value=default_range, key=f"h_r_{i}")
                if book and rng: h_list.append(f"{book}: {rng}")

            feedback = st.text_area("피드백")

            if st.form_submit_button("💾 수업 저장하기"):
                c.execute("""INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (s_id, date.strftime("%Y-%m-%d"), sess_num, " | ".join(p_list), rate, " | ".join(h_list), feedback))
                conn.commit(); st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
        if c2.button("➖ 진도 제거") and st.session_state.p_rows > 1: st.session_state.p_rows -= 1; st.rerun()
        if c3.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
        if c4.button("➖ 숙제 제거") and st.session_state.h_rows > 1: st.session_state.h_rows -= 1; st.rerun()

    # --- TAB 2: 데이터 분석 ---
    with tab2:
        st.subheader(f"📊 {sel_student} 학습 분석")
        df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num", conn)
        if not df.empty:
            # 날짜 요일 형식 변환
            df['display_date'] = df['date'].apply(get_korean_weekday)
            
            fig = px.line(df, x='display_date', y='hw_result_rate', markers=True, title="회차별 성취도")
            fig.update_layout(yaxis_range=[-5, 105], xaxis_title="날짜(요일)")
            st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.write("📂 **상세 수업 히스토리**")
            for _, row in df.sort_values('session_num', ascending=False).iterrows():
                with st.expander(f"📌 {row['session_num']}회차 | {get_korean_weekday(row['date'])} | {row['hw_result_rate']}%"):
                    c_a, c_b = st.columns(2)
                    with c_a:
                        st.write("**📖 진도**")
                        for p in row['progress'].split(" | "): st.caption(p)
                    with c_b:
                        st.write("**📝 숙제**")
                        for h in row['next_hw'].split(" | "): st.caption(h)
                    st.write("**💬 피드백**")
                    st.info(row['feedback'] if row['feedback'] else "기록 없음")
        else:
            st.info("데이터가 없습니다.")

    # --- TAB 3: 설정 ---
    with tab3:
        st.subheader("⚙️ 설정 및 교재 관리")
        # 교재 추가/삭제 기능
        new_book = st.text_input("교재 추가")
        if st.button("추가") and new_book:
            s_books.append(new_book)
            c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
            conn.commit(); st.rerun()
        
        st.write("현재 교재 목록:")
        for i, b in enumerate(s_books):
            col_b1, col_b2 = st.columns([4, 1])
            col_b1.write(f"- {b}")
            if col_b2.button("삭제", key=f"book_del_{i}"):
                s_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
                conn.commit(); st.rerun()
