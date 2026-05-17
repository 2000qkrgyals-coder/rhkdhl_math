import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, time as dt_time
import plotly.express as px
import json
import time

# --- [0. 보안 및 기본 설정] ---
MASTER_PASSWORD = "03241005" 

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

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

if not st.session_state.logged_in:
    login_screen()
    st.stop()

# --- [1. 구글 시트 연결 및 데이터 로직] ---
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
        # 숫자형 컬럼 강제 변환 (오답 통계 포함)
        num_cols = ['id', 'student_id', 'session_num', 'duration', 'hw_result_rate', 
                    'wrong_total', 'err_calc', 'err_concept', 'err_hard', 'err_understand']
        if not df.empty:
            for col in num_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        conn.update(worksheet=worksheet_name, data=df)
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- [2. 세션 초기화 로직] ---
if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
if 'h_rows' not in st.session_state: st.session_state.h_rows = 1
if 'check_rows' not in st.session_state: st.session_state.check_rows = 1

def full_reset():
    for key in list(st.session_state.keys()):
        if key not in ['main_student_selector', 'p_rows', 'h_rows', 'check_rows', 'logged_in']:
            del st.session_state[key]
    st.session_state.p_rows = 1
    st.session_state.h_rows = 1
    st.session_state.check_rows = 1
    st.rerun()

# --- [3. 사이드바 및 학생 선택] ---
with st.sidebar:
    st.title("📑 Tutor Management")
    df_st = load_data("students")
    if not df_st.empty:
        sel_name = st.selectbox("학생 선택", df_st['name'], key="main_student_selector")
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except: s_books = []
    else:
        st.error("등록된 학생이 없습니다.")
        st.stop()

def get_date_with_weekday(date_val):
    if not date_val:
        return ""
    try:
        if isinstance(date_val, str):
            clean_date = date_val.split(" ")[0]
            dt = datetime.strptime(clean_date, "%Y-%m-%d")
        else:
            dt = date_val
            
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        return f"{dt.strftime('%Y-%m-%d')} ({weekdays[dt.weekday()]})"
    except:
        return str(date_val)

tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])
# --- TAB 1: 수업 기록 및 수정 (무한 로딩 + 변수 꼬임 완벽 해결 버전) ---
with tab1:
    def safe_int(val):
        try:
            if pd.isna(val) or val == "" or val is None: return 0
            return int(float(val))
        except: return 0

    # 1. 기본 데이터 로드 및 세션 상태 초기화 보호
    df_se = load_data("sessions")
    if (not df_se.empty) and ('student_id' in df_se.columns):
        all_sessions = df_se[df_se['student_id'] == s_id].sort_values(by='session_num', ascending=False)
    else:
        all_sessions = pd.DataFrame()

    # 동적 행 제어를 위한 초기 세션 변수 안전장치
    if 'check_rows' not in st.session_state: st.session_state.check_rows = 1
    if 'p_rows' not in st.session_state: st.session_state.p_rows = 1
    if 'h_rows' not in st.session_state: st.session_state.h_rows = 1

    # 수정 모드 체크 및 고유 접미사 생성
    is_edit_mode = st.session_state.get('edit_id') is not None
    edit_suffix = f"_edit_{st.session_state.edit_id}" if is_edit_mode else ""
    
    col_status, col_reset = st.columns([4, 1])
    if is_edit_mode: 
        col_status.warning(f"🔄 **{int(st.session_state.edit_session_num)}회차 수정 중**")
    if col_reset.button("🔄 내용 초기화", key="btn_full_reset"): 
        full_reset()

    # --- [전역 파서] 다음 숙제(next_hw) 가변 행 데이터 분리 처리 ---
    parsed_h_books, parsed_h_starts, parsed_h_ends, parsed_h_notes = [], [], [], []
    for i in range(st.session_state.h_rows):
        e_h = st.session_state.get(f"edit_h_val_{i}", "")
        def_hb = s_books[0] if s_books else "미등록"
        def_start, def_end, def_note = "", "", ""
        
        if ":" in e_h:
            def_hb = e_h.split(":")[0].strip()
            rem = e_h.split(":")[1].strip().replace("p.", "")
            
            # 비고/코멘트 분리
            if "(" in rem:
                page_part, note_part = rem.split("(", 1)
                def_note = note_part.replace(")", "").strip()
                page_part = page_part.strip()
            else:
                page_part = rem.strip()
            
            # 페이지 번호 추출 및 파싱 ('번' 문자 제거 후 검사)
            clean_page = page_part.replace("번", "").strip()
            if "~" in clean_page:
                p_split = clean_page.split("~")
                def_start, def_end = p_split[0].strip(), p_split[1].strip()
                if not def_start.isdigit() and not def_end.isdigit():
                    def_note, def_start, def_end = page_part, "", ""
            else:
                if clean_page.isdigit(): 
                    def_start = clean_page
                else: 
                    def_note = page_part
                    
        parsed_h_books.append(def_hb)
        parsed_h_starts.append(def_start)
        parsed_h_ends.append(def_end)
        parsed_h_notes.append(def_note)


    # --- 1. 지난 숙제 채점 섹션 ---
    st.write("### ✍️ 지난 숙제 채점")
    
    if not all_sessions.empty:
        # 최근 2회차만 정렬하여 가져오기
        recent_sessions = all_sessions.sort_values(by=['date', 'session_num'], ascending=False).head(2)
        
        hw_options = {
            f"[{int(row['session_num'])}회차] {get_date_with_weekday(row['date'])} : {row['next_hw']}": row['next_hw'] 
            for _, row in recent_sessions.iterrows()
        }
        
        # 💡 [콜백 엔지니어링] 무한 루프 차단 및 데이터 동기화 즉시 반영 함수
       # 💡 [콜백 엔지니어링] 다음 숙제 칸 침범 문제를 해결한 채점 전용 콜백 함수
        def apply_old_homework_callback():
            target_label = st.session_state.get("sb_apply_old_hw_track")
            if target_label and target_label != "선택 안 함":
                actual_hw = hw_options[target_label]
                hw_parts = actual_hw.split(" | ") if " | " in actual_hw else [actual_hw]
                    
                # 1. 오직 채점 행(check_rows)의 개수만 맞춥니다. (다음 숙제 h_rows는 건드리지 않음)
                st.session_state.check_rows = len(hw_parts)
                
                # 2. 채점용 데이터 세션에만 값을 주입합니다.
                for i, part in enumerate(hw_parts): 
                    st.session_state[f"edit_c_val_{i}"] = part.strip()
                    
                    # 채점 UI 컴포넌트 강제 동기화 데이터 파싱
                    raw_val = part.strip()
                    if ":" in raw_val:
                        p_book = raw_val.split(":")[0].strip()
                        p_rem = raw_val.split(":")[1].strip()
                        p_range, p_total, p_done = p_rem, 0, 0
                        if "(" in p_rem:
                            p_range = p_rem.split("(")[0].strip()
                            p_score = p_rem.split("(")[1].replace(")", "").strip()
                            if "/" in p_score:
                                try:
                                    p_done = int(p_score.split("/")[0].strip())
                                    p_total = int(p_score.split("/")[1].strip())
                                except ValueError: pass 
                        
                        # 채점 컴포넌트 State만 업데이트
                        st.session_state[f"cb_{i}{edit_suffix}"] = p_book
                        st.session_state[f"cr_{i}{edit_suffix}"] = p_range
                        st.session_state[f"ct_{i}{edit_suffix}"] = p_total
                        st.session_state[f"cd_{i}{edit_suffix}"] = p_done
                
                # 불러오기가 끝나면 셀렉트박스를 자동으로 "선택 안 함"으로 리셋
                st.session_state["sb_apply_old_hw_track"] = "선택 안 함"

        # 셀렉트박스 출력
        selected_label = st.selectbox(
            "📥 이전 숙제 불러오기", 
            ["선택 안 함"] + list(hw_options.keys()),
            key="sb_apply_old_hw_track"
        )
        
        if selected_label != "선택 안 함":
            st.button("적용하기", key="btn_apply_old_hw_unique_callback", on_click=apply_old_homework_callback)
        
    no_hw = st.checkbox("✅ 숙제 없음", key="no_hw_check", value=st.session_state.get('edit_no_hw', False))
    check_list, acc_total, acc_done = [], 0, 0
    
    if not no_hw:
        for i in range(st.session_state.check_rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            e_val = st.session_state.get(f"edit_c_val_{i}", "")
            
            def_book = s_books[0] if s_books else "미등록"
            def_range = ""
            def_total_q = 0
            def_done_q = 0
            
            if ":" in e_val:
                def_book = e_val.split(":")[0].strip()
                rem_part = e_val.split(":")[1].strip()
                
                if "(" in rem_part:
                    def_range = rem_part.split("(")[0].strip()
                    score_part = rem_part.split("(")[1].replace(")", "").strip()
                    if "/" in score_part:
                        try:
                            def_done_q = int(score_part.split("/")[0].strip())
                            def_total_q = int(score_part.split("/")[1].strip())
                        except:
                            def_done_q, def_total_q = 0, 0
                else:
                    def_range = rem_part
            
            # UI 컴포넌트 바인딩 및 안전 예외 인덱스 처리
            b_idx = s_books.index(def_book) if def_book in s_books else 0
            cb = c1.selectbox(f"교재 {i+1}", s_books, index=b_idx, key=f"cb_{i}{edit_suffix}")
            cr = c2.text_input(f"범위 {i+1}", value=def_range, key=f"cr_{i}{edit_suffix}")
            ct = c3.number_input(f"총", min_value=0, value=def_total_q, key=f"ct_{i}{edit_suffix}") 
            cd = c4.number_input(f"푼", min_value=0, value=def_done_q, key=f"cd_{i}{edit_suffix}")  
            
            if cb and cr: 
                check_list.append(f"{cb}: {cr} ({cd}/{ct})")
            acc_total += ct
            acc_done += cd
        
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
        st.info(f"📊 **이행률: {final_rate}%** (총 {acc_total} 중 {acc_done} 완료)")

        st.write("#### ❌ 숙제 오답 분석")
        w_total = st.number_input("전체 숙제 오답 개수", min_value=0, value=safe_int(st.session_state.get('edit_w_total', 0)), key=f"w_total{edit_suffix}")
        wc1, wc2, wc3, wc4 = st.columns(4)
        w_calc = wc1.number_input("계산실수", min_value=0, value=safe_int(st.session_state.get('edit_w_calc', 0)), key=f"w_calc{edit_suffix}")
        w_concept = wc2.number_input("개념부족", min_value=0, value=safe_int(st.session_state.get('edit_w_concept', 0)), key=f"w_concept{edit_suffix}")
        w_hard = wc3.number_input("고난도", min_value=0, value=safe_int(st.session_state.get('edit_w_hard', 0)), key=f"w_hard{edit_suffix}")
        w_under = wc4.number_input("문제이해", min_value=0, value=safe_int(st.session_state.get('edit_w_under', 0)), key=f"w_under{edit_suffix}")
    else:
        final_rate, w_total, w_calc, w_concept, w_hard, w_under = 100, 0, 0, 0, 0, 0

    c_c1, c_c2 = st.columns(2)
    if c_c1.button("➕ 채점칸 추가", key="btn_add_check"): 
        st.session_state.check_rows += 1
        st.rerun()
    if c_c2.button("➖ 채점칸 제거", key="btn_sub_check"): 
        st.session_state.check_rows = max(1, st.session_state.check_rows - 1)
        st.rerun()


    # --- 2. 데일리 테스트 섹션 ---
    st.divider()
    st.write("### 📝 데일리 테스트 결과")
    edit_t_total = safe_int(st.session_state.get('edit_test_total', 0))
    use_test = st.checkbox("오늘 데일리 테스트 실시", value=(edit_t_total > 0), key=f"use_test{edit_suffix}")
    
    if use_test:
        tc1, tc2, tc3 = st.columns([2, 1, 1])
        t_name = tc1.text_input("테스트 명", value=st.session_state.get('edit_test_name', "단원평가"), key=f"t_name{edit_suffix}")
        t_total = tc2.number_input("T.총 문항", min_value=0, value=safe_int(st.session_state.get('edit_test_total', 0)), key=f"t_total{edit_suffix}")
        t_score = tc3.number_input("T.맞은 개수", min_value=0, value=safe_int(st.session_state.get('edit_test_score', 0)), key=f"t_score{edit_suffix}")
        st.write("❌ 테스트 오답 분석")
        twc1, twc2, twc3, twc4 = st.columns(4)
        t_calc = twc1.number_input("T.계산실수", min_value=0, value=safe_int(st.session_state.get('edit_t_calc', 0)), key=f"t_calc{edit_suffix}")
        t_concept = twc2.number_input("T.개념부족", min_value=0, value=safe_int(st.session_state.get('edit_t_concept', 0)), key=f"t_concept{edit_suffix}")
        t_hard = twc3.number_input("T.고난도", min_value=0, value=safe_int(st.session_state.get('edit_t_hard', 0)), key=f"t_hard{edit_suffix}")
        t_under = twc4.number_input("T.문제이해", min_value=0, value=safe_int(st.session_state.get('edit_t_under', 0)), key=f"t_under{edit_suffix}")
    else:
        t_name, t_total, t_score, t_calc, t_concept, t_hard, t_under = "", 0, 0, 0, 0, 0, 0

    st.divider()


    # --- 3. 오늘 수업 정보 입력 폼 ---
    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if is_edit_mode else datetime.now()
        date_in = c_d.date_input("날짜", d_val, key=f"date_in{edit_suffix}")
        next_s = int(all_sessions['session_num'].max() + 1) if not all_sessions.empty else 1
        sess_num = c_n.number_input("회차", value=int(st.session_state.get('edit_session_num', next_s)), key=f"sess_num{edit_suffix}")
        
        c_t1, c_t2 = st.columns(2)
        def_start_t = dt_time(14, 0)
        def_end_t = dt_time(16, 0)
        
        if is_edit_mode:
            try:
                s_raw = str(st.session_state.get('edit_start_time', "14:00")).strip()
                e_raw = str(st.session_state.get('edit_end_time', "16:00")).strip()
                s_parts = s_raw.split(":")
                e_parts = e_raw.split(":")
                if len(s_parts) >= 2: def_start_t = dt_time(int(s_parts[0]), int(s_parts[1]))
                if len(e_parts) >= 2: def_end_t = dt_time(int(e_parts[0]), int(e_parts[1]))
            except: pass

        start_t = c_t1.time_input("시작", def_start_t, key=f"start_t{edit_suffix}")
        end_t = c_t2.time_input("종료", def_end_t, key=f"end_t{edit_suffix}")

        p_list, h_list = [], []
        st.write("📖 진도")
        for i in range(st.session_state.p_rows):
            cc1, cc2 = st.columns([1, 2])
            e_p = st.session_state.get(f"edit_p_val_{i}", "")
            def_pb = e_p.split(":")[0] if ":" in e_p else (s_books[0] if s_books else "미등록")
            def_pr = e_p.split(":")[1].strip() if ":" in e_p else ""
            
            p_idx = s_books.index(def_pb) if def_pb in s_books else 0
            pb = cc1.selectbox(f"진도 {i+1}", s_books, index=p_idx, key=f"pb_{i}{edit_suffix}")
            pr = cc2.text_input(f"진도 범위", value=def_pr, key=f"pr_{i}{edit_suffix}")
            if pb and pr: p_list.append(f"{pb}: {pr}")
        
        st.write("📝 다음 숙제")
        for i in range(st.session_state.h_rows):
            st.markdown(f"**📍 숙제 {i+1}**")
            hc1, hc2, hc3, hc4 = st.columns([2, 1, 1, 3])
            
            curr_hb = parsed_h_books[i] if i < len(parsed_h_books) else (s_books[0] if s_books else "미등록")
            curr_start = parsed_h_starts[i] if i < len(parsed_h_starts) else ""
            curr_end = parsed_h_ends[i] if i < len(parsed_h_ends) else ""
            curr_note = parsed_h_notes[i] if i < len(parsed_h_notes) else ""
            
            h_idx = s_books.index(curr_hb) if curr_hb in s_books else 0
            hb = hc1.selectbox(f"교재", s_books, index=h_idx, key=f"hb_{i}{edit_suffix}")
            h_start = hc2.text_input(f"시작(p)", value=curr_start, key=f"h_start_{i}{edit_suffix}", placeholder="12")
            h_end = hc3.text_input(f"끝(p)", value=curr_end, key=f"h_end_{i}{edit_suffix}", placeholder="18")
            h_note = hc4.text_input(f"비고/코멘트", value=curr_note, key=f"h_note_{i}{edit_suffix}", placeholder="홀수만")
            
            if hb and (h_start or h_end or h_note):
                prefix = "p." if (h_start.isdigit() or h_end.isdigit()) else ""
                page_str = f"{prefix}{h_start}" if h_start else ""
                if h_end: 
                    if page_str: page_str += f"~{h_end}"
                    else: page_str = f"{prefix}~{h_end}"
                
                # 중복 '번' 추가 제어 스크립트 보강
                if ("번" not in page_str) and (any(x in hb for x in ["쎈", "라이트쎈", "RPM", "플러스"])):
                    if page_str and not page_str.endswith("번"): page_str += "번"
                    
                note_str = f" ({h_note})" if h_note else ""
                h_list.append(f"{hb}: {page_str}{note_str}".strip())

        fback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""), key=f"fb_text{edit_suffix}")
        
        if st.form_submit_button("💾 저장하기"):
            dur = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
            new_id = int(st.session_state.edit_id) if is_edit_mode else (int(df_se['id'].max()+1) if not df_se.empty else 1)
            new_row = {
                'id': new_id, 'student_id': s_id, 'date': str(date_in), 'session_num': int(sess_num),
                'start_time': start_t.strftime("%H:%M"), 'end_time': end_t.strftime("%H:%M"), 'duration': int(dur),
                'hw_detail': " | ".join(check_list), 'progress': " | ".join(p_list),
                'hw_result_rate': int(final_rate), 'next_hw': " | ".join(h_list), 'feedback': fback,
                'wrong_total': w_total, 'err_calc': w_calc, 'err_concept': w_concept, 'err_hard': w_hard, 'err_understand': w_under,
                'test_name': t_name, 'test_total': t_total, 'test_score': t_score,
                'test_calc': t_calc, 'test_concept': t_concept, 'test_hard': t_hard, 'test_under': t_under
            }
            if is_edit_mode: df_se = df_se[df_se['id'] != st.session_state.edit_id]
            save_data(pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True), "sessions")
            st.success("저장되었습니다!")
            time.sleep(1)
            full_reset()

    # 동적 행 제어 버튼 리팩토링 및 가독성 최적화
    col_p1, col_p2, col_h1, col_h2 = st.columns(4)
    if col_p1.button("➕ 진도칸+", key="btn_add_progress"): 
        st.session_state.p_rows += 1
        st.rerun()
    if col_p2.button("➖ 진도칸-", key="btn_sub_progress"): 
        st.session_state.p_rows = max(1, st.session_state.p_rows - 1)
        st.rerun()
    if col_h1.button("➕ 숙제칸+", key="btn_add_hw"): 
        st.session_state.h_rows += 1
        st.rerun()
    if col_h2.button("➖ 숙제칸-", key="btn_sub_hw"): 
        st.session_state.h_rows = max(1, st.session_state.h_rows - 1)
        st.rerun()
