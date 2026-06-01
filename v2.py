import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, time as dt_time
import plotly.express as px
from reportlab.platypus import HRFlowable
import json
import time
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import plotly.io as pio
import os

# 리눅스 시스템 내 나눔 폰트 경로를 강제로 매니저에 등록
font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
if fm.findfont(fm.FontProperties(fname=font_path)):
    pio.kaleido.scope.default_font = "NanumGothic"

# 나눔 폰트 경로 찾기
font_files = fm.findSystemFonts(fontpaths=['/usr/share/fonts/truetype/nanum'])
for f in font_files:
    fm.fontManager.addfont(f)

# 폰트 설정 (NanumGothic을 기본으로 설정)
pio.kaleido.scope.default_font = "NanumGothic"
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

# --- [3. 사이드바 및 학생 선택 & 학생 추가] ---
with st.sidebar:
    st.title("📑 Tutor Management")
    
    # 1. 학생 데이터 로드
    df_st = load_data("students")
    
    # ----------------------------------------
    # ✨ [신규 기능] 사이드바 학생 추가 섹션
    # ----------------------------------------
    with st.expander("➕ 새 학생 등록하기", expanded=False):
        with st.form("add_student_form", clear_on_submit=True):
            new_name = st.text_input("학생 이름", placeholder="홍길동")
            new_books_raw = st.text_area("사용 교재 목록 (쉼표로 구분)", placeholder="쎈 중1-1, 라이트쎈, RPM")
            submit_student = st.form_submit_button("➕ 학생 등록")
            
            if submit_student:
                if not new_name.strip():
                    st.error("학생 이름을 입력해주세요.")
                else:
                    # 중복 이름 검사
                    if (not df_st.empty) and (new_name.strip() in df_st['name'].values):
                        st.error("이미 등록된 학생 이름입니다.")
                    else:
                        # 교재 텍스트를 JSON 배열 스트링으로 변환
                        if new_books_raw.strip():
                            book_list = [b.strip() for b in new_books_raw.split(",") if b.strip()]
                        else:
                            book_list = []
                        json_books = json.dumps(book_list, ensure_ascii=False)
                        
                        # 다음 ID 부여
                        next_st_id = int(df_st['id'].max() + 1) if (not df_st.empty and 'id' in df_st.columns) else 1
                        
                        # 새 행 데이터 생성
                        new_st_row = pd.DataFrame([{
                            'id': next_st_id,
                            'name': new_name.strip(),
                            'books': json_books
                        }])
                        
                        # 데이터 병합 및 구글 시트 저장
                        df_st = pd.concat([df_st, new_st_row], ignore_index=True)
                        save_data(df_st, "students")
                        
                        st.success(f"🎉 {new_name} 학생이 등록되었습니다!")
                        time.sleep(1)
                        st.rerun()
    
    st.divider() # 시각적 분리선
    
    # 2. 기존 학생 선택 및 교재 로드
    if not df_st.empty:
        # 학생 목록 선택 박스
        sel_name = st.selectbox("학생 선택", df_st['name'], key="main_student_selector")
        
        # 선택된 학생의 상세 데이터 추출
        s_data = df_st[df_st['name'] == sel_name].iloc[0]
        s_id = int(s_data['id'])
        
        try:
            s_books = json.loads(s_data['books']) if (pd.notna(s_data['books']) and s_data['books'] != "") else []
        except: 
            s_books = []
            
        # UI에 선택된 학생 정보 요약 표시
        st.info(f"👤 **선택된 학생:** {sel_name} (ID: {s_id})")
    else:
        st.error("등록된 학생이 없습니다. 위에서 학생을 먼저 등록해주세요.")
        st.stop()

