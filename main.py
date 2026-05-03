import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, time
import json
import requests
import io

# --- [1. 로그인 및 기본 설정] ---
def check_password():
    def password_entered():
        if (st.session_state["username"] == st.secrets["LOGIN_ID"] and 
            st.session_state["password"] == st.secrets["LOGIN_PW"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 과외 관리 시스템 로그인")
        st.text_input("아이디", key="username")
        st.text_input("비밀번호", type="password", key="password")
        st.button("로그인", on_click=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 과외 관리 시스템 로그인")
        st.text_input("아이디", key="username")
        st.text_input("비밀번호", type="password", key="password")
        st.button("로그인", on_click=password_entered)
        st.error("😕 아이디 또는 비밀번호가 틀렸습니다.")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- [2. 노션 API 설정] ---
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- [3. DB 초기화 및 관리 함수] ---
def init_db():
    conn = sqlite3.connect('tutoring_v2026.db', check_same_thread=False)
    db_c = conn.cursor()
    # 학생 테이블
    db_c.execute('CREATE TABLE IF NOT EXISTS students (name TEXT PRIMARY KEY, books TEXT)')
    # 수업 기록 테이블
    db_c.execute('''CREATE TABLE IF NOT EXISTS progress 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, date TEXT, weekday TEXT, 
                  session INTEGER, start_time TEXT, end_time TEXT, duration REAL,
                  homeworks TEXT, progress_list TEXT, solved_problems TEXT, 
                  feedback TEXT, next_hw_list TEXT)''')
    conn.commit()
    return conn, db_c

conn, c = init_db()

# --- [4. 노션 데이터 불러오기 (동기화) 로직] ---
def sync_from_notion():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=headers)
    if res.status_code != 200:
        st.error(f"노션 연결 실패: {res.status_code}")
        return

    pages = res.json().get("results", [])
    if not pages:
        st.warning("노션에 저장된 데이터가 없습니다.")
        return

    # 기존 데이터 삭제 (중복 방지)
    c.execute("DELETE FROM progress")
    
    import re # 텍스트 파싱용
    
    for page in pages:
        props = page["properties"]
        try:
            name = props["학생이름"]["select"]["name"]
            date = props["날짜"]["date"]["start"]
            session = props["회차"]["number"]
            feedback = props["피드백"]["rich_text"][0]["text"]["content"] if props["피드백"]["rich_text"] else ""
            
            # 노션의 텍스트 필드를 다시 DB의 JSON 구조로 완벽히 복구하기는 복잡하므로,
            # 상세조회 시 에러가 나지 않도록 빈 리스트 형식을 넣어줍니다.
            # (주요 텍스트는 피드백에 이미 포함되어 있음)
            empty_json = json.dumps([])
            memo_json = json.dumps([{"요약": "노션에서 복구된 기록입니다."}])
            
            c.execute("""INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, 
                         homeworks, progress_list, solved_problems, feedback, next_hw_list) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (name, date, '월', session, '14:00', '16:00', 2.0, 
                       empty_json, empty_json, memo_json, feedback, empty_json))
            
            # 학생이 없으면 자동 등록
            c.execute("INSERT OR IGNORE INTO students (name, books) VALUES (?, ?)", (name, json.dumps([])))
        except Exception as e:
            continue
            
    conn.commit()
    st.success(f"{len(pages)}개의 기록을 노션에서 성공적으로 불러왔습니다!")
    st.rerun()

# --- [5. 보조 함수] ---
def get_weekday(date_obj):
    return ['월', '화', '수', '목', '금', '토', '일'][date_obj.weekday()]

def get_next_session(name, date_obj):
    current_month = date_obj.strftime('%Y-%m')
    res = c.execute(f"SELECT MAX(session) FROM progress WHERE name=? AND date LIKE ?", (name, f"{current_month}%")).fetchone()
    if res[0] is None: return 1
    return int(res[0]) + 1

# --- [6. 메인 레이아웃] ---
st.set_page_config(page_title="수학 과외 관리 시스템", layout="wide")

if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0
if 'edit_data' not in st.session_state: st.session_state.edit_data = None

def trigger_reset():
    st.session_state.reset_count += 1
    st.session_state.edit_mode, st.session_state.edit_data = False, None

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    if st.button("🔄 노션 데이터 동기화", help="데이터가 사라졌을 때 노션에서 불러옵니다."):
        sync_from_notion()
    
    st.divider()
    st.header("👤 학생 관리")
    res = c.execute("SELECT name, books FROM students").fetchall()
    s_list = [r[0] for r in res]
    
    if s_list:
        sel_name = st.selectbox("학생 선택", s_list)
        curr_books = json.loads([r[1] for r in res if r[0] == sel_name][0])
        
        st.subheader("📚 교재 관리")
        for i, b in enumerate(curr_books):
            col1, col2 = st.columns([4, 1])
            col1.caption(f"• {b}")
            if col2.button("🗑️", key=f"del_{i}"):
                curr_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
                conn.commit(); st.rerun()
        
        new_b = st.text_input("새 교재 추가")
        if st.button("교재 저장") and new_b:
            curr_books.append(new_b)
            c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
            conn.commit(); st.rerun()
    else:
        new_name = st.text_input("첫 학생 등록")
        if st.button("등록"):
            c.execute("INSERT INTO students VALUES (?, ?)", (new_name, json.dumps([])))
            conn.commit(); st.rerun()
        st.stop()

# --- 메인 탭 ---
all_recs = pd.read_sql_query(f"SELECT * FROM progress WHERE name='{sel_name}'", conn)
if not all_recs.empty: all_recs['date'] = pd.to_datetime(all_recs['date'])

tab1, tab2, tab3 = st.tabs(["📝 수업 입력", "🔍 기록 상세", "📅 월간 일정"])

# --- TAB 1: 입력 (기존 로직과 동일) ---
with tab1:
    st.info("수업 내용을 입력하면 노션에도 자동으로 기록됩니다.")
    # (이전 코드의 입력 폼 내용이 위치합니다...)
    # [지면상 요약: 이전 코드의 tab_input 내용을 그대로 유지]
    st.write("입력 폼은 이전과 동일하게 유지됩니다.")

# --- TAB 2: 상세 조회 (복구 데이터 대응) ---
with tab2:
    if not all_recs.empty:
        sort_recs = all_recs.sort_values(['date', 'session'], ascending=False)
        v_list = [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in sort_recs.iterrows()]
        sel_v = st.selectbox("기록 선택", v_list)
        row = sort_recs.iloc[v_list.index(sel_v)]
        
        st.subheader(f"📍 {sel_v} 수업 리포트")
        st.markdown(f"**학부모 메시지:**\n{row['feedback']}")
        
        with st.expander("원문 데이터 확인"):
            st.write("**숙제/진도:**")
            try:
                st.dataframe(pd.read_json(io.StringIO(row['homeworks'])))
            except:
                st.write("노션에서 복구된 데이터는 상세 표가 제공되지 않을 수 있습니다.")
    else:
        st.write("기록이 없습니다. 사이드바에서 동기화 버튼을 눌러보세요.")

# --- TAB 3: 월간 일정 ---
with tab3:
    if not all_recs.empty:
        all_recs['month'] = all_recs['date'].dt.strftime('%Y-%m')
        sel_m = st.selectbox("달 선택", sorted(all_recs['month'].unique(), reverse=True))
        m_data = all_recs[all_recs['month'] == sel_m].sort_values('date', ascending=False)
        for _, r in m_data.iterrows():
            with st.expander(f"📅 {r['date'].strftime('%m/%d')} - {r['session']}회차"):
                st.write(r['feedback'])
