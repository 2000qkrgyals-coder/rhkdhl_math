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

# --- TAB 2: 학습 분석 (월별 상세 필터링 모드) ---
with tab2:
    st.subheader("📊 월별 상세 학습 통계")
    
    # 데이터 복사 및 전처리
    df_ana = df_se[df_se['student_id'] == s_id].copy()
    
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        df_ana['hw_result_rate'] = pd.to_numeric(df_ana['hw_result_rate'], errors='coerce')
        df_ana['duration'] = pd.to_numeric(df_ana['duration'], errors='coerce')
        
        # 1. 연도 및 월 선택UI (데이터가 있는 월만 추출)
        df_ana['year_month'] = df_ana['date'].dt.strftime('%Y-%m')
        available_months = sorted(df_ana['year_month'].unique(), reverse=True)
        
        col_sel1, col_sel2 = st.columns([2, 3])
        selected_month = col_sel1.selectbox("📅 분석할 월 선택", available_months)
        
        # 2. 선택한 월의 데이터만 필터링
        df_filtered = df_ana[df_ana['year_month'] == selected_month].sort_values('date')
        
        if not df_filtered.empty:
            # X축 라벨을 "일자(회차)" 형태로 만들어 식별이 잘 되게 함
            df_filtered['x_axis'] = df_filtered['date'].dt.strftime('%m/%d') + \
                                   " (" + df_filtered['session_num'].astype(int).astype(str) + "회)"
            
            # --- 그래프 1: 숙제 이행률 (선 + 점) ---
            st.write(f"### 📈 {selected_month} 이행률 추이")
            fig_rate = px.line(df_filtered, x='x_axis', y='hw_result_rate', 
                               markers=True,
                               text='hw_result_rate', # 점 위에 숫자 표시
                               title=f"{selected_month} 개별 수업별 이행률(%)", 
                               labels={'x_axis': '날짜(회차)', 'hw_result_rate': '이행률(%)'})
            
            fig_rate.update_traces(textposition="top center")
            fig_rate.update_layout(xaxis_type='category', yaxis_range=[-5, 115])
            st.plotly_chart(fig_rate, use_container_width=True)
            
            # --- 그래프 2: 수업 시간 (막대) ---
            st.write(f"### ⏱️ {selected_month} 수업 시간 상세")
            fig_dur = px.bar(df_filtered, x='x_axis', y='duration', 
                             text='duration',
                             color='duration',
                             color_continuous_scale='Blues',
                             title=f"{selected_month} 개별 수업 시간(분)",
                             labels={'x_axis': '날짜(회차)', 'duration': '수업시간(분)'})
            
            fig_dur.update_traces(textposition="outside")
            fig_dur.update_layout(xaxis_type='category')
            st.plotly_chart(fig_dur, use_container_width=True)
            
            # --- 월간 요약 지표 ---
            st.divider()
            m_avg_rate = int(df_filtered['hw_result_rate'].mean())
            m_total_dur = int(df_filtered['duration'].sum())
            m_count = len(df_filtered)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("월평균 이행률", f"{m_avg_rate}%")
            c2.metric("월 총 수업시간", f"{m_total_dur}분")
            c3.metric("수업 횟수", f"{m_count}회")
            
        else:
            st.warning("해당 월에는 기록된 수업이 없습니다.")
            
    else:
        st.info("데이터가 없습니다. 먼저 수업을 기록해 주세요.")

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

# --- TAB 4: 전체 로그 (월별 필터링 기능 추가) ---
with tab4:
    st.subheader("📂 수업 로그 조회")

    if not all_sessions.empty:
        # 데이터 전처리: 날짜 기반으로 '연도-월' 컬럼 생성
        all_sessions['date_dt'] = pd.to_datetime(all_sessions['date'])
        all_sessions['year_month'] = all_sessions['date_dt'].dt.strftime('%Y-%m')
        
        # 필터링 UI
        available_months_log = sorted(all_sessions['year_month'].unique(), reverse=True)
        log_filter = st.selectbox("📅 조회할 월 선택", ["전체 보기"] + available_months_log, key="log_month_filter")

        # 필터 적용
        if log_filter == "전체 보기":
            display_df = all_sessions.sort_values(by='session_num', ascending=False)
        else:
            display_df = all_sessions[all_sessions['year_month'] == log_filter].sort_values(by='session_num', ascending=False)

        st.write(f"🔍 **총 {len(display_df)}건**의 기록이 있습니다.")
        st.divider()

        # 로그 출력 루프
        for _, row in display_df.iterrows():
            # 회차, 날짜, 시간, 이행률을 한눈에 보여주는 제목
            title = f"📌 {int(row['session_num'])}회차 | {row['date']} ({int(row['duration'])}분) | 숙제 {int(row['hw_result_rate'])}%"
            
            with st.expander(title):
                col_log1, col_log2 = st.columns(2)
                with col_log1:
                    st.markdown("**✅ 숙제 채점 결과**")
                    st.caption(row['hw_detail'] if row['hw_detail'] else "기록 없음")
                    st.markdown("**📖 오늘 나간 진도**")
                    st.caption(row['progress'] if row['progress'] else "기록 없음")
                
                with col_log2:
                    st.markdown("**📝 다음 시간 숙제**")
                    st.caption(row['next_hw'] if row['next_hw'] else "숙제 없음")
                    st.markdown("**💬 선생님 피드백**")
                    st.info(row['feedback'] if row['feedback'] else "입력된 피드백이 없습니다.")

                # 데이터 수정 버튼
                if st.button("📝 이 데이터 수정하기", key=f"edit_log_{row['id']}"):
                    st.session_state.edit_id = row['id']
                    st.session_state.edit_date = row['date']
                    st.session_state.edit_session_num = int(row['session_num'])
                    st.session_state.edit_feedback = row['feedback']
                    
                    # 진도/숙제/채점 행 개수 복원 및 값 주입
                    p_parts = str(row['progress']).split(" | ")
                    st.session_state.p_rows = len(p_parts)
                    for i, p in enumerate(p_parts): st.session_state[f"edit_p_val_{i}"] = p
                    
                    h_parts = str(row['next_hw']).split(" | ")
                    st.session_state.h_rows = len(h_parts)
                    for i, h in enumerate(h_parts): st.session_state[f"edit_h_val_{i}"] = h
                    
                    c_parts = str(row['hw_detail']).split(" | ")
                    st.session_state.check_rows = len(c_parts)
                    for i, c in enumerate(c_parts): st.session_state[f"edit_c_val_{i}"] = c
                    
                    st.success("데이터를 불러왔습니다. '수업 기록' 탭으로 이동하세요!")
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.info("기록된 수업 로그가 없습니다.")
