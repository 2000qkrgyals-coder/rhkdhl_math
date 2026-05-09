import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v8_2.db', check_same_thread=False)
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

# --- [2. 사이드바] ---
with st.sidebar:
    st.title("📑 Tutor Management v8.2")
    with st.expander("👤 학생 등록"):
        new_name = st.text_input("이름 입력")
        if st.button("학생 추가"):
            c.execute("INSERT INTO students (name, books) VALUES (?, ?)", (new_name, json.dumps([])))
            conn.commit(); st.rerun()

    st_df = pd.read_sql_query("SELECT * FROM students", conn)
    if not st_df.empty:
        sel_name = st.selectbox("학생 선택", st_df['name'])
        s_data = st_df[st_df['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        s_books = json.loads(s_data['books']) if s_data['books'] else []
    else:
        st.warning("학생을 먼저 등록하세요."); st.stop()

# --- [3. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 데이터 분석", "📚 교재 관리", "📂 전체 로그"])

# 세션 상태 초기화 (수정 모드 관리)
if 'edit_id' not in st.session_state: st.session_state.edit_id = None
if 'load_hw_session' not in st.session_state: st.session_state.load_hw_session = None

# --- TAB 1: 수업 기록/수정 ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ 현재 {st.session_state.edit_session_num}회차 기록을 **수정 중**입니다.")
        if st.button("수정 취소 (새 기록 모드)"):
            st.session_state.edit_id = None; st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록" if not st.session_state.edit_id else f"[{sel_name}] 수업 기록 수정")
    
    # 1. 과거 숙제 불러오기 기능
    all_sessions = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    
    with st.expander("📥 지난 숙제 내역 불러오기", expanded=True):
        if not all_sessions.empty:
            hw_options = {f"{r['session_num']}회차 ({get_date_str(datetime.strptime(r['date'], '%Y-%m-%d'))})": r['next_hw'] for _, r in all_sessions.iterrows()}
            selected_hw_key = st.selectbox("불러올 회차 선택", hw_options.keys())
            if st.button("해당 숙제를 채점 칸에 적용"):
                st.session_state.load_hw_content = hw_options[selected_hw_key]
                st.rerun()
        else:
            st.info("이전에 기록된 수업이 없습니다.")

    # 숙제 파싱 로직
    parsed_hw = []
    content_to_parse = st.session_state.get('load_hw_content', "")
    if content_to_parse:
        for it in content_to_parse.split(" | "):
            if ":" in it:
                b, r = it.split(":", 1)
                parsed_hw.append({"book": b.strip(), "range": r.strip()})

    # 채점 섹션
    st.write("### ✍️ 숙제 채점")
    check_rows = max(1, len(parsed_hw))
    total_q, done_q = 0, 0
    for i in range(check_rows):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        def_b = parsed_hw[i]['book'] if i < len(parsed_hw) else ""
        def_r = parsed_hw[i]['range'] if i < len(parsed_hw) else ""
        
        cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(def_b) if def_b in s_books else 0, key=f"cb_{i}")
        cr = c2.text_input(f"범위 {i+1}", value=def_r, key=f"cr_{i}")
        ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
        cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
        total_q += ct; done_q += cd
    
    final_rate = int((done_q / total_q * 100)) if total_q > 0 else 100
    st.info(f"💡 이번 회차 숙제 이행률: **{final_rate}%**")

    st.divider()

    # 수업 입력/수정 폼
    with st.form("main_form"):
        col_d, col_n = st.columns(2)
        # 수정 모드면 기존 값, 아니면 새 값
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_val = st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)
        
        date = col_d.date_input("날짜", d_val)
        sess_num = col_n.number_input("회차", value=int(n_val))

        st.write("📖 **오늘의 진도**")
        prog_val = st.text_input("진도 내용 (교재: 범위 | 교재: 범위 형식)", value=st.session_state.get('edit_progress', ""))
        
        st.write("📝 **다음 숙제**")
        hw_val = st.text_input("다음 숙제 내용", value=st.session_state.get('edit_next_hw', ""))
        
        fback_val = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""))

        save_btn = st.form_submit_button("💾 수정 완료" if st.session_state.edit_id else "💾 수업 저장")
        
        if save_btn:
            if st.session_state.edit_id:
                c.execute("""UPDATE sessions SET date=?, session_num=?, progress=?, hw_result_rate=?, next_hw=?, feedback=? 
                             WHERE id=?""", (date.strftime("%Y-%m-%d"), sess_num, prog_val, final_rate, hw_val, fback_val, st.session_state.edit_id))
                st.session_state.edit_id = None # 수정 완료 후 초기화
            else:
                c.execute("INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) VALUES (?,?,?,?,?,?,?)",
                          (s_id, date.strftime("%Y-%m-%d"), sess_num, prog_val, final_rate, hw_val, fback_val))
            conn.commit(); st.rerun()

# --- TAB 2: 데이터 분석 ---
with tab2:
    st.subheader("📊 학습 통계")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        df['display_date'] = pd.to_datetime(df['date']).apply(get_date_str)
        fig = px.line(df, x='display_date', y='hw_result_rate', markers=True)
        fig.update_layout(yaxis_range=[-5, 105], xaxis_title="날짜(요일)")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("기록이 없습니다.")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    new_b = st.text_input("새 교재 추가")
    if st.button("추가") and new_b:
        s_books.append(new_b); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()
    for i, b in enumerate(s_books):
        c_b1, c_b2 = st.columns([5,1])
        c_b1.write(f"📖 {b}")
        if c_b2.button("삭제", key=f"del_b_{i}"):
            s_books.pop(i); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 (수정 버튼 추가) ---
with tab4:
    st.subheader("📂 수업 히스토리")
    df_log = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    for _, row in df_log.iterrows():
        d_label = get_date_str(datetime.strptime(row['date'], "%Y-%m-%d"))
        col_log, col_edit = st.columns([6, 1])
        with col_log:
            with st.expander(f"📌 {row['session_num']}회차 | {d_label} | 성취도 {row['hw_result_rate']}%"):
                st.write(f"**진도:** {row['progress']}")
                st.write(f"**숙제:** {row['next_hw']}")
                st.info(f"**피드백:** {row['feedback']}")
        with col_edit:
            if st.button("📝 수정", key=f"edit_btn_{row['id']}"):
                # 수정 데이터 세션에 저장
                st.session_state.edit_id = row['id']
                st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = row['session_num']
                st.session_state.edit_progress = row['progress']
                st.session_state.edit_next_hw = row['next_hw']
                st.session_state.edit_feedback = row['feedback']
                st.success(f"{row['session_num']}회차 데이터를 불러왔습니다. 첫 번째 탭으로 이동하세요!")
