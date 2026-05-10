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
        st.error(f"데이터 로드 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

def save_data(df, worksheet_name):
    try:
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

# --- [2. 세션 상태 관리 및 초기화 로직] ---
# 초기 위젯 갯수 및 수정 모드 상태 설정
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
if 'check_rows' not in st.session_state: st.session_state.check_rows = 1

def full_reset():
    """모든 입력값과 세션 상태를 완전히 비움"""
    for key in list(st.session_state.keys()):
        # 학생 선택 정보와 핵심 카운트를 제외한 모든 위젯 상태 삭제
        if key not in ['main_student_selector', 'p_rows', 'h_rows', 'check_rows']:
            del st.session_state[key]
    # 기본값 재설정
    st.session_state.p_rows = 1
    st.session_state.h_rows = 1
    st.session_state.check_rows = 1
    st.rerun()

# --- [3. 사이드바 - 학생 관리] ---
with st.sidebar:
    st.title("📑 Tutor Pro v10.0")
    df_st = load_data("students")
    
    if not df_st.empty:
        sel_name = st.selectbox("학생 선택", df_st['name'], key="main_student_selector")
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        try:
            # JSON 형식의 교재 리스트 파싱
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except: s_books = []
    else:
        st.warning("학생을 먼저 등록하세요."); st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    df_se = load_data("sessions")
    if not df_se.empty:
        for col in ['id', 'student_id', 'session_num', 'hw_result_rate']:
            df_se[col] = pd.to_numeric(df_se[col], errors='coerce')

    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False) if not df_se.empty else pd.DataFrame()

    # 수정 모드 표시 및 초기화 버튼
    col_status, col_reset = st.columns([4, 1])
    is_edit = st.session_state.get('edit_id') is not None
    if is_edit:
        col_status.info(f"🔄 **{st.session_state.get('edit_session_num')}회차 수정 중**")
    
    if col_reset.button("🔄 내용 초기화"):
        full_reset()

    st.write("### ✍️ 지난 숙제 채점")
    no_hw = st.checkbox("✅ 숙제 없음 (채점 생략)", key="no_hw_check")

    check_list, acc_total, acc_done = [], 0, 0
    if not no_hw:
        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            # 수정 시 데이터 복원용 (값이 있으면 사용)
            e_val = st.session_state.get(f"edit_c_val_{i}", "")
            
            cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", key=f"cr_{i}")
            ct = c3.number_input(f"총", min_value=0, key=f"ct_{i}")
            cd = c4.number_input(f"푼", min_value=0, key=f"cd_{i}")
            
            if cb and cr: check_list.append(f"{cb}: {cr} ({cd}/{ct})")
            acc_total += ct; acc_done += cd
        
        # 실시간 자동 이행률 계산
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
        st.write(f"📊 **실시간 이행률 합계: {final_rate}%** ({acc_done}/{acc_total})")
    else: final_rate = 100

    st.divider()

    with st.form("lesson_form", clear_on_submit=True):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        date_in = c_d.date_input("날짜", datetime.now())
        next_s = (all_sessions['session_num'].max() + 1) if not all_sessions.empty else 1
        sess_num = c_n.number_input("회차", value=int(st.session_state.get('edit_session_num', next_s)))
        
        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("시작", dt_time(14, 0)); end_t = c_t2.time_input("종료", dt_time(16, 0))

        st.write("📖 오늘 나간 진도")
        p_list = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 다음 숙제")
        h_list = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback = st.text_area("피드백", key="fb_text")
        submit = st.form_submit_button("💾 데이터 저장")

    if submit:
        dur = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
        new_row = {
            'id': int(st.session_state.edit_id) if is_edit else int(df_se['id'].max() + 1 if not df_se.empty else 1),
            'student_id': int(s_id), 'date': str(date_in), 'session_num': int(sess_num),
            'start_time': str(start_t.strftime("%H:%M")), 'end_time': str(end_t.strftime("%H:%M")), 'duration': int(dur),
            'hw_detail': str(" | ".join(check_list)), 'progress': str(" | ".join(p_list)),
            'hw_result_rate': int(final_rate), 'next_hw': str(" | ".join(h_list)), 'feedback': str(fback)
        }
        if is_edit: df_se = df_se[df_se['id'] != st.session_state.edit_id]
        df_se = pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df_se, "sessions")
        st.success("기록 완료!"); time.sleep(1); full_reset()

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("➕ 채점/진도+"): st.session_state.check_rows += 1; st.session_state.p_rows += 1; st.rerun()
    if c2.button("➖ 채점/진도-"): st.session_state.check_rows = max(1, st.session_state.check_rows-1); st.session_state.p_rows = max(1, st.session_state.p_rows-1); st.rerun()
    if c3.button("➕ 숙제+"): st.session_state.h_rows += 1; st.rerun()
    if c4.button("➖ 숙제-"): st.session_state.h_rows = max(1, st.session_state.h_rows-1); st.rerun()

# --- TAB 2: 학습 분석 ---
with tab2:
    st.subheader("📊 학습 성장 리포트")
    df_ana = df_se[df_se['student_id'] == s_id].sort_values(by='session_num')
    if not df_ana.empty:
        # 이행률 추이 차트
        fig_rate = px.line(df_ana, x='session_num', y='hw_result_rate', markers=True, 
                          title="회차별 숙제 이행률(%)", labels={'hw_result_rate':'이행률', 'session_num':'회차'})
        fig_rate.update_layout(yaxis_range=[-5, 105])
        st.plotly_chart(fig_rate, use_container_width=True)
        
        # 수업 시간 차트
        fig_dur = px.bar(df_ana, x='session_num', y='duration', title="회차별 수업 시간(분)")
        st.plotly_chart(fig_dur, use_container_width=True)
    else:
        st.info("분석할 데이터가 없습니다. 첫 수업을 기록해 보세요!")

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 사용 중인 교재")
    new_b = st.text_input("새 교재 추가")
    if st.button("교재 등록") and new_b:
        if new_b not in s_books:
            s_books.append(new_b)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.success(f"'{new_b}' 등록됨"); st.rerun()

    st.divider()
    for i, b in enumerate(s_books):
        col_b, col_del = st.columns([4, 1])
        col_b.write(f"{i+1}. {b}")
        if col_del.button("삭제", key=f"del_b_{i}"):
            s_books.remove(b)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()

# --- TAB 4: 로그 (취소선 방지 코드 적용) ---
with tab4:
    st.subheader("📂 수업 로그")
    if not all_sessions.empty:
        for _, row in all_sessions.iterrows():
            # 취소선 방지: 텍스트 출력 시 마크다운 형식이 아닌 일반 텍스트박스(code block 등) 사용 권장
            title = f"📌 {int(row['session_num'])}회차 | {row['date']} ({int(row['duration'])}분) | {int(row['hw_result_rate'])}%"
            with st.expander(title):
                # st.text()를 사용하여 특수문자가 마크다운으로 해석되지 않게 방지
                st.write("**✅ 상세 채점**")
                st.text(row.get('hw_detail', '없음'))
                st.write("**📖 수업 진도**")
                st.text(row['progress'])
                st.write("**📝 다음 숙제**")
                st.text(row['next_hw'])
                st.info(f"💬 피드백: {row['feedback']}")
