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
    'edit_id': None, 'edit_session_num': 0,
    'edit_date': datetime.now().strftime("%Y-%m-%d"),
    'edit_start': "14:00", 'edit_end': "16:00",
    'edit_feedback': "", 'no_hw': False
}
for key, default in init_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- [3. 사이드바 - 학생 선택] ---
with st.sidebar:
    st.title("📑 Tutor Pro v9.5")
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
        st.warning("학생을 등록해 주세요."); st.stop()

# --- [4. 메인 화면 탭] ---
tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 1: 기록 및 수정 ---
with tab1:
    df_se = load_data("sessions")
    all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)

    if st.session_state.get('edit_id') is not None:
        st.info(f"🔄 **{st.session_state.get('edit_session_num')}회차 기록 수정 모드**")
        if st.button("❌ 수정 취소 및 초기화"): 
            st.session_state.edit_id = None
            st.rerun()
    
    st.subheader(f"[{sel_name}] 수업 기록")

    # [지난 숙제 채점]
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
            acc_total += ct; acc_done += cd
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
    else:
        final_rate = 100

    st.divider()

    # --- [중요: 폼 에러 방지를 위해 시간 파싱을 폼 외부에서 수행] ---
    try:
        # 시간 데이터가 datetime 객체인 경우와 문자열인 경우 모두 대응
        e_start = str(st.session_state.edit_start)
        e_end = str(st.session_state.edit_end)
        
        # "14:00:00" 형식으로 올 경우를 대비해 슬라이싱
        st_val = datetime.strptime(e_start[:5], "%H:%M").time() if st.session_state.edit_id else dt_time(14, 0)
        et_val = datetime.strptime(e_end[:5], "%H:%M").time() if st.session_state.edit_id else dt_time(16, 0)
        d_val = datetime.strptime(str(st.session_state.edit_date), "%Y-%m-%d") if st.session_state.edit_id else datetime.now()
    except Exception as e:
        # 파싱 에러 시 기본값 할당
        st_val, et_val, d_val = dt_time(14, 0), dt_time(16, 0), datetime.now()

    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        date_in = c_d.date_input("수업 날짜", d_val)
        sess_num = c_n.number_input("회차", value=int(st.session_state.edit_session_num if st.session_state.edit_id else (all_sessions['session_num'].max() + 1 if not all_sessions.empty else 1)))

        c_t1, c_t2 = st.columns(2)
        start_t = c_t1.time_input("수업 시작", st_val)
        end_t = c_t2.time_input("수업 종료", et_val)

        st.write("📖 진도")
        p_list = []
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            edit_p = st.session_state.get(f"edit_p_val_{i}", "")
            pb_init = edit_p.split(":")[0].strip() if ":" in edit_p else (s_books[0] if s_books else "미등록")
            pr_init = edit_p.split(":")[1].strip() if ":" in edit_p else ""
            pb = cc1.selectbox(f"진도 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(pb_init) if pb_init in s_books else 0, key=f"pb_{i}")
            pr = cc2.text_input(f"진도 범위 {i+1}", value=pr_init, key=f"pr_{i}")
            if pb and pr: p_list.append(f"{pb}: {pr}")

        st.write("📝 다음 숙제")
        h_list = []
        for i in range(st.session_state.h_rows):
            cc1, cc2 = st.columns([1, 2])
            edit_h = st.session_state.get(f"edit_h_val_{i}", "")
            hb_init = edit_h.split(":")[0].strip() if ":" in edit_h else (s_books[0] if s_books else "미등록")
            hr_init = edit_h.split(":")[1].strip() if ":" in edit_h else ""
            hb = cc1.selectbox(f"숙제 교재 {i+1}", s_books if s_books else ["미등록"], index=s_books.index(hb_init) if hb_init in s_books else 0, key=f"hb_{i}")
            hr = cc2.text_input(f"숙제 범위 {i+1}", value=hr_init, key=f"hr_{i}")
            if hb and hr: h_list.append(f"{hb}: {hr}")

        fback = st.text_area("피드백", value=st.session_state.edit_feedback if st.session_state.edit_id else "")
        submit = st.form_submit_button("📝 수정 완료" if st.session_state.edit_id else "💾 데이터 저장")

    if submit:
        duration = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
        new_data = {
            'id': int(st.session_state.edit_id if st.session_state.edit_id else (df_se['id'].max() + 1 if not df_se.empty else 1)),
            'student_id': s_id, 'date': date_in.strftime("%Y-%m-%d"), 'session_num': sess_num,
            'start_time': start_t.strftime("%H:%M"), 'end_time': end_t.strftime("%H:%M"), 'duration': duration,
            'progress': " | ".join(p_list), 'hw_result_rate': final_rate, 'next_hw': " | ".join(h_list), 'feedback': fback
        }
        if st.session_state.edit_id:
            df_se.loc[df_se['id'] == st.session_state.edit_id, list(new_data.keys())] = list(new_data.values())
            st.session_state.edit_id = None
        else:
            df_se = pd.concat([df_se, pd.DataFrame([new_data])], ignore_index=True)
        save_data(df_se, "sessions"); st.success("성공!"); time.sleep(1); st.rerun()

# --- TAB 2, 3, 4 생략 (기존과 동일하며 복원 로직 포함됨) ---
# (지면 관계상 핵심 수정사항만 반영하였습니다. 나머지 TAB 코드는 v9.4와 동일하게 유지됩니다.)
# --- TAB 2: 학습 분석 ---
with tab2:
    st.subheader("📊 학습 분석")
    df_ana = load_data("sessions")
    df_ana = df_ana[df_ana['student_id'] == s_id].sort_values(by='date')
    if not df_ana.empty:
        st.plotly_chart(px.line(df_ana, x='session_num', y='hw_result_rate', markers=True, title="회차별 숙제 이행률(%)").update_layout(yaxis_range=[-5, 105]))
        if 'duration' in df_ana.columns:
            st.plotly_chart(px.bar(df_ana, x='session_num', y='duration', title="회차별 수업 시간(분)"))

# --- TAB 3: 교재 관리 ---
with tab3:
    st.subheader("📚 교재 관리")
    col_b1, col_b2 = st.columns([3, 1])
    nb = col_b1.text_input("새 교재 이름")
    if col_b2.button("추가") and nb:
        if nb not in s_books:
            s_books.append(nb)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()
    st.write("---")
    for b in s_books:
        c1, c2 = st.columns([4, 1])
        c1.write(f"📖 {b}")
        if c2.button("삭제", key=f"del_{b}"):
            s_books.remove(b)
            df_st.loc[df_st['id'] == s_id, 'books'] = json.dumps(s_books, ensure_ascii=False)
            save_data(df_st, "students")
            st.rerun()

# --- TAB 4: 전체 로그 (취소선 버그 및 복원 기능 완비) ---
with tab4:
    st.subheader("📂 전체 수업 로그")
    df_log = load_data("sessions")
    df_log = df_log[df_log['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    
    for _, row in df_log.iterrows():
        t_info = f" ({row['start_time']}~{row['end_time']}, {row['duration']}분)"
        with st.expander(f"📌 {int(row['session_num'])}회차 | {row['date']}{t_info} | {row['hw_result_rate']}%"):
            # 취소선 방지를 위해 st.text() 사용
            st.write("**📖 진도:**")
            st.text(row['progress'])
            st.write("**📝 숙제:**")
            st.text(row['next_hw'])
            st.write("**💬 피드백:**")
            st.text(row['feedback'])
            
            if st.button("📝 수정하기", key=f"ed_btn_{row['id']}"):
                # 수정 데이터 세션 주입
                st.session_state.edit_id = row['id']
                st.session_state.edit_date = row['date']
                st.session_state.edit_session_num = int(row['session_num'])
                st.session_state.edit_start = row['start_time']
                st.session_state.edit_end = row['end_time']
                st.session_state.edit_feedback = row['feedback']
                
                # 진도/숙제 파싱 및 칸 개수 동기화
                p_parts = row['progress'].split(" | ")
                h_parts = row['next_hw'].split(" | ")
                st.session_state.p_rows = len(p_parts)
                st.session_state.h_rows = len(h_parts)
                
                for i, v in enumerate(p_parts): st.session_state[f"edit_p_val_{i}"] = v
                for i, v in enumerate(h_parts): st.session_state[f"edit_h_val_{i}"] = v
                
                st.success("데이터를 불러왔습니다. 첫 번째 탭으로 이동하세요!")
                time.sleep(0.5)
                st.rerun()