# --- [날짜 요일 변환 헬퍼 함수] ---
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
# --- TAB 1: 수업 기록 및 수정 (StreamlitAPIException 완벽 해결 버전) ---
with tab1:
    def safe_int(val):
        try:
            if pd.isna(val) or val == "" or val is None: return 0
            return int(float(val))
        except: return 0

    # 1. 기본 데이터 로드
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

    # --- 1. 지난 숙제 채점 섹션 ---
    st.write("### ✍️ 지난 숙제 채점")
    
    if not all_sessions.empty:
        recent_sessions = all_sessions.sort_values(by=['date', 'session_num'], ascending=False).head(2)
        hw_options = {
            f"[{int(row['session_num'])}회차] {get_date_with_weekday(row['date'])} : {row['next_hw']}": row['next_hw'] 
            for _, row in recent_sessions.iterrows()
        }
        
        # 콜백 시점에 데이터 파싱 및 안전 주입
        def apply_old_homework_callback():
            target_label = st.session_state.get("sb_apply_old_hw_track")
            if target_label and target_label != "선택 안 함":
                actual_hw = hw_options[target_label]
                hw_parts = actual_hw.split(" | ") if " | " in actual_hw else [actual_hw]
                    
                st.session_state.check_rows = len(hw_parts)
                
                for i, part in enumerate(hw_parts): 
                    raw_val = part.strip()
                    cb_val, start_val, end_val, note_val, done_val = (s_books[0] if s_books else "미등록"), "", "", "", 0
                    
                    if ":" in raw_val:
                        cb_val = raw_val.split(":")[0].strip()
                        rem = raw_val.split(":")[1].strip().replace("p.", "")
                        
                        if "(" in rem:
                            page_part, score_part = rem.split("(", 1)
                            score_part = score_part.replace(")", "").strip()
                            page_part = page_part.strip()
                            
                            if "/" in score_part:
                                try: done_val = int(score_part.split("/")[0].strip())
                                except: pass
                            else: note_val = score_part
                        else:
                            page_part = rem.strip()
                        
                        clean_page = page_part.replace("번", "").strip()
                        if "~" in clean_page:
                            p_split = clean_page.split("~")
                            start_val, end_val = p_split[0].strip(), p_split[1].strip()
                        else:
                            if clean_page.isdigit(): start_val = clean_page
                            else: note_val = page_part
                    
                    cal_total = 0
                    if start_val.isdigit() and end_val.isdigit():
                        cal_total = max(0, int(end_val) - int(start_val) + 1)
                    
                    # 컴포넌트 Key에 직접 안전 값 셋팅 (렌더링 전 시점이라 여기선 안전합니다)
                    st.session_state[f"cb_{i}{edit_suffix}"] = cb_val
                    st.session_state[f"c_start_{i}{edit_suffix}"] = start_val
                    st.session_state[f"c_end_{i}{edit_suffix}"] = end_val
                    st.session_state[f"c_note_{i}{edit_suffix}"] = note_val
                    st.session_state[f"ct_{i}{edit_suffix}"] = cal_total  
                    st.session_state[f"cd_{i}{edit_suffix}"] = done_val
                
                st.session_state["sb_apply_old_hw_track"] = "선택 안 함"

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
            st.markdown(f"**📝 채점 {i+1}**")
            cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([2, 1, 1, 2, 1, 1])
            
            # 수정 모드(과거 기록 편집 클릭) 시 데이터 백업 파싱 로직
            e_c = st.session_state.get(f"edit_c_val_{i}", "")
            if e_c and f"cb_{i}{edit_suffix}" not in st.session_state:
                cb_init, start_init, end_init, note_init, done_init, total_init = (s_books[0] if s_books else "미등록"), "", "", "", 0, 0
                if ":" in e_c:
                    cb_init = e_c.split(":")[0].strip()
                    rem = e_c.split(":")[1].strip().replace("p.", "")
                    if "(" in rem:
                        page_part, score_part = rem.split("(", 1)
                        score_part = score_part.replace(")", "").strip()
                        page_part = page_part.strip()
                        if "/" in score_part:
                            try: 
                                score_split = score_part.split("/")
                                done_init = int(score_split[0].strip())
                                total_init = int(score_split[1].strip())
                            except: pass
                        else: note_init = score_part
                    else:
                        page_part = rem.strip()
                    
                    clean_page = page_part.replace("번", "").strip()
                    if "~" in clean_page:
                        p_split = clean_page.split("~")
                        start_init, end_init = p_split[0].strip(), p_split[1].strip()
                    else:
                        if clean_page.isdigit(): start_init = clean_page
                        else: note_init = page_part
                
                if total_init == 0 and start_init.isdigit() and end_init.isdigit():
                    total_init = max(0, int(end_init) - int(start_init) + 1)

                st.session_state[f"cb_{i}{edit_suffix}"] = cb_init
                st.session_state[f"c_start_{i}{edit_suffix}"] = start_init
                st.session_state[f"c_end_{i}{edit_suffix}"] = end_init
                st.session_state[f"c_note_{i}{edit_suffix}"] = note_init
                st.session_state[f"ct_{i}{edit_suffix}"] = total_init
                st.session_state[f"cd_{i}{edit_suffix}"] = done_init

            # 세션에서 값 불러오기
            v_cb = st.session_state.get(f"cb_{i}{edit_suffix}", (s_books[0] if s_books else "미등록"))
            v_start = st.session_state.get(f"c_start_{i}{edit_suffix}", "")
            v_end = st.session_state.get(f"c_end_{i}{edit_suffix}", "")
            v_note = st.session_state.get(f"c_note_{i}{edit_suffix}", "")
            v_total = st.session_state.get(f"ct_{i}{edit_suffix}", 0)
            v_done = st.session_state.get(f"cd_{i}{edit_suffix}", 0)

            # UI 컴포넌트 배치
            b_idx = s_books.index(v_cb) if v_cb in s_books else 0
            cb = cc1.selectbox(f"교재", s_books, index=b_idx, key=f"cb_{i}{edit_suffix}")
            c_start = cc2.text_input(f"시작(p)", value=v_start, key=f"c_start_{i}{edit_suffix}")
            c_end = cc3.text_input(f"끝(p)", value=v_end, key=f"c_end_{i}{edit_suffix}")
            c_note = cc4.text_input(f"비고/코멘트", value=v_note, key=f"c_note_{i}{edit_suffix}")
            
            # 💡 [핵심 교정] 수동 입력 혹은 주입된 상태값을 기반으로 실시간 계산 판정 유연화
            auto_total = v_total
            if c_start.isdigit() and c_end.isdigit():
                auto_total = max(0, int(c_end) - int(c_start) + 1)
            elif v_total > 0:
                auto_total = v_total
            
            # 💡 에러의 원인이던 수동 세션 대입(=) 구문을 완전히 걷어내고 컴포넌트 자체 연동으로 처리
            ct = cc5.number_input(f"총", min_value=0, value=int(auto_total), key=f"ct_{i}{edit_suffix}")
            cd = cc6.number_input(f"푼", min_value=0, value=int(v_done), key=f"cd_{i}{edit_suffix}")

            if cb and (c_start or c_end or c_note):
                prefix = "p." if (c_start.isdigit() or c_end.isdigit()) else ""
                page_str = f"{prefix}{c_start}" if c_start else ""
                if c_end: 
                    if page_str: page_str += f"~{c_end}"
                    else: page_str = f"{prefix}~{c_end}"
                
                    
                note_str = f" ({c_note})" if c_note else ""
                check_list.append(f"{cb}: {page_str}{note_str} ({cd}/{ct})")
                acc_total += ct
                acc_done += cd
        
        final_rate = int((acc_done / acc_total * 100)) if acc_total > 0 else 100
        st.info(f"📊 **이행률: {final_rate}%** (총 {acc_total}페이지/문항 중 {acc_done} 완료)")

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


  # --- 3. 오늘 수업 정보 입력 폼 (시차 교정 및 월별 회차 리셋 반영) ---
    with st.form("lesson_form"):
        st.write("### 📖 오늘 수업 정보")
        c_d, c_n = st.columns(2)
        
        # ⏰ [시차 교정] 서버의 세계 표준시(UTC)를 한국 표준시(KST)로 변환 (+9시간)
        # 6월 1일 오전인데 5월 31일로 뜨는 현상을 완벽하게 해결합니다.
        import datetime as dt
        from datetime import datetime, timedelta
        
        now_kst = datetime.utcnow() + timedelta(hours=9)
        
        # 날짜 기본값 설정 (수정 모드면 기존 날짜, 새 글이면 정확한 오늘 한국 날짜)
        d_val = datetime.strptime(st.session_state.edit_date, "%Y-%m-%d") if is_edit_mode else now_kst.date()
        date_in = c_d.date_input("날짜", d_val, key=f"date_in{edit_suffix}")
        
        # 🔢 [월별 회차 자동 리셋 로직] 
        # 선택된 혹은 입력된 날짜의 '연도-월'을 추출합니다 (ex: "2026-06")
        current_ym = date_in.strftime('%Y-%m')
        
        if is_edit_mode:
            # 수정 모드일 때는 기존에 저장했던 회차 번호를 그대로 유지
            next_s = int(st.session_state.get('edit_session_num', 1))
        else:
            if not all_sessions.empty:
                # 1. 전체 데이터의 날짜 컬럼을 시계열로 변환 후 연-월 문자열 생성
                all_sessions_cp = all_sessions.copy()
                all_sessions_cp['date_dt'] = pd.to_datetime(all_sessions_cp['date'], errors='coerce')
                all_sessions_cp['ym'] = all_sessions_cp['date_dt'].dt.strftime('%Y-%m')
                
                # 2. 이번 달(현재 입력 폼의 월)에 해당하는 기존 수업 데이터만 필터링
                monthly_sessions = all_sessions_cp[all_sessions_cp['ym'] == current_ym]
                
                if not monthly_sessions.empty:
                    # 이번 달에 이미 수업 기록이 있다면: 최대 회차 + 1
                    next_s = int(monthly_sessions['session_num'].max() + 1)
                else:
                    # 새로운 달의 첫 수업이라면: 1회차로 산뜻하게 리셋!
                    next_s = 1
            else:
                next_s = 1

        # 계산된 회차 번호를 입력창에 반영
        sess_num = c_n.number_input("회차", value=next_s, key=f"sess_num{edit_suffix}")
        p_list, h_list = [], []
        
        # --- 📖 진도 입력 섹션 (숙제 포맷과 동일하게 컴포넌트 분할) ---
        st.write("### 📖 진도")
        for i in range(st.session_state.p_rows):
            st.markdown(f"**📍 진도 {i+1}**")
            pc1, pc2, pc3, pc4 = st.columns([2, 1, 1, 3])
            
            # [수정 모드 데이터 파싱] 기존에 저장된 "교재: p.시작~끝 (비고)" 텍스트 분해 로직
            e_p = st.session_state.get(f"edit_p_val_{i}", "")
            if e_p and f"pb_{i}{edit_suffix}" not in st.session_state:
                pb_init, p_start_init, p_end_init, p_note_init = (s_books[0] if s_books else "미등록"), "", "", ""
                if ":" in e_p:
                    pb_init = e_p.split(":")[0].strip()
                    rem_p = e_p.split(":")[1].strip().replace("p.", "")
                    if "(" in rem_p:
                        page_part, note_part = rem_p.split("(", 1)
                        p_note_init = note_part.replace(")", "").strip()
                        page_part = page_part.strip()
                    else:
                        page_part = rem_p.strip()
                    
                    clean_page = page_part.replace("번", "").strip()
                    if "~" in clean_page:
                        p_split = clean_page.split("~")
                        p_start_init, p_end_init = p_split[0].strip(), p_split[1].strip()
                    else:
                        if clean_page.isdigit(): p_start_init = clean_page
                        else: p_note_init = page_part
                
                st.session_state[f"pb_{i}{edit_suffix}"] = pb_init
                st.session_state[f"p_start_{i}{edit_suffix}"] = p_start_init
                st.session_state[f"p_end_{i}{edit_suffix}"] = p_end_init
                st.session_state[f"p_note_{i}{edit_suffix}"] = p_note_init

            v_pb = st.session_state.get(f"pb_{i}{edit_suffix}", (s_books[0] if s_books else "미등록"))
            v_pstart = st.session_state.get(f"p_start_{i}{edit_suffix}", "")
            v_pend = st.session_state.get(f"p_end_{i}{edit_suffix}", "")
            v_pnote = st.session_state.get(f"p_note_{i}{edit_suffix}", "")

            p_idx = s_books.index(v_pb) if v_pb in s_books else 0
            pb = pc1.selectbox(f"교재", s_books, index=p_idx, key=f"pb_{i}{edit_suffix}")
            p_start = pc2.text_input(f"시작(p)", value=v_pstart, key=f"p_start_{i}{edit_suffix}", placeholder="12")
            p_end = pc3.text_input(f"끝(p)", value=v_pend, key=f"p_end_{i}{edit_suffix}", placeholder="18")
            p_note = pc4.text_input(f"비고/코멘트", value=v_pnote, key=f"p_note_{i}{edit_suffix}", placeholder="개념 설명")
            
            # 데이터 병합 후 리스트에 추가
            if pb and (p_start or p_end or p_note):
                p_prefix = "p." if (p_start.isdigit() or p_end.isdigit()) else ""
                p_page_str = f"{p_prefix}{p_start}" if p_start else ""
                if p_end: 
                    if p_page_str: p_page_str += f"~{p_end}"
                    else: p_page_str = f"{p_prefix}~{p_end}"
                    
                p_note_str = f" ({p_note})" if p_note else ""
                p_list.append(f"{pb}: {p_page_str}{p_note_str}".strip())
        
       # --- 📝 다음 숙제 입력 섹션 ---
        st.write("### 📝 다음 숙제")
        for i in range(st.session_state.h_rows):
            st.markdown(f"**📍 숙제 {i+1}**")
            hc1, hc2, hc3, hc4 = st.columns([2, 1, 1, 3])
            
            e_h = st.session_state.get(f"edit_h_val_{i}", "")
            if e_h and f"hb_{i}{edit_suffix}" not in st.session_state:
                hb_init, h_start_init, h_end_init, h_note_init = (s_books[0] if s_books else "미등록"), "", "", ""
                if ":" in e_h:
                    hb_init = e_h.split(":")[0].strip()
                    rem = e_h.split(":")[1].strip().replace("p.", "")
                    if "(" in rem:
                        page_part, note_part = rem.split("(", 1)
                        h_note_init = note_part.replace(")", "").strip()
                        page_part = page_part.strip()
                    else:
                        page_part = rem.strip()
                    
                    clean_page = page_part.replace("번", "").strip()
                    if "~" in clean_page:
                        p_split = clean_page.split("~")
                        h_start_init, h_end_init = p_split[0].strip(), p_split[1].strip()
                    else:
                        if clean_page.isdigit(): h_start_init = clean_page
                        else: h_note_init = page_part
                
                st.session_state[f"hb_{i}{edit_suffix}"] = hb_init
                st.session_state[f"h_start_{i}{edit_suffix}"] = h_start_init
                st.session_state[f"h_end_{i}{edit_suffix}"] = h_end_init
                st.session_state[f"h_note_{i}{edit_suffix}"] = h_note_init

            v_hb = st.session_state.get(f"hb_{i}{edit_suffix}", (s_books[0] if s_books else "미등록"))
            v_hstart = st.session_state.get(f"h_start_{i}{edit_suffix}", "")
            v_hend = st.session_state.get(f"h_end_{i}{edit_suffix}", "")
            v_hnote = st.session_state.get(f"h_note_{i}{edit_suffix}", "")

            h_idx = s_books.index(v_hb) if v_hb in s_books else 0
            hb = hc1.selectbox(f"교재", s_books, index=h_idx, key=f"hb_{i}{edit_suffix}")
            h_start = hc2.text_input(f"시작(p)", value=v_hstart, key=f"h_start_{i}{edit_suffix}", placeholder="12")
            h_end = hc3.text_input(f"끝(p)", value=v_hend, key=f"h_end_{i}{edit_suffix}", placeholder="18")
            h_note = hc4.text_input(f"비고/코멘트", value=v_hnote, key=f"h_note_{i}{edit_suffix}", placeholder="홀수만")
            
            if hb and (h_start or h_end or h_note):
                prefix = "p." if (h_start.isdigit() or h_end.isdigit()) else ""
                page_str = f"{prefix}{h_start}" if h_start else ""
                if h_end: 
                    if page_str: page_str += f"~{h_end}"
                    else: page_str = f"{prefix}~{h_end}"
                    
                note_str = f" ({h_note})" if h_note else ""
                h_list.append(f"{hb}: {page_str}{note_str}".strip())

        fback = st.text_area("피드백", value=st.session_state.get('edit_feedback', ""), key=f"fb_text{edit_suffix}")
        
        # 🚨 [들여쓰기 완전 패치 적용 완료 블록]
        if st.form_submit_button("💾 저장하기"):
            # 'start_t', 'end_t', 'date_in' 변수가 메모리에 안전하게 잡혀있을 때만 시간 계산
            if 'start_t' in locals() and 'end_t' in locals() and start_t and end_t and 'date_in' in locals() and date_in:
                try:
                    dur = (datetime.combine(date_in, end_t) - datetime.combine(date_in, start_t)).seconds // 60
                    if dur > 720: 
                        dur = 0
                except Exception:
                    dur = 0
            else:
                dur = 0 # 예외 발생 시 안전하게 0분 처리로 NameError 차단
                
            new_id = int(st.session_state.edit_id) if is_edit_mode else (int(df_se['id'].max()+1) if not df_se.empty else 1)
            
            new_row = {
                'id': new_id, 'student_id': s_id, 'date': str(date_in) if 'date_in' in locals() else str(datetime.today().date()), 
                'session_num': int(sess_num),
                'start_time': start_t.strftime("%H:%M") if ('start_t' in locals() and start_t) else "00:00", 
                'end_time': end_t.strftime("%H:%M") if ('end_t' in locals() and end_t) else "00:00", 
                'duration': int(dur),
                'hw_detail': " | ".join(check_list), 'progress': " | ".join(p_list),
                'hw_result_rate': int(final_rate), 'next_hw': " | ".join(h_list), 'feedback': fback,
                'wrong_total': w_total, 'err_calc': w_calc, 'err_concept': w_concept, 'err_hard': w_hard, 'err_understand': w_under,
                'test_name': t_name, 'test_total': t_total, 'test_score': t_score,
                'test_calc': t_calc, 'test_concept': t_concept, 'test_hard': t_hard, 'test_under': t_under
            }
               
            if is_edit_mode: 
                df_se = df_se[df_se['id'] != st.session_state.edit_id]
            
            save_data(pd.concat([df_se, pd.DataFrame([new_row])], ignore_index=True), "sessions")
            st.success("저장되었습니다!")
            time.success_sleep = True  # 안전 지연 전처리 대신 time 모듈 호환성 보장
            time.sleep(1)
            full_reset()

    # 동적 행 제어 버튼 영역 (st.form 외부에 정확하게 정렬 배치)
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

