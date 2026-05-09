import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import json

# --- [1. 기본 설정 및 DB 초기화] ---
st.set_page_config(page_title="Master Tutor v1", layout="wide")

def init_db():
    conn = sqlite3.connect('my_tutor_core.db', check_same_thread=False)
    c = conn.cursor()
    # 학생 테이블
    c.execute('CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, target TEXT)')
    # 수업 기록 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 student_id INTEGER, 
                 date TEXT, 
                 session_num INTEGER,
                 curriculum TEXT,
                 hw_score INTEGER,
                 hw_note TEXT,
                 class_note TEXT,
                 next_hw TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- [2. 유틸리티 함수] ---
def get_students():
    return pd.read_sql_query("SELECT * FROM students", conn)

def save_session(data):
    query = '''INSERT INTO sessions (student_id, date, session_num, curriculum, hw_score, hw_note, class_note, next_hw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
    c.execute(query, data)
    conn.commit()

# --- [3. 사이드바: 학생 관리] ---
with st.sidebar:
    st.title("👨‍🏫 Tutor Dashboard")
    st.divider()
    
    students_df = get_students()
    
    if not students_df.empty:
        selected_student_name = st.selectbox("학생 선택", students_df['name'])
        student_id = int(students_df[students_df['name'] == selected_student_name]['id'].values[0])
    else:
        st.info("등록된 학생이 없습니다.")
        student_id = None

    with st.expander("➕ 새 학생 등록"):
        new_name = st.text_input("이름")
        new_target = st.text_input("목표 (예: 1등급, 인서울)")
        if st.button("등록"):
            c.execute("INSERT INTO students (name, target) VALUES (?, ?)", (new_name, new_target))
            conn.commit()
            st.rerun()

# --- [4. 메인 화면: 탭 구성] ---
if student_id:
    tab1, tab2, tab3 = st.tabs(["📝 수업 기록", "📊 학습 분석", "📅 히스토리"])

    # --- Tab 1: 수업 기록 (입력 시간 단축형) ---
    with tab1:
        st.subheader(f"✨ {selected_student_name} 학생 수업 기록")
        
        with st.form("session_form", clear_on_submit=True):
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                date = st.date_input("수업 날짜", datetime.now())
            with col2:
                # 마지막 회차 자동 계산
                last_sess = c.execute("SELECT MAX(session_num) FROM sessions WHERE student_id=?", (student_id,)).fetchone()[0]
                session_num = (last_sess + 1) if last_sess else 1
                st.number_input("수업 회차", value=session_num)
            with col3:
                curriculum = st.text_input("오늘의 진도", placeholder="예: 삼각함수의 활용")

            st.divider()
            
            # 숙제 성취도 슬라이더 (일일이 개수 안 적어도 됨)
            st.write("📋 **지난 숙제 성취도**")
            hw_score = st.slider("숙제 완성도 (%)", 0, 100, 80, step=5)
            hw_note = st.text_input("숙제 특이사항 (취약 단원/번호)", placeholder="예: 15번 유형(내심) 반복 오답")
            
            # 수업 내용 및 다음 숙제
            class_note = st.text_area("수업 피드백 (학부모 전송용)", placeholder="오늘 학생의 이해도나 태도를 적어주세요.")
            
            # 다음 숙제 자동 추천 로직
            suggested_hw = ""
            if hw_score < 70:
                suggested_hw = "[자동추천] 지난 단원 오답 재풀이 필수\n"
            next_hw = st.text_area("다음 숙제", value=suggested_hw)

            if st.form_submit_button("🚀 수업 기록 저장"):
                save_session((student_id, date.strftime("%Y-%m-%d"), session_num, curriculum, hw_score, hw_note, class_note, next_hw))
                st.success("기록 완료! 분석 탭에서 확인하세요.")
                st.rerun()

    # --- Tab 2: 학습 분석 (시각화) ---
    with tab2:
        st.subheader("📈 학습 데이터 분석")
        
        # 데이터 불러오기
        df = pd.read_sql_query(f"SELECT * FROM sessions WHERE student_id={student_id} ORDER BY date", conn)
        
        if not df.empty:
            # 1. 성취도 변화 그래프
            fig = px.line(df, x='date', y='hw_score', title='숙제 성취도 추이', markers=True)
            fig.update_layout(yaxis_range=[0, 105])
            st.plotly_chart(fig, use_container_width=True)
            
            # 2. 요약 지표
            m1, m2, m3 = st.columns(3)
            m1.metric("평균 성취도", f"{round(df['hw_score'].mean(), 1)}%")
            m2.metric("총 수업 횟수", f"{len(df)}회")
            m3.metric("최근 성취도", f"{df.iloc[-1]['hw_score']}%", 
                      delta=f"{int(df.iloc[-1]['hw_score'] - (df.iloc[-2]['hw_score'] if len(df)>1 else 0))}%")

            # 3. 오답 키워드 클라우드 형식 (간이)
            st.write("🚩 **집중 관리가 필요한 약점 (최근 기록)**")
            notes = df['hw_note'].dropna().tolist()
            for n in notes[-5:]: # 최근 5개만
                if n: st.warning(f"• {n}")
        else:
            st.info("데이터가 충분하지 않습니다.")

    # --- Tab 3: 히스토리 (학부모 상담용) ---
    with tab3:
        st.subheader("📂 전체 수업 기록목록")
        history_df = pd.read_sql_query(f"SELECT date, session_num, curriculum, hw_score, class_note, next_hw FROM sessions WHERE student_id={student_id} ORDER BY date DESC", conn)
        
        if not history_df.empty:
            # 보기 좋게 컬럼명 변경
            history_df.columns = ['날짜', '회차', '진도', '숙제점수', '피드백', '부여된 숙제']
            st.dataframe(history_df, use_container_width=True, hide_index=True)
            
            # 텍스트로 복사하기 기능 (카톡 전송용)
            if st.button("📱 최신 피드백 복사용 텍스트 생성"):
                latest = history_df.iloc[0]
                msg = f"[{latest['날짜']} 수업 보고서]\n- 회차: {latest['회차']}회차\n- 진도: {latest['진도']}\n- 숙제성취도: {latest['숙제점수']}%\n- 피드백: {latest['피드백']}\n- 다음숙제: {latest['부여된 숙제']}"
                st.code(msg)
        else:
            st.info("기록이 없습니다.")

else:
    st.title("👋 반갑습니다!")
    st.info("왼쪽 사이드바에서 학생을 등록하거나 선택해주세요.")
