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
        # 학생 선택과 로그인 정보, 행 개수 정보는 유지
        if key not in ['main_student_selector', 'p_rows', 'h_rows', 'check_rows', 'logged_in']:
            del st.session_state[key]
    st.session_state.p_rows = 1
    st.session_state.h_rows = 1
    st.session_state.check_rows = 1
    st.rerun()

# --- [3. 사이드바 및 학생 선택] ---
with st.sidebar:
    st.title("📑 Tutor Pro v11.0")
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

tab1, tab2, tab3, tab4 = st.tabs(["📝 수업 기록/수정", "📊 학습 분석", "📚 교재 관리", "📂 전체 로그"])

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 수업 로그 조회")
    if not all_sessions.empty:
        all_sessions['date_dt'] = pd.to_datetime(all_sessions['date'])
        all_sessions['year_month'] = all_sessions['date_dt'].dt.strftime('%Y-%m')
        log_filter = st.selectbox("📅 조회할 월 선택", ["전체 보기"] + sorted(all_sessions['year_month'].unique(), reverse=True), key="log_month_filter")
        display_df = all_sessions if log_filter == "전체 보기" else all_sessions[all_sessions['year_month'] == log_filter]

        for _, row in display_df.iterrows():
            # 제목에 테스트 실시 여부 표시
            test_tag = f" | 📝 {row['test_name']}" if row.get('test_total', 0) > 0 else ""
            title = f"📌 {int(row['session_num'])}회차 | {row['date']} | 이행 {int(row['hw_result_rate'])}%{test_tag}"
            
            with st.expander(title):
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
                    st.markdown("**📖 수업 진도**")
                    st.text(row['progress'] if row['progress'] else "기록 없음")
                    st.markdown("**🚀 다음 숙제**")
                    st.text(row['next_hw'] if row['next_hw'] else "숙제 없음")
                
                st.info(f"💬 피드백: {row['feedback']}")
                
                # --- 수정하기 버튼 클릭 시 모든 데이터(테스트 포함) 복원 ---
                if st.button("📝 수정하기", key=f"edit_log_{row['id']}"):
                    # 기본 정보 복원
                    st.session_state.edit_id = row['id']
                    st.session_state.edit_date = row['date']
                    st.session_state.edit_session_num = int(row['session_num'])
                    st.session_state.edit_feedback = row['feedback']
                    
                    # 숙제 오답 데이터 복원
                    st.session_state.edit_w_total = row['wrong_total']
                    st.session_state.edit_w_calc = row['err_calc']
                    st.session_state.edit_w_concept = row['err_concept']
                    st.session_state.edit_w_hard = row['err_hard']
                    st.session_state.edit_w_under = row['err_understand']
                    
                    # 데일리 테스트 데이터 복원
                    st.session_state.edit_test_name = row.get('test_name', "")
                    st.session_state.edit_test_total = row.get('test_total', 0)
                    st.session_state.edit_test_score = row.get('test_score', 0)
                    st.session_state.edit_t_calc = row.get('test_calc', 0)
                    st.session_state.edit_t_concept = row.get('test_concept', 0)
                    st.session_state.edit_t_hard = row.get('test_hard', 0)
                    st.session_state.edit_t_under = row.get('test_under', 0)
                    
                    # 가변 행(진도, 숙제, 채점칸) 개수 및 내용 복원
                    for col, state_key in [('progress', 'p_rows'), ('next_hw', 'h_rows'), ('hw_detail', 'check_rows')]:
                        parts = str(row[col]).split(" | ")
                        st.session_state[state_key] = len(parts)
                        prefix = 'edit_p_val_' if col == 'progress' else ('edit_h_val_' if col == 'next_hw' else 'edit_c_val_')
                        for i, p in enumerate(parts):
                            st.session_state[f"{prefix}{i}"] = p
                    
                    st.success("테스트 데이터를 포함하여 모든 정보를 불러왔습니다. 탭 1로 이동하세요!"); time.sleep(0.8); st.rerun()
    else:
        st.info("로그가 없습니다.")
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

