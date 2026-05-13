import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, time as dt_time
import plotly.express as px
import json
import time

# --- [0. 보안 설정] ---
# 실제 배포 시에는 비밀번호를 코드에 적지 말고 Streamlit Secrets 기능을 권장합니다.
MASTER_PASSWORD = "03241005"  # <--- 선생님이 사용하실 비밀번호로 수정하세요.

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- [1. 로그인 화면 구현] ---
def login_screen():
    st.title("🔒 Tutor Pro Access")
    pwd = st.text_input("마스터 비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if pwd == MASTER_PASSWORD:
            st.session_state.logged_in = True
            st.success("로그인 성공!")
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")

# 로그인되지 않은 경우 앱 실행 중단
if not st.session_state.logged_in:
    login_screen()
    st.stop()

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
        if not df.empty:
            for col in ['id', 'student_id', 'session_num', 'duration', 'hw_result_rate']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- [2. 세션 상태 및 초기화 로직] ---
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
if 'check_rows' not in st.session_state: st.session_state.check_rows = 1

def full_reset():
    for key in list(st.session_state.keys()):
        if key not in ['main_student_selector', 'p_rows', 'h_rows', 'check_rows']:
            del st.session_state[key]
    st.session_state.p_rows = 1
    st.session_state.h_rows = 1
    st.session_state.check_rows = 1
    st.rerun()

# --- [3. 사이드바] ---
with st.sidebar:
    st.title("📑 Tutor Pro v10.5")
    df_st = load_data("students")
    if not df_st.empty:
        sel_name = st.selectbox("학생 선택", df_st['name'], key="main_student_selector")
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except: s_books = []
    else: st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False) if not df_se.empty else pd.DataFrame()

    col_status, col_reset = st.columns([4, 1])
    is_edit_mode = st.session_state.get('edit_id') is not None
    if is_edit_mode: 
        col_status.warning(f"🔄 **{st.session_state.edit_session_num}회차 수정 중**")
    if col_reset.button("🔄 내용 초기화"): full_reset()

    st.write("### ✍️ 지난 숙제 채점")
    
    if not all_sessions.empty:
        hw_options = {f"[{int(row['session_num'])}회차] {row['date']} : {row['next_hw']}": row['next_hw'] for _, row in all_sessions.iterrows()}
        selected_label = st.selectbox("📥 이전 숙제 불러오기 (날짜/회차)", ["선택 안 함"] + list(hw_options.keys()))
        
        if selected_label != "선택 안 함" and st.button("적용하기"):
            actual_hw = hw_options[selected_label]
            hw_parts = actual_hw.split(" | ")
            st.session_state.check_rows = len(hw_parts)
            for i, part in enumerate(hw_parts):
                st.session_state[f"edit_c_val_{i}"] = part
            st.rerun()

    no_hw = st.checkbox("✅ 숙제 없음", key="no_hw_check", value=st.session_state.get('edit_no_hw', False))
    check_list, acc_total, acc_done = [], 0, 0
    
    if not no_hw:
        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            e_val = st.session_state.get(f"edit_c_val_{i}", "")
            def_book = e_val.split(":")[0] if ":" in e_val else (s_books[0] if s_books else "미등록")
            def_range = e_val.split(":")[1].split("(")[0].strip() if "(" in e_val else (e_val.split(":")[1].strip() if ":" in e_val else "")
            
            cb = c1.selectbox(f"교재 {i+1}", s_books, index=s_books.index(def_book) if def_book in s_books else 0, key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", value=def_range, key=f"cr_{i}")
            ct = c3.number_input(f"총", min_value=0, key=f"ct_{i}")
            cd = c4.number_input(f"푼", min_value=0, key=f"cd_{i}")
            if cb and cr: check_list.append(f"{cb}: {cr} ({cd}/{ct})")
            acc_total += ct; acc_done += cd
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
        st.write(f"📊 **이행률 합계: {final_rate}%**")
    else: final_rate = 100

    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("➕ 채점칸 추가"): st.session_state.check_rows += 1; st.rerun()
    if c_btn2.button("➖ 채점칸 제거"): st.session_state.check_rows = max(1, st.session_state.check_rows-1); st.rerun()

    st.divider()

    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if is_edit_mode else datetime.now()
        date_in = c_d.date_input("날짜", d_val)
        next_s = int(all_sessions['session_num'].max() + 1) if not all_sessions.empty else 1
        sess_num = c_n.number_input("회차", value=int(st.session_state.get('edit_session_num', next_s)))
        
        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("시작", dt_time(14, 0)); end_t = c_t2.time_input("종료", dt_time(16, 0))

        p_list, h_list = [], []
        st.write("📖 진도")
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            e_p = st.session_state.get(f"edit_p_val_{i}", "")
            p_book = e_p.split(":")[0].strip() if ":" in e_p else ""
            p_range = e_p.split(":")[1].strip() if ":" in e_p else ""
            pb = cc1.selectbox(f"진도 {i+1}", s_books, index=s_books.index(p_book) if p_book in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위", value=p_range, key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")
        
        st.write("📝 다음 숙제")
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            e_h = st.session_state.get(f"edit_h_val_{i}", "")
            h_book = e_h.split(":")[0].strip() if ":" in e_h else ""
            h_range = e_h.split(":")[1].strip() if ":" in e_h else ""
            hb = cc1.selectbox(f"숙제 {i+1}", s_books, index=s_books.index(h_book) if h_book in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위", value=h_range, key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""), key="fb_text")
        if st.form_submit_button("💾 저장하기"):
            dur = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
            new_id = int(st.session_state.edit_id) if is_edit_mode else (int(df_se['id'].max()+1) if not df_se.empty else 1)
            new_row = {
                'id': new_id, 'student_id': s_id, 'date': str(date_in), 'session_num': int(sess_num),
                'start_time': start_t.strftime("%H:%M"), 'end_time': end_t.strftime("%H:%M"), 'duration': int(dur),
                'hw_detail': " | ".join(check_list), 'progress': " | ".join(p_list),
                'hw_result_rate': int(final_rate), 'next_hw': " | ".join(h_list), 'feedback': fback
            }
            if is_edit_mode: df_se = df_se[df_se['id'] != st.session_state.edit_id]
            save_data(pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True), "sessions")
            st.success("저장되었습니다!"); time.sleep(1); full_reset()

    col_p1, col_p2, col_h1, col_h2 = st.columns(4)
    if col_p1.button("➕ 진도칸+"): st.session_state.p_rows += 1; st.rerun()
    if col_p2.button("➖ 진도칸-"): st.session_state.p_rows = max(1, st.session_state.p_rows-1); st.rerun()
    if col_h1.button("➕ 숙제칸+"): st.session_state.h_rows += 1; st.rerun()
    if col_h2.button("➖ 숙제칸-"): st.session_state.h_rows = max(1, st.session_state.h_rows-1); st.rerun()

# --- TAB 2: 학습 분석 (개별 데이터 보존 통계) ---
with tab2:
    st.subheader("📊 학습 데이터 통계")
    df_ana = df_se[df_se['student_id'] == s_id].copy()
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        df_ana['hw_result_rate'] = pd.to_numeric(df_ana['hw_result_rate'], errors='coerce')
        df_ana['duration'] = pd.to_numeric(df_ana['duration'], errors='coerce')
        
        view_opt = st.radio("통계 기준", ["회차별", "주별 통계", "월별 통계"], horizontal=True)
        
        df_plot = df_ana.sort_values('date')
        
        if view_opt == "주별 통계":
            # X축 라벨을 해당 날짜가 속한 주차의 월/일로 변환
            df_plot['x_axis'] = df_plot['date'].dt.to_period('W').apply(lambda r: r.start_time.strftime('%m/%d 주'))
        elif view_opt == "월별 통계":
            # X축 라벨을 해당 날짜가 속한 월로 변환
            df_plot['x_axis'] = df_plot['date'].dt.strftime('%Y-%m')
        else:
            # 회차별 (기존 방식)
            df_plot['x_axis'] = df_plot['session_num'].astype(int).astype(str) + "회차"

        # 평균을 내지 않고 모든 데이터를 점으로 표시 (색상을 회차로 구분)
        fig_rate = px.scatter(df_plot, x='x_axis', y='hw_result_rate', 
                              size=[10]*len(df_plot), color='session_num',
                              title="기간별 숙제 이행률 분포", 
                              labels={'x_axis': '시점', 'hw_result_rate': '이행률(%)', 'session_num': '회차'},
                              hover_data=['date'])
        # 선을 추가하여 흐름 표시
        fig_rate.add_traces(px.line(df_plot, x='x_axis', y='hw_result_rate').data)
        fig_rate.update_layout(xaxis_type='category', yaxis_range=[-5, 105])
        st.plotly_chart(fig_rate, use_container_width=True)
        
        fig_dur = px.bar(df_plot, x='x_axis', y='duration', color='session_num',
                         title="기간별 수업 시간 상세",
                         labels={'x_axis': '시점', 'duration': '수업시간(분)'},
                         barmode='group') # 같은 주/월에 여러 수업이 있으면 나란히 표시
        fig_dur.update_layout(xaxis_type='category')
        st.plotly_chart(fig_dur, use_container_width=True)
    else: st.info("데이터가 없습니다.")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 목록")
    nb = st.text_input("새 교재 명")
    if st.button("교재 추가") and nb:
        if nb not in s_books:
            s_books.append(nb); df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students"); st.rerun()
    for i, b in enumerate(s_books):
        c_b, c_d = st.columns([4,1])
        c_b.write(f"📖 {b}")
        if c_d.button("삭제", key=f"del_book_{i}"):
            s_books.remove(b); df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students"); st.rerun()

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 전체 수업 로그")
    if not all_sessions.empty:
        for _, row in all_sessions.iterrows():
            title = f"📌 {int(row['session_num'])}회차 | {row['date']} ({int(row['duration'])}분) | {int(row['hw_result_rate'])}%"
            with st.expander(title):
                st.text(f"✅ 채점: {row['hw_detail']}")
                st.text(f"📖 진도: {row['progress']}")
                st.text(f"📝 숙제: {row['next_hw']}")
                st.info(f"💬 피드백: {row['feedback']}")
                
                if st.button("📝 이 데이터 수정", key=f"edit_log_{row['id']}"):
                    st.session_state.edit_id = row['id']
                    st.session_state.edit_date = row['date']
                    st.session_state.edit_session_num = int(row['session_num'])
                    st.session_state.edit_feedback = row['feedback']
                    p_parts = str(row['progress']).split(" | ")
                    st.session_state.p_rows = len(p_parts)
                    for i, p in enumerate(p_parts): st.session_state[f"edit_p_val_{i}"] = p
                    h_parts = str(row['next_hw']).split(" | ")
                    st.session_state.h_rows = len(h_parts)
                    for i, h in enumerate(h_parts): st.session_state[f"edit_h_val_{i}"] = h
                    c_parts = str(row['hw_detail']).split(" | ")
                    st.session_state.check_rows = len(c_parts)
                    for i, c in enumerate(c_parts): st.session_state[f"edit_c_val_{i}"] = c
                    st.success("수정 데이터 로드 완료! 탭 1로 이동하세요."); time.sleep(1); st.rerun()
