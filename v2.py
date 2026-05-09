import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, time as dt_time
import plotly.express as px
import json
import time

# --- [1. 구글 시트 연결 및 데이터 로드] ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    try:
        df = conn.read(worksheet=worksheet_name, ttl="1s")
        return df.dropna(how='all') 
    except Exception as e:
        st.error(f"로드 오류: {e}")
        return pd.DataFrame()

def save_data(df, worksheet_name):
    try:
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- [2. 세션 상태 초기화 및 초기화 함수] ---
def reset_session_inputs():
    """입력 필드 초기화 함수"""
    st.session_state.edit_id = None
    st.session_state.p_rows = 1
    st.session_state.h_rows = 1
    st.session_state.check_rows = 1
    st.session_state.edit_feedback = ""
    st.session_state.no_hw = False
    # 동적으로 생성된 진도/숙제/채점값 삭제
    keys_to_del = [k for k in st.session_state.keys() if any(x in k for x in ['edit_p_val_', 'edit_h_val_', 'edit_c_val_', 'pb_', 'pr_', 'hb_', 'hr_', 'cb_', 'cr_', 'ct_', 'cd_'])]
    for k in keys_to_del:
        del st.session_state[k]

init_keys = {
    'p_rows': 1, 'h_rows': 1, 'check_rows': 1, 
    'edit_id': None, 'edit_session_num': 0,
    'edit_date': datetime.now().strftime("%Y-%m-%d"),
    'edit_start': "14:00", 'edit_end': "16:00",
    'edit_feedback': "", 'no_hw': False
}
for key, default in init_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- [3. 사이드바 - 학생 관리] ---
with st.sidebar:
    st.title("📑 Tutor Pro v9.9")
    df_st = load_data("students")
    
    if not df_st.empty:
        sel_name = st.selectbox("학생 선택", df_st['name'])
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except: s_books = []
    else:
        st.warning("학생을 등록하세요."); st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    df_se = load_data("sessions")
    if not df_se.empty:
        for col in ['id', 'student_id', 'session_num', 'hw_result_rate']:
            df_se[col] = pd.to_numeric(df_se[col], errors='coerce')

    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False) if not df_se.empty else pd.DataFrame()

    # 상단 상태 알림 및 초기화 버튼
    col_status, col_reset = st.columns([4, 1])
    if st.session_state.get('edit_id') is not None:
        col_status.info(f"🔄 **{st.session_state.get('edit_session_num')}회차 수정 모드**")
    if col_reset.button("🔄 내용 초기화"):
        reset_session_inputs()
        st.rerun()

    st.write("### ✍️ 지난 숙제 채점")
    no_hw_check = st.checkbox("✅ 숙제 없음 (채점 생략)", value=st.session_state.no_hw)
    st.session_state.no_hw = no_hw_check

    check_list, acc_total, acc_done = [], 0, 0
    if not st.session_state.no_hw:
        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            edit_c = st.session_state.get(f"edit_c_val_{i}", "")
            cb_i = edit_c.split(":")[0].strip() if ":" in edit_c else (s_books[0] if s_books else "미등록")
            cr_i = edit_c.split(":")[1].split("(")[0].strip() if "(" in edit_c else ""
            ct_i = int(edit_c.split("(")[1].split("/")[1].replace(")", "")) if "/" in edit_c else 0
            cd_i = int(edit_c.split("(")[1].split("/")[0]) if "/" in edit_c else 0

            cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(cb_i) if cb_i in s_books else 0, key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", value=cr_i, key=f"cr_{i}")
            ct = c3.number_input(f"총 문항", min_value=0, value=ct_i, key=f"ct_{i}")
            cd = c4.number_input(f"푼 문항", min_value=0, value=cd_i, key=f"cd_{i}")
            if cb and cr: check_list.append(f"{cb}: {cr} ({cd}/{ct})")
            acc_total += ct; acc_done += cd
        
        # [실시간 자동 계산 결과 표시]
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
        st.write(f"📊 **실시간 이행률 합계: {final_rate}%** ({acc_done}/{acc_total})")
    else: final_rate = 100

    st.divider()

    # 시간/날짜 복원 안전장치
    try:
        e_s, e_e = str(st.session_state.edit_start), str(st.session_state.edit_end)
        st_val = datetime.strptime(e_s[:5], "%H:%M").time() if st.session_state.edit_id else dt_time(14, 0)
        et_val = datetime.strptime(e_e[:5], "%H:%M").time() if st.session_state.edit_id else dt_time(16, 0)
        d_val = datetime.strptime(str(st.session_state.edit_date), "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
    except: st_val, et_val, d_val = dt_time(14, 0), dt_time(16, 0), datetime.now()

    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        date_in = c_d.date_input("날짜", d_val)
        next_s = (all_sessions['session_num'].max() + 1) if not all_sessions.empty else 1
        sess_num = c_n.number_input("회차", value=int(st.session_state.edit_session_num if st.session_state.edit_id else next_s))
        
        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("시작", st_val); end_t = c_t2.time_input("종료", et_val)

        st.write("📖 오늘 나간 진도")
        p_list = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            edit_p = st.session_state.get(f"edit_p_val_{i}", "")
            pb_i = edit_p.split(":")[0].strip() if ":" in edit_p else (s_books[0] if s_books else "미등록")
            pr_i = edit_p.split(":")[1].strip() if ":" in edit_p else ""
            pb = cc1.selectbox(f"진도 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(pb_i) if pb_i in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"범위 {i+1}", value=pr_i, key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 다음 숙제")
        h_list = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            edit_h = st.session_state.get(f"edit_h_val_{i}", "")
            hb_i = edit_h.split(":")[0].strip() if ":" in edit_h else (s_books[0] if s_books else "미등록")
            hr_i = edit_h.split(":")[1].strip() if ":" in edit_h else ""
            hb = cc1.selectbox(f"숙제 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(hb_i) if hb_i in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", value=hr_i, key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback = st.text_area("수업 피드백", value=st.session_state.edit_feedback if st.session_state.edit_id else "")
        submit = st.form_submit_button("💾 데이터 저장")

    if submit:
        dur = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
        new_row = {
            'id': int(st.session_state.edit_id) if st.session_state.edit_id else int(df_se['id'].max() + 1 if not df_se.empty else 1),
            'student_id': int(s_id), 'date': str(date_in.strftime("%Y-%m-%d")), 'session_num': int(sess_num),
            'start_time': str(start_t.strftime("%H:%M")), 'end_time': str(end_t.strftime("%H:%M")), 'duration': int(dur),
            'hw_detail': str(" | ".join(check_list) if check_list else "없음"),
            'progress': str(" | ".join(p_list)), 'hw_result_rate': int(final_rate), 'next_hw': str(" | ".join(h_list)), 'feedback': str(fback)
        }
        if st.session_state.edit_id:
            df_se = df_se[df_se['id'] != st.session_state.edit_id]
        df_se = pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df_se, "sessions")
        reset_session_inputs() # 저장 후 초기화
        st.success("데이터가 성공적으로 저장되었습니다!"); time.sleep(1); st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("➕ 채점/진도+"): st.session_state.check_rows += 1; st.session_state.p_rows += 1; st.rerun()
    if c2.button("➖ 채점/진도-"): 
        st.session_state.check_rows = max(1, st.session_state.check_rows-1)
        st.session_state.p_rows = max(1, st.session_state.p_rows-1); st.rerun()
    if c3.button("➕ 숙제+"): st.session_state.h_rows += 1; st.rerun()
    if c4.button("➖ 숙제-"): st.session_state.h_rows = max(1, st.session_state.h_rows-1); st.rerun()

# --- TAB 4: 전체 로그 (수업 시간 표시) ---
with tab4:
    st.subheader("📂 수업 로그 히스토리")
    if not all_sessions.empty:
        for _, row in all_sessions.iterrows():
            # [요청사항] 수업 시간(분)을 제목에 표시
            t_info = f" ({row['start_time']}~{row['end_time']}, {int(row['duration'])}분)"
            with st.expander(f"📌 {int(row['session_num'])}회차 | {row['date']}{t_info} | {row['hw_result_rate']}%"):
                st.write("**✅ 상세 채점:**"); st.text(row.get('hw_detail', '없음'))
                st.write("**📖 진도:**"); st.text(row['progress'])
                st.write("**📝 숙제:**"); st.text(row['next_hw'])
                st.write("**💬 피드백:**"); st.text(row['feedback'])
                if st.button("📝 수정", key=f"ed_{row['id']}"):
                    st.session_state.edit_id = row['id']
                    st.session_state.edit_date, st.session_state.edit_session_num = row['date'], int(row['session_num'])
                    st.session_state.edit_start, st.session_state.edit_end = row['start_time'], row['end_time']
                    st.session_state.edit_feedback = row['feedback']
                    c_p = str(row.get('hw_detail', '')).split(" | ") if row.get('hw_detail') != "없음" else []
                    st.session_state.check_rows = len(c_p) if c_p else 1
                    for i, v in enumerate(c_p): st.session_state[f"edit_c_val_{i}"] = v
                    p_p, h_p = str(row['progress']).split(" | "), str(row['next_hw']).split(" | ")
                    st.session_state.p_rows, st.session_state.h_rows = len(p_p), len(h_p)
                    for i, v in enumerate(p_p): st.session_state[f"edit_p_val_{i}"] = v
                    for i, v in enumerate(h_p): st.session_state[f"edit_h_val_{i}"] = v
                    st.rerun()