# --- TAB 2: 학습 분석 ---
with tab2:
    st.subheader("📊 월별 상세 학습 통계")
    df_ana = df_se[df_se['student_id'] == s_id].copy()
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        df_ana['year_month'] = df_ana['date'].dt.strftime('%Y-%m')
        selected_month = st.selectbox("📅 분석할 월 선택", sorted(df_ana['year_month'].unique(), reverse=True))
        df_filtered = df_ana[df_ana['year_month'] == selected_month].sort_values('date')
        
        if not df_filtered.empty:
            df_filtered['x_axis'] = df_filtered['date'].dt.strftime('%m/%d') + " (" + df_filtered['session_num'].astype(int).astype(str) + "회)"
            
            # 1. 숙제 이행률 차트
            st.plotly_chart(px.line(df_filtered, x='x_axis', y='hw_result_rate', markers=True, text='hw_result_rate', title="이행률 추이(%)").update_layout(xaxis_type='category', yaxis_range=[-5, 115]), use_container_width=True)
            
            # 2. 오답 원인 분석 (숙제 vs 테스트 비교)
            st.write(f"### ❌ {selected_month} 오답 원인 분석")
            an_col1, an_col2 = st.columns(2)
            
            with an_col1:
                st.write("**[숙제 오답]**")
                w_sums = df_filtered[['err_calc', 'err_concept', 'err_hard', 'err_understand']].sum()
                if w_sums.sum() > 0:
                    fig_hw_pie = px.pie(values=w_sums.values, names=['계산실수', '개념부족', '고난도', '문제이해'], hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_hw_pie, use_container_width=True)
                else: st.caption("숙제 오답 데이터 없음")
            
            with an_col2:
                st.write("**[테스트 오답]**")
                t_w_sums = df_filtered[['test_calc', 'test_concept', 'test_hard', 'test_under']].sum()
                if t_w_sums.sum() > 0:
                    fig_test_pie = px.pie(values=t_w_sums.values, names=['계산실수', '개념부족', '고난도', '문제이해'], hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
                    st.plotly_chart(fig_test_pie, use_container_width=True)
                else: st.caption("테스트 오답 데이터 없음")

            st.divider()
            # 3. 테스트 점수 리스트
            st.write("📝 **월간 테스트 성적표**")
            df_test_table = df_filtered[df_filtered['test_total'] > 0][['date', 'test_name', 'test_score', 'test_total']]
            if not df_test_table.empty:
                df_test_table['정답률'] = (df_test_table['test_score'] / df_test_table['test_total'] * 100).astype(int).astype(str) + "%"
                st.table(df_test_table)
            else: st.caption("기록된 테스트가 없습니다.")

            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("월평균 이행률", f"{int(df_filtered['hw_result_rate'].mean())}%")
            c2.metric("총 수업시간", f"{int(df_filtered['duration'].sum())}분")
            c3.metric("누적 오답수(숙제)", f"{int(w_sums.sum())}개")
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

# --- TAB 4: 전체 로그 (요일 표시 + 수정 + 학부모 카톡 복원 완결판) ---
with tab4:
    st.subheader("📂 수업 로그 조회")
    if not all_sessions.empty:
        all_sessions['date_dt'] = pd.to_datetime(all_sessions['date'])
        all_sessions['year_month'] = all_sessions['date_dt'].dt.strftime('%Y-%m')
        log_filter = st.selectbox("📅 조회할 월 선택", ["전체 보기"] + sorted(all_sessions['year_month'].unique(), reverse=True), key="log_month_filter")
        
        display_df = all_sessions if log_filter == "전체 보기" else all_sessions[all_sessions['year_month'] == log_filter]

        for idx, row in display_df.iterrows():
            # 요일이 포함된 날짜 문자열 생성
            date_with_day = get_date_with_weekday(row['date'])
            
            # 익스팬더 제목 (.0 제거를 위해 int형 변환)
            label = f"[{int(row['session_num'])}회차] {date_with_day} | 이행률 {row['hw_result_rate']}%"
            with st.expander(label):
                
                col_info1, col_info2 = st.columns(2)
                
                with col_info1:
                    st.markdown("**✅ 숙제 및 오답**")
                    st.text(row['hw_detail'] if row['hw_detail'] else "기록 없음")
                    if row['wrong_total'] > 0:
                        st.caption(f"📍 숙제오답: 총 {int(row['wrong_total'])}개 (계산:{int(row['err_calc'])} / 개념:{int(row['err_concept'])} / 난이도:{int(row['err_hard'])} / 이해:{int(row['err_understand'])})")
                    
                    st.markdown("**📝 데일리 테스트**")
                    if row.get('test_total', 0) > 0:
                        st.write(f" 결과: **{int(row['test_score'])} / {int(row['test_total'])}**")
                        st.caption(f"📍 테스트오답: 계산:{int(row['test_calc'])} / 개념:{int(row['test_concept'])} / 난이도:{int(row['test_hard'])} / 이해:{int(row['test_under'])}")
                    else:
                        st.caption("실시하지 않음")
                        
                with col_info2:
                    st.markdown("**📖 오늘 진도 및 다음 숙제**")
                    st.write(f"⏱️ 수업 시간: {row.get('start_time', '14:00')} ~ {row.get('end_time', '16:00')} ({row.get('duration', 0)}분)")
                    st.text(f"진도: {row['progress']}" if row['progress'] else "진도: 없음")
                    st.text(f"다음 숙제: {row['next_hw']}" if row['next_hw'] else "다음 숙제: 없음")
                    st.markdown("**💬 피드백**")
                    st.info(row['feedback'] if row['feedback'] else "작성된 피드백이 없습니다.")
                
                st.divider()
                
                # --- 📱 학부모 전송용 텍스트 자동 생성 로직 --- ⭐
                # 데일리 테스트 결과 정돈
                if row.get('test_total', 0) > 0:
                    test_str = f"✍️ 데일리 테스트: {int(row['test_score'])}문항 / {int(row['test_total'])}문항 만족"
                else:
                    test_str = "✍️ 데일리 테스트: 미실시"
                
                # 가독성을 극대화한 브리핑 문자열 조립
                parent_message = f"""[수업 브리핑 안내]
안녕하세요, 어머니! 오늘 수업 기록 공유드립니다. 📝

🗓️ 수업 일시: {date_with_day}
🔢 수업 회차: {int(row['session_num'])}회차

📊 지난 숙제 이행률: {row['hw_result_rate']}%
{test_str}

📖 오늘 수업 진도:
{row['progress'] if row['progress'] else "기록 없음"}

📌 다음 숙제 미션:
{row['next_hw'] if row['next_hw'] else "기록 없음"}

💬 선생님 피드백:
{row['feedback'] if row['feedback'] else "오늘도 집중해서 성실하게 수업에 임했습니다."}

궁금하신 점이 있으시면 언제든 편하게 말씀해 주세요. 감사합니다! 😊"""

                # 하단 버튼 배치 (수정하기 / 카톡 복사)
                c_btn1, c_btn2 = st.columns([1, 1])
                
                with c_btn1:
                    # 기존 수정하기 버튼
                    if st.button("📝 수정하기", key=f"edit_log_{row['id']}"):
                        st.session_state.edit_id = row['id']
                        st.session_state.edit_date = row['date']
                        st.session_state.edit_session_num = int(row['session_num'])
                        st.session_state.edit_feedback = row['feedback']
                        st.session_state.edit_start_time = str(row.get('start_time', "14:00"))
                        st.session_state.edit_end_time = str(row.get('end_time', "16:00"))
                        st.session_state.edit_w_total = row.get('wrong_total', 0)
                        st.session_state.edit_w_calc = row.get('err_calc', 0)
                        st.session_state.edit_w_concept = row.get('err_concept', 0)
                        st.session_state.edit_w_hard = row.get('err_hard', 0)
                        st.session_state.edit_w_under = row.get('err_understand', 0)
                        st.session_state.edit_test_name = row.get('test_name', "")
                        st.session_state.edit_test_total = row.get('test_total', 0)
                        st.session_state.edit_test_score = row.get('test_score', 0)
                        st.session_state.edit_t_calc = row.get('test_calc', 0)
                        st.session_state.edit_t_concept = row.get('test_concept', 0)
                        st.session_state.edit_t_hard = row.get('test_hard', 0)
                        st.session_state.edit_t_under = row.get('test_under', 0)
                        
                        if row['hw_detail'] and str(row['hw_detail']).strip():
                            c_parts = str(row['hw_detail']).split(" | ")
                            st.session_state.check_rows = len(c_parts)
                            for i, part in enumerate(c_parts): st.session_state[f"edit_c_val_{i}"] = part.strip()
                        else:
                            st.session_state.check_rows = 1
                            st.session_state["edit_c_val_0"] = ""

                        if row['progress'] and str(row['progress']).strip():
                            p_parts = str(row['progress']).split(" | ")
                            st.session_state.p_rows = len(p_parts)
                            for i, part in enumerate(p_parts): st.session_state[f"edit_p_val_{i}"] = part.strip()
                        else:
                            st.session_state.p_rows = 1
                            st.session_state["edit_p_val_0"] = ""

                        if row['next_hw'] and str(row['next_hw']).strip():
                            h_parts = str(row['next_hw']).split(" | ")
                            st.session_state.h_rows = len(h_parts)
                            for i, part in enumerate(h_parts): st.session_state[f"edit_h_val_{i}"] = part.strip()
                        else:
                            st.session_state.h_rows = 1
                            st.session_state["edit_h_val_0"] = ""
                        
                        st.success("모든 원본 데이터를 성공적으로 백업했습니다. 탭 1로 이동합니다."); time.sleep(0.8); st.rerun()
                
                with c_btn2:
                    # ✨ 대망의 학부모 전송용 텍스트 복사 버튼 (텍스트 영역으로 시각화하여 복사 유도)
                    st.text_area("📱 아래 텍스트를 복사해서 카톡에 붙여넣으세요!", value=parent_message, height=180, key=f"msg_area_{row['id']}")
                    
    else:
        st.info("기록된 수업 로그가 없습니다.")
