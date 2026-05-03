import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, time
import json
import requests
import io

# --- [1. 로그인 설정] ---
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

# --- [2. 노션 및 DB 초기화] ---
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def init_db():
    conn = sqlite3.connect('tutoring_v2026_final.db', check_same_thread=False)
    db_c = conn.cursor()
    db_c.execute('CREATE TABLE IF NOT EXISTS students (name TEXT PRIMARY KEY, books TEXT)')
    db_c.execute('''CREATE TABLE IF NOT EXISTS progress 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, date TEXT, weekday TEXT, 
                  session INTEGER, start_time TEXT, end_time TEXT, duration REAL,
                  homeworks TEXT, progress_list TEXT, solved_problems TEXT, 
                  feedback TEXT, next_hw_list TEXT)''')
    conn.commit()
    return conn, db_c

conn, c = init_db()

# --- [3. 노션 동기화 (데이터 복구) 함수] ---
def sync_from_notion():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    try:
        res = requests.post(url, headers=headers)
        if res.status_code != 200:
            st.error("노션 연결 실패")
            return
        
        pages = res.json().get("results", [])
        if not pages:
            st.info("복구할 데이터가 없습니다.")
            return

        # DB 초기화 후 재삽입
        c.execute("DELETE FROM progress")
        for page in pages:
            p = page["properties"]
            name = p["학생이름"]["select"]["name"]
            date = p["날짜"]["date"]["start"]
            sess = p["회차"]["number"]
            feed = p["피드백"]["rich_text"][0]["text"]["content"] if p["피드백"]["rich_text"] else ""
            
            # 복구 데이터는 세부 표 데이터가 텍스트화 되어있으므로 빈 JSON 처리 (에러 방지)
            empty_j = json.dumps([])
            memo_j = json.dumps([{"요약": "노션에서 복구된 기록입니다. 상세 표는 원본 메시지를 확인하세요."}])
            
            c.execute("""INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, 
                         homeworks, progress_list, solved_problems, feedback, next_hw_list) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (name, date, '월', sess, '14:00', '16:00', 2.0, empty_j, empty_j, memo_j, feed, empty_j))
            c.execute("INSERT OR IGNORE INTO students (name, books) VALUES (?, ?)", (name, json.dumps([])))
        
        conn.commit()
        st.success(f"{len(pages)}개의 데이터를 복구했습니다!")
        st.rerun()
    except Exception as e:
        st.error(f"동기화 중 오류: {e}")

# --- [4. 노션 데이터 전송 함수] ---
def save_to_notion(data):
    hw_txt = "• 숙제 없음" if data['hw_df'].empty else "".join([f"• {r.get('분류','')}: {r.get('푼 문항',0)}/{r.get('총 문항',0)}\n" for _, r in data['hw_df'].iterrows()])
    pr_txt = f"메모: {data['memo']}\n" + "".join([f"• {r.get('분류','')}: {r.get('단원/개념','')}\n" for _, r in data['pr_df'].iterrows()])
    nh_txt = "• 다음 숙제 없음" if data['nhw_df'].empty else "".join([f"• {r.get('분류','')}: {r.get('범위','')}\n" for _, r in data['nhw_df'].iterrows()])

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "학생이름": {"select": {"name": data['name']}},
            "날짜": {"date": {"start": data['date']}},
            "회차": {"number": data['session']},
            "오늘숙제": {"rich_text": [{"text": {"content": hw_txt}}]},
            "수업내용": {"rich_text": [{"text": {"content": pr_txt}}]},
            "다음숙제": {"rich_text": [{"text": {"content": nh_txt}}]},
            "피드백": {"rich_text": [{"text": {"content": data['feedback']}}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

# --- [5. 사이드바 및 세션 관리] ---
st.set_page_config(page_title="수학 과외 관리 v2026", layout="wide")
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0

with st.sidebar:
    st.header("⚙️ 데이터 관리")
    if st.button("🔄 노션 데이터 동기화"): sync_from_notion()
    st.divider()
    
    st.header("👤 학생 관리")
    res = c.execute("SELECT name, books FROM students").fetchall()
    s_list = [r[0] for r in res]
    
    if s_list:
        sel_name = st.selectbox("학생 선택", s_list)
        curr_books = json.loads([r[1] for r in res if r[0] == sel_name][0])
        st.subheader("📚 교재")
        for i, b in enumerate(curr_books):
            col1, col2 = st.columns([4, 1])
            col1.caption(f"• {b}")
            if col2.button("🗑️", key=f"del_{i}"):
                curr_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
                conn.commit(); st.rerun()
        
        new_b = st.text_input("새 교재")
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

# --- [6. 메인 화면 탭] ---
all_recs = pd.read_sql_query(f"SELECT * FROM progress WHERE name='{sel_name}'", conn)
if not all_recs.empty: all_recs['date'] = pd.to_datetime(all_recs['date'])

tab_in, tab_de, tab_ca = st.tabs(["📝 수업 입력", "🔍 기록 상세", "📅 월간 일정"])

# --- TAB 1: 수업 입력 ---
with tab_in:
    u_k = f"{st.session_state.reset_count}"
    c1, c2, c3, c4 = st.columns(4)
    in_date = c1.date_input("날짜", datetime.now(), key=f"d_{u_k}")
    in_sess = c2.number_input("회차", min_value=1, value=1, key=f"s_{u_k}")
    in_st = c3.time_input("시작", time(14,0), key=f"st_{u_k}")
    in_et = c4.time_input("종료", time(16,0), key=f"et_{u_k}")

    st.markdown("##### 1. 오늘 숙제 결과")
    no_hw_t = st.checkbox("확인한 숙제 없음", key=f"nt_{u_k}")
    if not no_hw_t:
        df_hw = st.data_editor(pd.DataFrame(columns=["분류","범위","총 문항","푼 문항","모름"]), num_rows="dynamic", use_container_width=True, key=f"h_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    else: df_hw = pd.DataFrame()

    st.markdown("##### 2. 오늘 진도")
    df_pr = st.data_editor(pd.DataFrame(columns=["분류","단원/개념","특이사항"]), num_rows="dynamic", use_container_width=True, key=f"p_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_memo = st.text_area("수업 피드백 메모", key=f"m_{u_k}")

    st.markdown("##### 3. 다음 숙제")
    no_hw_n = st.checkbox("내준 숙제 없음", key=f"nn_{u_k}")
    if not no_hw_n:
        df_nh = st.data_editor(pd.DataFrame(columns=["분류","범위","세부지시"]), num_rows="dynamic", use_container_width=True, key=f"nh_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    else: df_nh = pd.DataFrame()
    in_feed = st.text_area("학부모 전송 메시지", key=f"f_{u_k}")

    if st.button("💾 저장 및 전송", type="primary", use_container_width=True):
        dur = (datetime.combine(in_date, in_et) - datetime.combine(in_date, in_st)).seconds / 3600
        c.execute("INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, homeworks, progress_list, solved_problems, feedback, next_hw_list) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sel_name, in_date.strftime("%Y-%m-%d"), '월', int(in_sess), in_st.strftime("%H:%M"), in_et.strftime("%H:%M"), dur, df_hw.to_json(orient='records'), df_pr.to_json(orient='records'), json.dumps([{"요약": in_memo}]), in_feed, df_nh.to_json(orient='records')))
        conn.commit()
        save_to_notion({"name": sel_name, "date": in_date.strftime("%Y-%m-%d"), "session": int(in_sess), "hw_df": df_hw, "pr_df": df_pr, "memo": in_memo, "nhw_df": df_nh, "feedback": in_feed})
        st.session_state.reset_count += 1
        st.rerun()

# --- TAB 2: 상세 조회 ---
with tab_de:
    if not all_recs.empty:
        sort_recs = all_recs.sort_values(['date', 'session'], ascending=False)
        v_list = [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in sort_recs.iterrows()]
        sel_v = st.selectbox("기록 선택", v_list)
        row = sort_recs.iloc[v_list.index(sel_v)]
        
        st.markdown(f"### 📍 {sel_v} 수업")
        st.info(f"**학부모 메시지:**\n\n{row['feedback']}")
        
        st.markdown("##### 📝 오늘 숙제 결과")
        try:
            hw_v = pd.read_json(io.StringIO(row['homeworks']))
            if hw_v.empty: st.write("지난 숙제 없음")
            else: st.dataframe(hw_v, use_container_width=True, hide_index=True)
        except: st.write("복구된 데이터입니다.")

        st.markdown("##### 📖 수업 진도")
        try:
            pr_v = pd.read_json(io.StringIO(row['progress_list']))
            st.dataframe(pr_v, use_container_width=True, hide_index=True)
        except: st.write("복구된 데이터입니다.")
        
        st.markdown("##### ✍️ 다음 숙제")
        try:
            nh_v = pd.read_json(io.StringIO(row['next_hw_list']))
            if nh_v.empty: st.write("내준 숙제 없음")
            else: st.dataframe(nh_v, use_container_width=True, hide_index=True)
        except: st.write("복구된 데이터입니다.")

# --- TAB 3: 월간 일정 ---
with tab_ca:
    if not all_recs.empty:
        all_recs['month'] = all_recs['date'].dt.strftime('%Y-%m')
        sel_m = st.selectbox("달 선택", sorted(all_recs['month'].unique(), reverse=True))
        m_data = all_recs[all_recs['month'] == sel_m].sort_values('date', ascending=False)
        for _, r in m_data.iterrows():
            with st.expander(f"📅 {r['date'].strftime('%m/%d')} - {r['session']}회차 수업"):
                st.write("**[진도]**")
                try:
                    st.table(pd.read_json(io.StringIO(r['progress_list'])))
                except: st.write("표 데이터 없음")
                st.write("**[다음 숙제]**")
                try:
                    nh_v = pd.read_json(io.StringIO(r['next_hw_list']))
                    if nh_v.empty: st.write("없음")
                    else: st.table(nh_v)
                except: st.write("표 데이터 없음")
                st.caption(f"메시지: {r['feedback']}")
    else: st.write("기록이 없습니다.")
