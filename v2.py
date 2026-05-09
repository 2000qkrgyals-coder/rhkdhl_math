import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v8_1.db', check_same_thread=False)
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
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f"{date_obj.month}월 {date_obj.day}일 ({days[date_obj.weekday()]})"

# --- [2. 사이드바: 학생 등록 및 선택] ---
with st.sidebar:
    st.title("📑 Tutor Management v8.1")
    
    # 학생 등록 섹션 (에어컨이나 빈 화면 방지용)
    with st.expander("👤 신규 학생 등록", expanded=True):
        new_name = st.text_input("이름 입력")
        if st.button("학생 추가"):
            if new_name:
                c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_name, json.dumps([])))
                conn.commit()
                st.success(f"{new_name} 등록 완료!")
                st.rerun()
            else:
                st.error("이름을 입력하세요.")

    st.divider()
    
    # 등록된 학생 선택
    st_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not st_df.empty:
        sel_name = st.selectbox("학생 선택", st_df['name'])
        s_data = st_df[st_df['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        s_books = json.loads(s_data['books']) if s_data['books'] else []
        
        if st.button("❌ 현재 학생 삭제"):
            c.execute(f"DELETE FROM students WHERE id={s_id}")
            c.execute(f"DELETE FROM sessions WHERE student_id={s_id}")
            conn.commit()
            st.rerun()
    else:
        st.warning("먼저 학생을 등록해 주세요!")
        st.stop() # 학생이 없으면 더 이상 진행하지 않음 (이제 등록 창은 보임)

# --- [3. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록", "📊 데이터 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 수업 기록 ---
with tab1:
    st.subheader(f"[{sel_name}] 수업 기록")
    
    # 지난 숙제 불러오기
    last_sess = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC LIMIT 1", conn)
    parsed_prev_hw = []
    if not last_sess.empty and last_sess.iloc[0]['next_hw']:
        items = last_sess.iloc[0]['next_hw'].split(" | ")
        for it in items:
            if ":" in it:
                b, r = it.split(":", 1)
                parsed_prev_hw.append({"book": b.strip(), "range": r.strip()})

    st.write("### ✍️ 지난 숙제 채점")
    # 숙제 채점 항목 동적 관리
    if 'check_rows' not in st.session_state: st.session_state.check_rows = max(1, len(parsed_prev_hw))
    
    total_q_sum, done_q_sum = 0, 0
    for i in range(st.session_state.check_rows):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        def_b = parsed_prev_hw[i]['book'] if i < len(parsed_prev_hw) else (s_books[0] if s_books else "")
        def_r = parsed_prev_hw[i]['range'] if i < len(parsed_prev_hw) else ""
        
        cb = c1.selectbox(f"채점 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(def_b) if def_b in s_books else 0, key=f"cb_{i}")
        cr = c2.text_input(f"범위 {i+1}", value=def_r, key=f"cr_{i}")
        ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
        cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
        total_q_sum += ct
        done_q_sum += cd
    
    btn_c1, btn_c2 = st.columns(2)
    if btn_c1.button("➕ 채점 항목 추가"): st.session_state.check_rows += 1; st.rerun()
    if btn_c2.button("➖ 채점 항목 삭제") and st.session_state.check_rows > 1: st.session_state.check_rows -= 1; st.rerun()

    final_rate = int((done_q_sum / total_q_sum * 100)) if total_q_sum > 0 else 100
    st.info(f"💡 전체 숙제 이행률: **{final_rate}%**")

    st.divider()

    with st.form("class_entry"):
        col_d, col_n = st.columns(2)
        date = col_d.date_input("날짜", datetime.now())
        s_num = col_n.number_input("회차", value=(last_sess.iloc[0]['session_num']+1 if not last_sess.empty else 1))

        st.write("📖 **오늘의 진도**")
        if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
        p_res = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", key=f"pr_{i}")
            if pb and pr: p_res.append(f"{pb}: {pr}")

        st.write("📝 **다음 숙제**")
        if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
        h_res = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", key=f"hr_{i}")
            if hb and hr: h_res.append(f"{hb}: {hr}")

        fback = st.text_area("피드백")
        if st.form_submit_button("💾 수업 기록 저장"):
            c.execute("INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) VALUES (?,?,?,?,?,?,?)",
                      (s_id, date.strftime("%Y-%m-%d"), s_num, " | ".join(p_res), final_rate, " | ".join(h_res), fback))
            conn.commit(); st.rerun()

    cp1, cp2, ch1, ch2 = st.columns(4)
    if cp1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
    if cp2.button("➖ 진도 삭제") and st.session_state.p_rows > 1: st.session_state.p_rows -= 1; st.rerun()
    if ch1.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
    if ch2.button("➖ 숙제 삭제") and st.session_state.h_rows > 1: st.session_state.h_rows -= 1; st.rerun()

# --- TAB 2: 데이터 분석 (날짜 형식 개선) ---
with tab2:
    st.subheader("📊 학습 분석")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        df['display_date'] = pd.to_datetime(df['date']).apply(get_date_str)
        fig = px.line(df, x='display_date', y='hw_result_rate', markers=True, title="성취도 추이")
        fig.update_layout(yaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("데이터가 없습니다.")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    new_b = st.text_input("새 교재 이름")
    if st.button("교재 추가"):
        s_books.append(new_b)
        c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id))
        conn.commit(); st.rerun()
    for i, b in enumerate(s_books):
        cb1, cb2 = st.columns([5,1])
        cb1.write(f"📖 {b}")
        if cb2.button("삭제", key=f"db_{i}"):
            s_books.pop(i); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    df_log = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    for _, row in df_log.iterrows():
        d_label = get_date_str(datetime.strptime(row['date'], "%Y-%m-%d"))
        with st.expander(f"📌 {row['session_num']}회차 | {d_label} | 성취도 {row['hw_result_rate']}%"):
            st.write(f"**진도:** {row['progress']}")
            st.write(f"**숙제:** {row['next_hw']}")
            st.info(f"**피드백:** {row['feedback']}")
