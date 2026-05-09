import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, time as dt_time
import plotly.express as px
import json
import time

# --- [1. 구글 시트 연결 및 최적화 설정] ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    try:
        return conn.read(worksheet=worksheet_name, ttl="1s")
    except Exception as e:
        st.error(f"시트 로드 오류: {e}")
        return pd.DataFrame()

def save_data(df, worksheet_name):
    try:
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- [2. 세션 상태 초기화] ---
init_keys = {
    'p_rows': 1, 'h_rows': 1, 'check_rows': 1, 
    'edit_id': None, 'no_hw': False
}
for key, default in init_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- [3. 사이드바 - 학생 선택] ---
with st.sidebar:
    st.title("📑 Tutor Pro v9.3")
    df_st = load_data("students")
    
    if not df_st.empty:
        sel_name = st.selectbox("관리할 학생 선택", df_st['name'])
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except:
            s_books = []
    else:
        st.warning("학생을 등록해 주세요.")
        st.stop()

# --- [4. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)

    if st.session_state.edit_id:
        st.info(f"🔄 **{st.session_state.edit_session_num}회차 기록 수정 모드**")
        if st.button("❌ 수정 취소 및 초기화"): 
            st.session_state.edit_id = None
            st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")

    # [지난 숙제 채점 섹션]
    st.write("### ✍️ 지난 숙제 채점")
    no_hw_check = st.checkbox("✅ 지난 숙제 없음 (채점 생략)", value=st.session_state.no_hw)
    st.session_state.no_hw = no_hw_check

    acc_total, acc_done = 0, 0
    if not st.session_state.no_hw:
        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", key=f"cr_{i}")
            ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
            cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
            acc_total += ct
            acc_done += cd
        
        c_b1, c_b2 = st.columns(2)
        if c_b1.button("➕ 채점 칸 추가"): st.session_state.check_rows += 1; st.rerun()
        if c_b2.button("➖ 제거") and st.session_state.check_rows > 1: st.session_state.check_rows -= 1; st.rerun()
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
    else:
        final_rate = 100

    st.divider()

    # [오늘 수업 정보 입력 섹션]
    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        
        # 수정 모드일 경우 세션에 저장된 값 사용, 아닐 경우 기본값
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_val = st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)
        st_val = datetime.strptime(st.session_state.edit_start, "%H:%M").time() if st.session_state.edit_id else dt_time(14, 0)
        et_val = datetime.strptime(st.session_state.edit_end, "%H:%M").time() if st.session_state.edit_id else dt_time(16, 0)

        c_d, c_n = st.columns(2)
        date_in = c_d.date_input("수업 날짜", d_val)
        sess_num = c_n.number_input("회차", value=int(n_val))

        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("수업 시작", st_val)
        end_t = c_t2.time_input("수업 종료", et_val)

        st.write("📖 진도")
        p_list = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            # 수정 데이터 불러오기 로직
            row_p_val = st.session_state.get(f"edit_p_val_{i}", "")
            pb_val = row_p_val.split(":")[0].strip() if ":" in row_p_val else (s_books[0] if s_books else "미등록")
            pr_val = row_p_val.split(":")[1].strip() if ":" in row_p_val else ""
            
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], 
                               index=s_books.index(pb_val) if pb_val in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", value=pr_val, key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 다음 숙제")
        h_list = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            # 수정 데이터 불러오기 로직
            row_h_val = st.session_state.get(f"edit_h_val_{i}", "")
            hb_val = row_h_val.split(":")[0].strip() if ":" in row_h_val else (s_books[0] if s_books else "미등록")
            hr_val = row_h_val.split(":")[1].strip() if ":" in row_h_val else ""

            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], 
                               index=s_books.index(hb_val) if hb_val in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", value=hr_val, key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback_val = st.session_state.edit_feedback if st.session_state.edit_id else ""
        fback = st.text_area("피드백", value=fback_val)
        
        btn_label = "📝 수정 완료 (덮어쓰기)" if st.session_state.edit_id else "💾 데이터 저장"
        submit = st.form_submit_button(btn_label)

    c_p1, c_p2, c_h1, c_h2 = st.columns(4)
    if c_p1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
    if c_p2.button("➖ 진도 제거"): st.session_state.p_rows = max(1, st.session_state.p_rows - 1); st.rerun()
    if c_h1.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
    if c_h2.button("➖ 숙제 제거"): st.session_state.h_rows = max(1, st.session_state.h_rows - 1); st.rerun()

    if submit:
        duration = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
        p_s = " | ".join(p_list) if p_list else "없음"
        h_s = " | ".join(h_list) if h_list else "없음"
        
        df_se = load_data("sessions")
        # 데이터 생성
        new_row = {
            'id': int(st.session_state.edit_id if st.session_state.edit_id else (df_se['id'].max() + 1 if not df_se.empty else 1)),
            'student_id': s_id, 'date': date_in.strftime("%Y-%m-%d"), 'session_num': sess_num,
            'start_time': start_t.strftime("%H:%M"), 'end_time': end_t.strftime("%H:%M"), 'duration': duration,
            'progress': p_s, 'hw_result_rate': final_rate, 'next_hw': h_s, 'feedback': fback
        }
        
        if st.session_state.edit_id:
            df_se.loc[df_se['id'] == st.session_state.edit_id, list(new_row.keys())] = list(new_row.values())
            st.session_state.edit_id = None # 수정 모드 해제
        else:
            df_se = pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True)
        
        save_data(df_se, "sessions")
        st.success("데이터가 성공적으로 반영되었습니다!")
        time.sleep(1)
        st.rerun()