# --- TAB 2: 학습 분석 (데일리 테스트 정답률 그래프 + 디자인 완성도 극대화 버전) ---
with tab2:
    st.markdown("## 📊 월별 상세 학습 통계")
    
    df_ana = df_se[df_se['student_id'] == s_id].copy()
    if not df_ana.empty:
        df_ana['date'] = pd.to_datetime(df_ana['date'])
        df_ana['year_month'] = df_ana['date'].dt.strftime('%Y-%m')
        
        selected_month = st.selectbox("📅 분석할 월 선택", sorted(df_ana['year_month'].unique(), reverse=True))
        df_filtered = df_ana[df_ana['year_month'] == selected_month].sort_values('date')
        
        if not df_filtered.empty:
            df_filtered['x_axis'] = df_filtered['date'].dt.strftime('%m/%d') + " (" + df_filtered['session_num'].astype(int).astype(str) + "회)"
            
            # 1. 데이터 기본 통계 집계
            w_sums = df_filtered[['err_calc', 'err_concept', 'err_hard', 'err_understand']].sum()
            t_w_sums = df_filtered[['test_calc', 'test_concept', 'test_hard', 'test_under']].sum()
            avg_hw = int(df_filtered['hw_result_rate'].mean())
            total_dur = int(df_filtered['duration'].sum())
            
            # --- 🤖 AI 월간 종합 피드백 텍스트 생성 ---
            st.markdown("### 🤖 AI 월간 종합 브리핑 룸")
            
            max_hw_err = w_sums.idxmax() if w_sums.sum() > 0 else "none"
            err_mapping = {'err_calc': '계산 실수', 'err_concept': '개념 이해 부족', 'err_hard': '고난도 문항', 'err_understand': '문제 문해력(이해) 부족', 'none': '없음'}
            main_err_name = err_mapping[max_hw_err]
            
            if avg_hw >= 90:
                hw_comment = "과제 수행도가 매우 우수합니다. 자기주도 학습 습관이 잘 잡혀있어 진도를 계획대로 탄탄하게 나가고 있습니다."
                status_star = "⭐⭐⭐⭐⭐ (최우수)"
            elif avg_hw >= 70:
                hw_comment = "과제를 성실히 수행하려는 노력 성향이 보이나, 특정 회차에서 다소 지연되거나 오답 정리가 미흡한 부분이 발생했습니다. 지속적인 독려가 필요합니다."
                status_star = "⭐⭐⭐ (보완 및 독려)"
            else:
                hw_comment = "현재 숙제 이행도가 다소 저조하여 진도 누수 우려가 있습니다. 복습 시간 확보를 위해 가정에서도 함께 체크해 주시면 감사하겠습니다."
                status_star = "⭐ (집중 관리 필요)"

            df_test_table = df_filtered[df_filtered['test_total'] > 0].copy()
            if not df_test_table.empty:
                df_test_table['score_rate'] = (df_test_table['test_score'] / df_test_table['test_total'] * 100).astype(int)
                avg_test_rate = int(df_test_table['score_rate'].mean())
                test_comment = f"이번 달 데일리 테스트 평균 정답률은 {avg_test_rate}%입니다. 개념을 실전 문제에 적용하는 과정에서 주로 [{main_err_name}] 유형의 감점이 두드러졌습니다. 오답 노트를 통해 취약점을 확실히 메우도록 지도 중입니다."
            else:
                avg_test_rate = "기록 없음"
                test_comment = "이번 달 시행된 공식 데일리 테스트 피드백이 없습니다. 평소 단원 평가 성적을 기반으로 개념 다지기에 집중하고 있습니다."

            # 알림톡 텍스트 조립
            report_text = f"""[📊 {selected_month} 월간 학습 성적표 안내]

안녕하세요 학부모님, 수학 과외 선생님입니다. 
이번 달 진행된 종합 학습 통계 및 분석 리포트를 보내드립니다.

━━━━━━━━━━━━━━━━━━━━
📌 1. 월간 핵심 지표 요약
━━━━━━━━━━━━━━━━━━━━
• 월평균 숙제 이행률: {avg_hw}% {status_star}
• 월간 총 수업 시간: {total_dur}분
• 데일리 테스트 평균 정답률: {avg_test_rate if isinstance(avg_test_rate, str) else f"{avg_test_rate}%"}
• 주요 오답 원인 유형: {main_err_name}

━━━━━━━━━━━━━━━━━━━━
📝 2. 담당 교사 종합 총평
━━━━━━━━━━━━━━━━━━━━
• 과제 수행 및 학습 태도:
{hw_comment}

• 테스트 및 취약점 분석:
{test_comment}

항상 믿고 맡겨주셔서 감사드립니다. 다음 달에는 발견된 취약 요소를 완벽하게 극복할 수 있도록 더욱 정밀하게 지도하겠습니다. 

- 수학 교사 올림 -"""

            # 화면에 AI 리포트 출력 및 편집 창
            with st.container(border=True):
                st.markdown(f"#### 📝 **{selected_month} 학부모 브리핑 및 종합 PDF 발행**")
                edited_report = st.text_area("카톡 전송용 텍스트 (수정 가능)", value=report_text, height=220, key=f"ai_rep_{s_id}_{selected_month}")
                
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if st.button("📋 이 알림톡 양식 통째로 복사하기", use_container_width=True):
                        st.write('<script>navigator.clipboard.writeText(`' + edited_report + '`);</script>', unsafe_allow_html=True)
                        st.success("클립보드에 복사되었습니다!")

            st.divider()

            # --- 📌 2. 그래프 객체 생성 및 폰트 사전 세팅 (화면 브리핑용) ---
            if w_sums.sum() > 0:
                fig_hw_pie = px.pie(values=w_sums.values, names=['계산실수', '개념부족', '고난도', '문제이해'], hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_hw_pie.update_layout(margin=dict(t=20, b=20, l=10, r=10), width=350, height=300)
            else: fig_hw_pie = None

            if t_w_sums.sum() > 0:
                fig_test_pie = px.pie(values=t_w_sums.values, names=['계산실수', '개념부족', '고난도', '문제이해'], hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
                fig_test_pie.update_layout(margin=dict(t=20, b=20, l=10, r=10), width=350, height=300)
            else: fig_test_pie = None

            # 📈 그래프 A: 회차별 숙제 이행률 라인
            fig_hw_line = px.line(df_filtered, x='x_axis', y='hw_result_rate', markers=True, text='hw_result_rate', title="📊 회차별 숙제 이행률 추이(%)")
            fig_hw_line.update_layout(xaxis_type='category', yaxis_range=[-5, 115], width=700, height=320)
            fig_hw_line.update_traces(textposition="top center")

            # 📈 그래프 B: 회차별 데일리 테스트 정답률 라인
            if not df_test_table.empty:
                fig_test_line = px.line(df_test_table, x='x_axis', y='score_rate', markers=True, text='score_rate', title="🎯 회차별 데일리 테스트 정답률 추이(%)")
                fig_test_line.update_layout(xaxis_type='category', yaxis_range=[-5, 115], width=700, height=320)
                fig_test_line.update_traces(textposition="top center", line=dict(color='#EF4444', width=3))
            else: fig_test_line = None

            # 📈 그래프 C: 회차별 숙제 오답 원인 누적 바
            if w_sums.sum() > 0:
                df_hw_bar = df_filtered.melt(id_vars=['x_axis'], value_vars=['err_calc', 'err_concept', 'err_hard', 'err_understand'], var_name='오답원인', value_name='개수')
                df_hw_bar['오답원인'] = df_hw_bar['오답원인'].map({'err_calc': '계산실수', 'err_concept': '개념부족', 'err_hard': '고난도', 'err_understand': '문제이해'})
                fig_hw_bar = px.bar(df_hw_bar, x='x_axis', y='개수', color='오답원인', title="📖 회차별 숙제 오답 원인 추이", color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_hw_bar.update_layout(xaxis_type='category', width=700, height=320)
            else: fig_hw_bar = None

            # 📈 그래프 D: 회차별 테스트 오답 원인 누적 바
            if t_w_sums.sum() > 0:
                df_test_bar = df_filtered.melt(id_vars=['x_axis'], value_vars=['test_calc', 'test_concept', 'test_hard', 'test_under'], var_name='오답원인', value_name='개수')
                df_test_bar['오답원인'] = df_test_bar['오답원인'].map({'test_calc': '계산실수', 'test_concept': '개념부족', 'test_hard': '고난도', 'test_under': '문제이해'})
                fig_test_bar = px.bar(df_test_bar, x='x_axis', y='개수', color='오답원인', title="📝 회차별 테스트 오답 원인 추이", color_discrete_sequence=px.colors.qualitative.Safe)
                fig_test_bar.update_layout(xaxis_type='category', width=700, height=320)
            else: fig_test_bar = None


            # --- 📄 [프로페셔널 조판] PDF 생성 내부 로직 보완 ---
            with btn_c2:
                try:
                    import io
                    import urllib.request
                    import copy
                    from reportlab.lib.pagesizes import letter
                    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    from reportlab.lib import colors

                    @st.cache_data
                    def download_pdf_font():
                        url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as res: return res.read()

                    try: pdfmetrics.getFont('NanumGothic')
                    except KeyError: pdfmetrics.registerFont(TTFont('NanumGothic', io.BytesIO(download_pdf_font())))

                    # --- 📄 [프로페셔널 조판] PDF 생성 내부 로직 수정 버전 ---
                    def build_full_report_pdf():
                        pdf_buffer = io.BytesIO()
                        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
                        styles = getSampleStyleSheet()
                        
                        t_style = ParagraphStyle('T1', parent=styles['Heading1'], fontName='NanumGothic', fontSize=18, leading=24, spaceAfter=12, textColor=colors.HexColor('#1E3A8A'))
                        sub_style = ParagraphStyle('T2', parent=styles['Heading2'], fontName='NanumGothic', fontSize=11, leading=15, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor('#1E3A8A'))
                        b_style = ParagraphStyle('B1', parent=styles['Normal'], fontName='NanumGothic', fontSize=9.5, leading=16, spaceAfter=4, textColor=colors.HexColor('#334155'))
                        guide_style = ParagraphStyle('GD', parent=styles['Normal'], fontName='NanumGothic', fontSize=8.5, leading=13, alignment=1, textColor=colors.HexColor('#1E3A8A'))
                        
                        story = []
                    
                        # --- PAGE 1: 숙제 관련 그래프 ---
                        story.append(Paragraph(f"<b>📊 {selected_month} 월간 종합 학습 분석 (1/3)</b>", t_style))
                        
                        upper_block = []
                        lower_block = []
                        
                        if fig_hw_line:
                            pdf_hw_line = copy.deepcopy(fig_hw_line)
                            pdf_hw_line.update_layout(
                                title="회차별 숙제 이행률 (%)",
                                xaxis_title="회차",
                                yaxis_title="이행률 (%)",
                                font=dict(family="NanumGothic", size=10),
                                margin=dict(t=25, b=25)
                            )
                        
                            upper_block.extend([
                                Paragraph("<b>[1] 회차별 숙제 이행률 추이 그래프</b>", sub_style),
                                Image(io.BytesIO(pdf_hw_line.to_image(format="png")), width=500, height=220)
                            ])
                        
                        if fig_hw_bar:
                            pdf_hw_bar = copy.deepcopy(fig_hw_bar)
                            pdf_hw_bar.update_layout(
                                title="회차별 숙제 오답 원인 추이",
                                xaxis_title="회차",
                                yaxis_title="개수",
                                legend_title="오답원인",
                                font=dict(family="NanumGothic", size=10),
                                margin=dict(t=25, b=25)
                            )
                        
                            lower_block.extend([
                                Paragraph("<b>[2] 숙제 회차별 오답 원인 분석 그래프</b>", sub_style),
                                Image(io.BytesIO(pdf_hw_bar.to_image(format="png")), width=500, height=220)
                            ])
                        
                        for item in upper_block:
                            story.append(item)
                        
                        story.append(Spacer(1, 75))
                        
                        divider = HRFlowable(
                            width="100%",
                            thickness=1.5,
                            color=colors.HexColor("#CBD5E1"),
                            spaceBefore=5,
                            spaceAfter=10
                        )
                        
                        story.append(divider)
                        
                        for item in lower_block:
                            story.append(item)
                        
                        story.append(PageBreak())
                        # --- PAGE 2: 테스트 관련 그래프 ---
                        story.append(Paragraph(f"<b>📊 {selected_month} 월간 종합 학습 분석 (2/3)</b>", t_style))
                        
                        upper_block = []
                        lower_block = []
                        
                        if fig_test_line:
                            pdf_test_line = copy.deepcopy(fig_test_line)
                            pdf_test_line.update_layout(
                                title="회차별 데일리 테스트 정답률 추이 (%)",
                                xaxis_title="회차",
                                yaxis_title="정답률 (%)",
                                font=dict(family="NanumGothic", size=10),
                                margin=dict(t=25, b=25)
                            )
                        
                            upper_block.extend([
                                Paragraph("<b>[3] 회차별 데일리 테스트 결과 그래프</b>", sub_style),
                                Image(io.BytesIO(pdf_test_line.to_image(format="png")), width=500, height=220)
                            ])
                        
                        if fig_test_bar:
                            pdf_test_bar = copy.deepcopy(fig_test_bar)
                            pdf_test_bar.update_layout(
                                title="회차별 테스트 오답 원인 추이",
                                xaxis_title="회차",
                                yaxis_title="개수",
                                legend_title="오답원인",
                                font=dict(family="NanumGothic", size=10),
                                margin=dict(t=25, b=25)
                            )
                        
                            lower_block.extend([
                                Paragraph("<b>[4] 데일리 테스트 오답 회차별 통계 그래프</b>", sub_style),
                                Image(io.BytesIO(pdf_test_bar.to_image(format="png")), width=500, height=220)
                            ])
                        
                        for item in upper_block:
                            story.append(item)
                        
                        story.append(Spacer(1, 75))
                        
                        divider = HRFlowable(
                            width="100%",
                            thickness=1.5,
                            color=colors.HexColor("#CBD5E1"),
                            spaceBefore=5,
                            spaceAfter=10
                        )
                        
                        story.append(divider)
                        
                        for item in lower_block:
                            story.append(item)
                        
                        story.append(PageBreak())
                        # --- PAGE 3: 종합 피드백 ---
                        p3_blocks = []
                        p3_blocks.append(Paragraph(f"<b>📊 {selected_month} 월간 종합 학습 분석 (3/3)</b>", t_style))
                        
                        # 5. 파이 차트 (오답 비중)
                        img_pie_list = []
                        if fig_hw_pie:
                            pdf_hw_pie = copy.deepcopy(fig_hw_pie)
                            pdf_hw_pie.update_layout(title="월간 숙제 오답 분포", font=dict(family="NanumGothic", size=10))
                            pdf_hw_pie.update_traces(labels=['계산실수', '개념부족', '고난도', '문제이해'])
                            img_pie_list.append(Image(io.BytesIO(pdf_hw_pie.to_image(format="png")), width=220, height=180))
                        if fig_test_pie:
                            pdf_test_pie = copy.deepcopy(fig_test_pie)
                            pdf_test_pie.update_layout(title="월간 테스트 오답 분포", font=dict(family="NanumGothic", size=10))
                            pdf_test_pie.update_traces(labels=['계산실수', '개념부족', '고난도', '문제이해'])
                            img_pie_list.append(Image(io.BytesIO(pdf_test_pie.to_image(format="png")), width=220, height=180))
                            
                        if img_pie_list:
                            t_charts = Table([img_pie_list], colWidths=[250, 250])
                            p3_blocks.append(Paragraph("<b>[5] 월간 누적 전체 오답 유형 비중 분포</b>", sub_style))
                            p3_blocks.append(t_charts)
                        
                        # 종합 피드백
                        p3_blocks.append(Spacer(1, 20))
                        p3_blocks.append(Paragraph(f"<b>📝 담당 교사 월간 종합 피드백</b>", t_style))
                        f_body = [Paragraph(line.strip(), b_style) for line in edited_report.split('\n') if line.strip() and not any(x in line for x in ['📊', '📌', '📝', '━━━━━━━━━━━━━━━━━━━━'])]
                        t_feedback = Table([[f_body]], colWidths=[520])
                        t_feedback.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')), ('LINELEFT', (0,0), (-1,-1), 4, colors.HexColor('#1E3A8A')), ('PADDING', (0,0), (-1,-1), 10)]))
                        p3_blocks.append(t_feedback)
                        
                        story.append(KeepTogether(p3_blocks))
                        
                        doc.build(story)
                        return pdf_buffer.getvalue()
                    # 다운로드 버튼 매핑
                    st.download_button(
                        label="📄 완벽 조판 종합 학습분석 PDF 다운로드",
                        data=build_full_report_pdf(),
                        file_name=f"{selected_month}_종합_학습분석_리포트.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as ex:
                    st.error(f"⚠️ 종합 PDF 최적화 생성 대기 중... (원인: {str(ex)})")


            # --- 📌 3. 화면 UI 시각화 렌더링 영역 ---
            st.markdown("### 📌 월간 통계 데이터 시각화 (화면 브리핑용)")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📈 월평균 이행률", f"{avg_hw}%")
            m2.metric("⏱️ 총 수업시간", f"{total_dur}분")
            m3.metric("📝 누적 숙제 오답", f"{int(w_sums.sum())}개")
            m4.metric("🔥 누적 테스트 오답", f"{int(t_w_sums.sum())}개")
            
            an_col1, an_col2 = st.columns(2)
            with an_col1:
                st.write("**[📖 월간 숙제 오답 분포]**")
                if fig_hw_pie: st.plotly_chart(fig_hw_pie, use_container_width=True)
                else: st.caption("💡 숙제 오답 데이터가 없습니다.")
            
            with an_col2:
                st.write("**[📝 월간 테스트 오답 분포]**")
                if fig_test_pie: st.plotly_chart(fig_test_pie, use_container_width=True)
                else: st.caption("💡 테스트 오답 데이터가 없습니다.")

            st.divider()
            
            st.markdown("### 📈 회차별 상세 변화 추이")
            # 💡 기존 3개 탭에서 "📝 테스트 정답률" 탭을 추가하여 총 4개 탭 구조로 고도화
            chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs(["✍️ 숙제 이행률", "🎯 테스트 정답률", "📖 숙제 오답 추이", "📝 테스트 오답 추이"])
            
            with chart_tab1:
                st.plotly_chart(fig_hw_line, use_container_width=True)
            if fig_test_line:
                with chart_tab2:
                    st.plotly_chart(fig_test_line, use_container_width=True)
            else:
                with chart_tab2: st.caption("💡 테스트 성적 추이 데이터가 없습니다.")
            if fig_hw_bar:
                with chart_tab3:
                    st.plotly_chart(fig_hw_bar, use_container_width=True)
            else:
                with chart_tab3: st.caption("💡 숙제 오답 추이 데이터가 없습니다.")
            if fig_test_bar:
                with chart_tab4:
                    st.plotly_chart(fig_test_bar, use_container_width=True)
            else:
                with chart_tab4: st.caption("💡 테스트 오답 추이 데이터가 없습니다.")

            st.divider()

            st.markdown("### 🏆 월간 데일리 테스트 리포트")
            if not df_test_table.empty:
                for idx, row in df_test_table.iterrows():
                    t_date = row['date'].strftime('%Y-%m-%d')
                    t_name = row['test_name']
                    t_score = int(row['test_score'])
                    t_total = int(row['test_total'])
                    t_rate = row['score_rate']
                    
                    status_emoji = "🟢 [최우수]" if t_rate >= 90 else "🔵 [양호]" if t_rate >= 70 else "🟡 [보완필요]"
                    
                    with st.expander(f"{status_emoji} {t_date} | **{t_name}** 👉 정답률 {t_rate}%", expanded=True):
                        tc_1, tc_2, tc_3 = st.columns([1, 1, 2])
                        tc_1.metric("맞은 문항 수", f"{t_score} / {t_total} 문항")
                        
                        err_parts = []
                        if row['test_calc'] > 0: err_parts.append(f"계산실수({int(row['test_calc'])})")
                        if row['test_concept'] > 0: err_parts.append(f"개념부족({int(row['test_concept'])})")
                        if row['test_hard'] > 0: err_parts.append(f"고난도({int(row['test_hard'])})")
                        if row['test_under'] > 0: err_parts.append(f"문제이해({int(row['test_under'])})")
                        
                        err_text = ", ".join(err_parts) if err_parts else "틀린 문제 없음 (만점! 💯)"
                        tc_3.markdown(f"🔍 **오답 세부 원인:**\n\n`{err_text}`")
            else: st.info("💡 이번 달에 진행된 데일리 테스트 기록이 존재하지 않습니다.")
                
    else: st.info("📊 학습 분석을 진행할 세션 데이터가 아직 입력되지 않았습니다.")
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
안녕하세요! 오늘 수업 기록 공유드립니다. 📝

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
