import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. DB 초기화] ---
def init_db():
    conn = sqlite3.connect('tutor_pro_v8_3.db', check_same_thread=False)
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
    st.title("📑 Tutor Management v8.3")
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

# 세션 상태 초기화
if 'edit_id' not in st.session_state: st.session_state.edit_id = None
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1

# --- TAB 1: 수업 기록/수정 ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ {st.session_state.edit_session_num}회차 수정 모드 활성화 중")
        if st.button("수정 취소"):
            st.session_state.edit_id = None; st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")
    
    # 1. 지난 숙제 불러오기
    all_sessions = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    with st.expander("📥 지난 숙제 내역 불러오기"):
        if not all_sessions.empty:
            hw_options = {f"{r['session_num']}회차 ({get_date_str(datetime.strptime(r['date'], '%Y-%m-%d'))})": r['next_hw'] for _, r in all_sessions.iterrows()}
            selected_hw_key = st.selectbox("회차 선택", hw_options.keys())
            if st.button("채점 칸에 적용"):
                st.session_state.load_hw_content = hw_options[selected_hw_key]
                st.rerun()

    # 숙제 파싱 (채점용)
    parsed_check_hw = []
    load_content = st.session_state.get('load_hw_content', "")
    if load_content:
        for it in load_content.split(" | "):
            if ":" in it:
                b, r = it.split(":", 1)
                parsed_check_hw.append({"book": b.strip(), "range": r.strip()})

    # ✍️ 숙제 채점 섹션
    st.write("### ✍️ 숙제 채점")
    check_cnt = max(1, len(parsed_check_hw))
    t_q, d_q = 0, 0
    for i in range(check_cnt):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        def_b = parsed_check_hw[i]['book'] if i < len(parsed_check_hw) else ""
        def_r = parsed_check_hw[i]['range'] if i < len(parsed_check_hw) else ""
        cb = c1.selectbox(f"채점 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(def_b) if def_b in s_books else 0, key=f"cb_{i}")
        cr = c2.text_input(f"범위 {i+1}", value=def_r, key=f"cr_{i}")
        ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
        cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
        t_q += ct; d_q += cd
    final_rate = int((d_q / t_q * 100)) if t_q > 0 else 100
    st.info(f"💡 숙제 이행률: **{final_rate}%**")

    st.divider()

    # 📝 수업 입력 폼
    with st.form("input_form"):
        col_d, col_n = st.columns(2)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_val = st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)
        date = col_d.date_input("날짜", d_val)
        sess_num = col_n.number_input("회차", value=int(n_val))

        # 동적 진도 항목
        st.write("📖 **오늘의 진도**")
        p_list = []
        # 수정 모드 시 기존 데이터 분리
        if st.session_state.edit_id and 'edit_progress' in st.session_state:
            edit_p_items = st.session_state.edit_progress.split(" | ")
            st.session_state.p_rows = max(st.session_state.p_rows, len(edit_p_items))
        else: edit_p_items = []

        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            e_pb, e_pr = ("", "")
            if i < len(edit_p_items) and ":" in edit_p_items[i]:
                e_pb, e_pr = edit_p_items[i].split(":", 1)
            
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(e_pb.strip()) if e_pb.strip() in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", value=e_pr.strip(), key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        # 동적 숙제 항목
        st.write("📝 **다음 숙제**")
        h_list = []
        if st.session_state.edit_id and 'edit_next_hw' in st.session_state:
            edit_h_items = st.session_state.edit_next_hw.split(" | ")
            st.session_state.h_rows = max(st.session_state.h_rows, len(edit_h_items))
        else: edit_h_items = []

        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            e_hb, e_hr = ("", "")
            if i < len(edit_h_items) and ":" in edit_h_items[i]:
                e_hb, e_hr = edit_h_items[i].split(":", 1)

            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(e_hb.strip()) if e_hb.strip() in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", value=e_hr.strip(), key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        feedback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""))
        
        if st.form_submit_button("💾 수정 완료" if st.session_state.edit_id else "💾 수업 저장"):
            prog_str = " | ".join(p_list)
            next_hw_str = " | ".join(h_list)
            if st.session_state.edit_id:
                c.execute("UPDATE sessions SET date=?, session_num=?, progress=?, hw_result_rate=?, next_hw=?, feedback=? WHERE id=?",
                          (date.strftime("%Y-%m-%d"), sess_num, prog_str, final_rate, next_hw_str, feedback, st.session_state.edit_id))
                st.session_state.edit_id = None
            else:
                c.execute("INSERT INTO sessions (student_id, date, session_num, progress, hw_result_rate, next_hw, feedback) VALUES (?,?,?,?,?,?,?)",
                          (s_id, date.strftime("%Y-%m-%d"), sess_num, prog_str, final_rate, next_hw_str, feedback))
            conn.commit(); st.rerun()

    # 항목 조절 버튼 (폼 외부에 배치)
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
    if col_btn1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
    if col_btn2.button("➖ 진도 삭제") and st.session_state.p_rows > 1: st.session_state.p_rows -= 1; st.rerun()
    if col_btn3.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
    if col_btn4.button("➖ 숙제 삭제") and st.session_state.h_rows > 1: st.session_state.h_rows -= 1; st.rerun()

# --- TAB 2: 데이터 분석 ---
with tab2:
    st.subheader("📊 학습 분석")
    df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY date", conn)
    if not df.empty:
        df['display_date'] = pd.to_datetime(df['date']).apply(get_date_str)
        fig = px.line(df, x='display_date', y='hw_result_rate', markers=True)
        fig.update_layout(yaxis_range=[-5, 105], xaxis_title="날짜(요일)")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("데이터가 없습니다.")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    nb = st.text_input("새 교재 이름")
    if st.button("교재 추가") and nb:
        s_books.append(nb); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()
    for i, b in enumerate(s_books):
        cb1, cb2 = st.columns([5,1])
        cb1.write(f"📖 {b}")
        if cb2.button("삭제", key=f"db_{i}"):
            s_books.pop(i); c.execute("UPDATE students SET books=? WHERE id=?", (json.dumps(s_books), s_id)); conn.commit(); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 수업 히스토리")
    df_log = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={s_id} ORDER BY session_num DESC", conn)
    for _, row in df_log.iterrows():
        d_label = get_date_str(datetime.strptime(row['date'], "%Y-%m-%d"))
        c_l, c_e = st.columns([6, 1])
        with c_l:
            with st.expander(f"📌 {row['session_num']}회차 | {d_label} | 성취도 {row['hw_result_rate']}%"):
                st.write(f"**진도:** {row['progress']}")
                st.write(f"**숙제:** {row['next_hw']}")
                st.info(f"**피드백:** {row['feedback']}")
        with c_e:
            if st.button("📝 수정", key=f"ed_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = row['session_num']
                st.session_state.edit_progress = row['progress']
                st.session_state.edit_next_hw = row['next_hw']
                st.session_state.edit_feedback = row['feedback']
                st.success("데이터를 불러왔습니다. 첫 번째 탭으로 이동하세요!")
                st.rerun()
