import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
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
    'p_rows': 1, 
    'h_rows': 1, 
    'check_rows': 1, 
    'edit_id': None,
    'no_hw': False  # 숙제 없음 상태 추가
}
for key, default in init_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- [3. 사이드바 - 학생 선택 및 등록] ---
with st.sidebar:
    st.title("📑 Tutor Pro v9.1")
    
    with st.expander("👤 신규 학생 등록"):
        new_name = st.text_input("학생 이름 입력", key="new_student_name")
        if st.button("등록하기") and new_name:
            df_st = load_data("students")
            new_id = int(df_st['id'].max() + 1) if not df_st.empty else 1
            new_row = pd.DataFrame([{'id': new_id, 'name': new_name, 'target_date': '', 'books': json.dumps([], ensure_ascii=False)}])
            df_st = pd.concat([df_st, new_row], ignore_index=True)
            save_data(df_st, "students")
            st.success(f"{new_name} 등록 완료!")
            time.sleep(0.5)
            st.rerun()

    df_st = load_data("students")
    
    if not df_st.empty:
        sel_name = st.selectbox("관리할 학생 선택", df_st['name'])
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except:
            s_books = []
        
        if st.button("❌ 학생 기록 전체 삭제"):
            df_st = df_st[df_st['id'] != s_id]
            save_data(df_st, "students")
            df_se = load_data("sessions")
            df_se = df_se[df_se['student_id'] != s_id]
            save_data(df_se, "sessions")
            st.rerun()
    else:
        st.warning("학생을 등록해 주세요.")
        st.stop()

# --- [4. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ 수정 모드 활성화 중")
        if st.button("수정 취소"): 
            st.session_state.edit_id = None
            st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)

    # --- [숙제 없음 기능 구간] ---
    st.write("### ✍️ 지난 숙제 확인")
    
    # 숙제 없음 체크박스
    no_hw_check = st.checkbox("✅ 지난 숙제 없음 (채점 생략)", value=st.session_state.no_hw)
    st.session_state.no_hw = no_hw_check

    acc_total, acc_done = 0, 0
    
    if not st.session_state.no_hw:
        with st.expander("📥 지난 숙제 내역 불러오기"):
            if not all_sessions.empty:
                hw_options = {f"{int(r['session_num'])}회차 ({r['date']})": r['next_hw'] for _, r in all_sessions.iterrows()}
                selected_hw_key = st.selectbox("회차 선택", list(hw_options.keys()))
                if st.button("채점 칸에 적용"):
                    items = hw_options[selected_hw_key].split(" | ")
                    st.session_state.check_rows = len(items)
                    for idx, item in enumerate(items):
                        if ":" in item:
                            b, r = item.split(":", 1)
                            st.session_state[f"cb_{idx}"] = b.strip()
                            st.session_state[f"cr_{idx}"] = r.strip()
                    st.rerun()

        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            cur_cb = st.session_state.get(f"cb_{i}", s_books[0] if s_books else "미등록")
            cur_cr = st.session_state.get(f"cr_{i}", "")
            
            cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], 
                              index=s_books.index(cur_cb) if cur_cb in s_books else 0, key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", value=cur_cr, key=f"cr_{i}")
            ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
            cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
            acc_total += ct
            acc_done += cd
        
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("➕ 채점 칸 추가"): 
            st.session_state.check_rows += 1
            st.rerun()
        if col_btn2.button("➖ 채점 칸 제거") and st.session_state.check_rows > 1:
            st.session_state.check_rows -= 1
            st.rerun()
            
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
    else:
        st.info("지난 수업에 내준 숙제가 없어 채점을 건너뜁니다.")
        final_rate = 100 # 숙제가 없었으므로 이행률은 100% 혹은 별도 처리

    st.markdown(f"#### 💡 최종 숙제 이행률: **{final_rate}%**")
    st.divider()

    with st.form("lesson_form"):
        col_d, col_n = st.columns(2)
        d_init = datetime.strptime(st.session_state.get('edit_date', datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
        n_init = st.session_state.get('edit_session_num', (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1))
        date_in = col_d.date_input("날짜", d_init)
        sess_num = col_n.number_input("회차", value=int(n_init))

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

        fback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""))
        submit = st.form_submit_button("💾 데이터 저장 (구글 시트)")

    c_p1, c_p2, c_h1, c_h2 = st.columns(4)
    if c_p1.button("➕ 진도 추가"): st.session_state.p_rows += 1; st.rerun()
    if c_p2.button("➖ 진도 제거") and st.session_state.p_rows > 1: st.session_state.p_rows -= 1; st.rerun()
    if c_h1.button("➕ 숙제 추가"): st.session_state.h_rows += 1; st.rerun()
    if c_h2.button("➖ 숙제 제거") and st.session_state.h_rows > 1: st.session_state.h_rows -= 1; st.rerun()

    if submit:
        p_s, h_s = (" | ".join(p_list) if p_list else "없음"), (" | ".join(h_list) if h_list else "없음")
        df_se = load_data("sessions")
        if st.session_state.edit_id:
            df_se.loc[df_se['id'] == st.session_state.edit_id, ['date', 'session_num', 'progress', 'hw_result_rate', 'next_hw', 'feedback']] = \
                [date_in.strftime("%Y-%m-%d"), sess_num, p_s, final_rate, h_s, fback]
            st.session_state.edit_id = None
        else:
            new_id = int(df_se['id'].max() + 1) if not df_se.empty else 1
            new_row = pd.DataFrame([{'id': new_id, 'student_id': s_id, 'date': date_in.strftime("%Y-%m-%d"), 
                                     'session_num': sess_num, 'progress': p_s, 'hw_result_rate': final_rate, 
                                     'next_hw': h_s, 'feedback': fback}])
            df_se = pd.concat([df_se, new_row], ignore_index=True)
        save_data(df_se, "sessions")
        st.success("저장되었습니다!")
        time.sleep(1)
        st.rerun()

