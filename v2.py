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

# --- [3. 사이드바 - 학생 선택 및 등록] ---
with st.sidebar:
    st.title("📑 Tutor Pro v9.2")
    
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
    else:
        st.warning("학생을 등록해 주세요.")
        st.stop()

# --- [4. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    if st.session_state.edit_id:
        st.warning(f"⚠️ 수정 모드 활성화 중 (수정 후 저장 시 기존 기록이 덮어씌워집니다)")
        if st.button("수정 취소"): 
            st.session_state.edit_id = None
            st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)

    # --- 숙제 채점 섹션 ---
    st.write("### ✍️ 지난 숙제 채점")
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
            cb = c1.selectbox(f"교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(cur_cb) if cur_cb in s_books else 0, key=f"cb_{i}")
            cr = c2.text_input(f"범위 {i+1}", value=cur_cr, key=f"cr_{i}")
            ct = c3.number_input(f"총 문항", min_value=0, step=1, key=f"ct_{i}")
            cd = c4.number_input(f"푼 문항", min_value=0, step=1, key=f"cd_{i}")
            acc_total += ct
            acc_done += cd
        
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("➕ 채점 칸 추가"): st.session_state.check_rows += 1; st.rerun()
        if col_btn2.button("➖ 채점 칸 제거") and st.session_state.check_rows > 1: st.session_state.check_rows -= 1; st.rerun()
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
    else:
        final_rate = 100

    st.info(f"💡 최종 숙제 이행률: **{final_rate}%**")
    st.divider()

    # --- 오늘 수업 정보 입력 ---
    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        date_in = c_d.date_input("수업 날짜", datetime.now())
        sess_num = c_n.number_input("회차", value=int(all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1))

        # 시간 입력 추가
        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("수업 시작", dt_time(14, 0))
        end_t = c_t2.time_input("수업 종료", dt_time(16, 0))

        st.write("📖 진도")
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
        # 시간 계산
        duration = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
        p_s, h_s = (" | ".join(p_list) if p_list else "없음"), (" | ".join(h_list) if h_list else "없음")
        
        df_se = load_data("sessions")
        new_data = {
            'id': int(st.session_state.edit_id if st.session_state.edit_id else (df_se['id'].max() + 1 if not df_se.empty else 1)),
            'student_id': s_id,
            'date': date_in.strftime("%Y-%m-%d"),
            'session_num': sess_num,
            'start_time': start_t.strftime("%H:%M"),
            'end_time': end_t.strftime("%H:%M"),
            'duration': duration,
            'progress': p_s,
            'hw_result_rate': final_rate,
            'next_hw': h_s,
            'feedback': fback
        }
        
        if st.session_state.edit_id:
            df_se.loc[df_se['id'] == st.session_state.edit_id, list(new_data.keys())] = list(new_data.values())
            st.session_state.edit_id = None
        else:
            df_se = pd.concat([df_se, pd.DataFrame([new_data])], ignore_index=True)
        
        save_data(df_se, "sessions")
        st.success(f"저장 완료! 총 수업 시간: {duration}분")
        time.sleep(1)
        st.rerun()

# --- TAB 2: 학습 분석 ---
with tab2:
    st.subheader("📊 학습 분석")
    df_ana = load_data("sessions")
    df_ana = df_ana[df_ana['student_id'] == s_id].sort_values(by='date')
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        # 그래프: 이행률 & 수업 시간
        st.plotly_chart(px.line(df_ana, x='session_num', y='hw_result_rate', markers=True, title="회차별 숙제 이행률(%)").update_layout(yaxis_range=[-5, 105]))
        if 'duration' in df_ana.columns:
            st.plotly_chart(px.bar(df_ana, x='session_num', y='duration', title="회차별 수업 시간(분)"))

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    col_nb1, col_nb2 = st.columns([3, 1])
    nb = col_nb1.text_input("새 교재 이름")
    if col_nb2.button("추가") and nb:
        s_books.append(nb)
        df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
        save_data(df_st, "students")
        st.rerun()
    for b in s_books:
        c1, c2 = st.columns([4, 1])
        c1.write(f"📖 {b}")
        if c2.button("삭제", key=f"del_{b}"):
            s_books.remove(b)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()

# --- TAB 4: 전체 로그 (선 그어짐 버그 수정) ---
with tab4:
    st.subheader("📂 전체 수업 로그")
    df_log = load_data("sessions")
    df_log = df_log[df_log['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    
    for _, row in df_log.iterrows():
        d_time = f" ({row['start_time']}~{row['end_time']}, {row['duration']}분)" if 'duration' in row else ""
        with st.expander(f"📌 {int(row['session_num'])}회차 | {row['date']}{d_time} | {row['hw_result_rate']}%"):
            st.write("**📖 진도:**")
            st.text(row['progress']) # 취소선 방지를 위해 st.text 사용
            st.write("**📝 다음 숙제:**")
            st.text(row['next_hw'])
            st.write("**💬 피드백:**")
            st.text(row['feedback'])
            
            if st.button("수정", key=f"ed_log_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.session_state.edit_feedback = row['feedback']
                st.rerun()