# --- TAB 4: 전체 로그 ---
with tab4:
    st.subheader("📂 수업 로그 조회")
    if not all_sessions.empty:
        all_sessions['date_dt'] = pd.to_datetime(all_sessions['date'])
        all_sessions['year_month'] = all_sessions['date_dt'].dt.strftime('%Y-%m')
        log_filter = st.selectbox("📅 조회할 월 선택", ["전체 보기"] + sorted(all_sessions['year_month'].unique(), reverse=True), key="log_month_filter")
        display_df = all_sessions if log_filter == "전체 보기" else all_sessions[all_sessions['year_month'] == log_filter]

        for _, row in display_df.iterrows():
            # 제목에 테스트 실시 여부 표시
            test_tag = f" | 📝 {row['test_name']}" if row.get('test_total', 0) > 0 else ""
            title = f"📌 {int(row['session_num'])}회차 | {row['date']} | 이행 {int(row['hw_result_rate'])}%{test_tag}"
            
            with st.expander(title):
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
                    st.markdown("**📖 수업 진도**")
                    st.text(row['progress'] if row['progress'] else "기록 없음")
                    
                    st.markdown("**🚀 다음 숙제**")
                    if row['next_hw'] and row['next_hw'] != "숙제 없음":
                        # 로그 화면에서 숙제를 더 가독성 있게 쪼개서 보여주는 뷰어 로직
                        raw_hws = str(row['next_hw']).split(" | ")
                        for idx, hw_item in enumerate(raw_hws):
                            if ":" in hw_item:
                                b_title, b_rem = hw_item.split(":", 1)
                                b_title = b_title.strip()
                                b_rem = b_rem.strip()
                                
                                # 코멘트(괄호) 분리하여 가독성 강화
                                if "(" in b_rem:
                                    b_range, b_note = b_rem.split("(", 1)
                                    b_note = b_note.replace(")", "").strip()
                                    st.markdown(f"{idx+1}. **{b_title}** : {b_range.strip()} 💡 *({b_note})*")
                                else:
                                    st.markdown(f"{idx+1}. **{b_title}** : {b_rem}")
                            else:
                                st.markdown(f"{idx+1}. {hw_item}")
                    else:
                        st.caption("숙제 없음")
                
                st.info(f"💬 피드백: {row['feedback']}")
                
                # --- 수정하기 버튼 클릭 시 모든 데이터(테스트 포함) 복원 ---
                if st.button("📝 수정하기", key=f"edit_log_{row['id']}"):
                    # 기본 정보 복원
                    st.session_state.edit_id = row['id']
                    st.session_state.edit_date = row['date']
                    st.session_state.edit_session_num = int(row['session_num'])
                    st.session_state.edit_feedback = row['feedback']
                    
                    # 숙제 오답 데이터 복원
                    st.session_state.edit_w_total = row['wrong_total']
                    st.session_state.edit_w_calc = row['err_calc']
                    st.session_state.edit_w_concept = row['err_concept']
                    st.session_state.edit_w_hard = row['err_hard']
                    st.session_state.edit_w_under = row['err_understand']
                    
                    # 데일리 테스트 데이터 복원
                    st.session_state.edit_test_name = row.get('test_name', "")
                    st.session_state.edit_test_total = row.get('test_total', 0)
                    st.session_state.edit_test_score = row.get('test_score', 0)
                    st.session_state.edit_t_calc = row.get('test_calc', 0)
                    st.session_state.edit_t_concept = row.get('test_concept', 0)
                    st.session_state.edit_t_hard = row.get('test_hard', 0)
                    st.session_state.edit_t_under = row.get('test_under', 0)
                    
                    # 가변 행(진도, 숙제, 채점칸) 개수 및 내용 복원
                    # (여기서 저장된 문자열이 'edit_h_val_i'에 원본 포맷으로 들어가므로 TAB 1이 알아서 다시 쪼갭니다.)
                    for col, state_key in [('progress', 'p_rows'), ('next_hw', 'h_rows'), ('hw_detail', 'check_rows')]:
                        parts = str(row[col]).split(" | ")
                        st.session_state[state_key] = len(parts)
                        prefix = 'edit_p_val_' if col == 'progress' else ('edit_h_val_' if col == 'next_hw' else 'edit_c_val_')
                        for i, p in enumerate(parts):
                            st.session_state[f"{prefix}{i}"] = p
                    
                    st.success("테스트 데이터를 포함하여 모든 정보를 불러왔습니다. 탭 1로 이동하세요!"); time.sleep(0.8); st.rerun()
    else:
        st.info("로그가 없습니다.")