# --- TAB 2: 학습 분석 ---
with tab2:
    st.subheader("📊 학습 분석")
    df_ana = load_data("sessions")
    df_ana = df_ana[df_ana['student_id'] == s_id].sort_values(by='date')
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        mode = st.radio("분석 단위", ["회차별", "주별", "월별"], horizontal=True)
        if mode == "회차별":
            df_ana['x'] = df_ana['session_num'].astype(str) + "회"
            plot_df = df_ana
        elif mode == "주별":
            df_ana['w'] = df_ana['date'].dt.to_period('W').apply(lambda r: r.start_time)
            plot_df = df_ana.groupby('w')['hw_result_rate'].mean().reset_index()
            plot_df['x'] = plot_df['w'].dt.strftime('%m/%d')
        else:
            df_ana['m'] = df_ana['date'].dt.to_period('M').apply(lambda r: r.start_time)
            plot_df = df_ana.groupby('m')['hw_result_rate'].mean().reset_index()
            plot_df['x'] = plot_df['m'].dt.strftime('%m월')
        st.plotly_chart(px.line(plot_df, x='x', y='hw_result_rate', markers=True, 
                                labels={'hw_result_rate':'이행률(%)', 'x':'일정'}).update_layout(yaxis_range=[-5, 105]))

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    col_nb1, col_nb2 = st.columns([3, 1])
    nb = col_nb1.text_input("새 교재 이름", key="new_book_input")
    if col_nb2.button("교재 추가") and nb:
        if nb not in s_books:
            s_books.append(nb)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()
    
    st.write("---")
    for b in s_books:
        c_b1, c_b2 = st.columns([4, 1])
        c_b1.write(f"📖 {b}")
        if c_b2.button("삭제", key=f"del_{b}"):
            s_books.remove(b)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()

# --- TAB 4: 전체 로그 (취소선 버그 수정 버전) ---
with tab4:
    st.subheader("📂 전체 수업 로그")
    df_log = load_data("sessions")
    df_log = df_log[df_log['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    
    for _, row in df_log.iterrows():
        # 제목 부분에도 취소선이 생기지 않도록 처리
        with st.expander(f"📌 {int(row['session_num'])}회차 | {row['date']} | {row['hw_result_rate']}%"):
            # st.text()를 사용하면 마크다운 문법을 무시하고 문자 그대로 출력합니다.
            st.write("**진도:**")
            st.text(row['progress']) 
            
            st.write("**숙제:**")
            st.text(row['next_hw'])
            
            st.write("**피드백:**")
            st.text(row['feedback'])
            
            if st.button("내용 수정", key=f"ed_log_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = int(row['session_num'])
                st.session_state.edit_feedback = row['feedback']
                st.rerun()