# --- [TAB 2, 3 동일] ---
with tab2:
    st.subheader("📊 학습 분석")
    df_ana = load_data("sessions")
    df_ana = df_ana[df_ana['student_id'] == s_id].sort_values(by='date')
    if not df_ana.empty:
        st.plotly_chart(px.line(df_ana, x='session_num', y='hw_result_rate', markers=True, title="회차별 숙제 이행률(%)").update_layout(yaxis_range=[-5, 105]))

with tab3:
    st.subheader("📚 교재 관리")
    col_nb1, col_nb2 = st.columns([3, 1])
    nb = col_nb1.text_input("새 교재 이름")
    if col_nb2.button("추가") and nb:
        s_books.append(nb)
        df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
        save_data(df_st, "students")
        st.rerun()

# --- TAB 4: 전체 로그 (수정 기능 강화) ---
with tab4:
    st.subheader("📂 전체 수업 로그")
    df_log = load_data("sessions")
    df_log = df_log[df_log['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    
    for _, row in df_log.iterrows():
        d_time = f" ({row['start_time']}~{row['end_time']})"
        with st.expander(f"📌 {int(row['session_num'])}회차 | {row['date']}{d_time} | {row['hw_result_rate']}%"):
            st.text(f"진도: {row['progress']}\n숙제: {row['next_hw']}\n피드백: {row['feedback']}")
            
            if st.button("📝 이 데이터 수정하기", key=f"ed_btn_{row['id']}"):
                # 1. 기본 정보 세션에 저장
                st.session_state.edit_id = row['id']
                st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = int(row['session_num'])
                st.session_state.edit_start = row['start_time']
                st.session_state.edit_end = row['end_time']
                st.session_state.edit_feedback = row['feedback']
                
                # 2. 진도/숙제 파싱 및 칸 개수 설정
                p_items = row['progress'].split(" | ")
                h_items = row['next_hw'].split(" | ")
                
                st.session_state.p_rows = len(p_items)
                st.session_state.h_rows = len(h_items)
                
                # 3. 각 칸의 세부 내용 임시 저장
                for i, val in enumerate(p_items): st.session_state[f"edit_p_val_{i}"] = val
                for i, val in enumerate(h_items): st.session_state[f"edit_h_val_{i}"] = val
                
                st.success("데이터를 불러왔습니다. '수업 기록' 탭으로 이동하세요!")
                time.sleep(1)
                st.rerun()
