import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, time
import json
import requests
import io
import re

# --- [1. 로그인 체크 함수] ---
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

# --- [2. 노션 및 DB 설정] ---
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def init_db():
    conn = sqlite3.connect('tutoring_v2026_pro.db', check_same_thread=False)
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

# --- [3. 강화된 노션 데이터 복구 로직] ---
def parse_notion_text_to_json(text, mode="hw"):
    """더 유연한 텍스트 파싱: 기호가 없거나 형식이 달라도 최대한 추출"""
    if not text: return "[]"
    lines = text.split("\n")
    results = []
    for line in lines:
        line = line.strip().lstrip("•-*").strip() # 불필요한 기호 제거
        if not line: continue
        try:
            if mode == "hw":
                # 숫자 추출 로직 강화 (예: "쎈 10/20", "쎈: 10개 중 5개" 등 대응)
                nums = re.findall(r'\d+', line)
                book = line.split(":")[0].strip() if ":" in line else line.split()[0]
                results.append({
                    "분류": book, "범위": "복구됨", 
                    "총 문항": int(nums[1]) if len(nums) > 1 else (int(nums[0]) if len(nums)==1 else 0), 
                    "푼 문항": int(nums[0]) if len(nums) > 0 else 0, 
                    "모름": 0
                })
            else:
                parts = line.split(":")
                book = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else "내용 복구됨"
                results.append({"분류": book, "단원/개념" if mode=="pr" else "범위": desc, "특이사항" if mode=="pr" else "세부지시": "복구됨"})
        except: continue
    return json.dumps(results, ensure_ascii=False)

def sync_from_notion():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_pages = []
    has_more = True
    next_cursor = None

    # 데이터가 100개 이상일 경우 끝까지 긁어오는 루프 (Pagination)
    with st.spinner("노션에서 전체 데이터를 불러오는 중..."):
        while has_more:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code != 200: break
            data = res.json()
            all_pages.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")

    if not all_pages:
        st.warning("복구할 데이터가 노션에 없습니다.")
        return

    c.execute("DELETE FROM progress")
    count = 0
    for page in all_pages:
        p = page.get("properties", {})
        try:
            # 학생 이름 추출
            n_data = p.get("학생이름", {}).get("select")
            name = n_data.get("name") if n_data else "알 수 없음"
            
            # 날짜 추출
            d_data = p.get("날짜", {}).get("date")
            date = d_data.get("start") if d_data else datetime.now().strftime("%Y-%m-%d")
            
            # 회차 추출
            sess = p.get("회차", {}).get("number", 1)
            
            # 텍스트 추출 (여러 줄 대응)
            def get_text(prop_name):
                texts = p.get(prop_name, {}).get("rich_text", [])
                return "".join([t.get("plain_text", "") for t in texts])

            hw_raw = get_text("오늘숙제")
            pr_raw = get_text("수업내용")
            nh_raw = get_text("다음숙제")
            feed = get_text("피드백")

            # 파싱 및 저장
            hw_j = parse_notion_text_to_json(hw_raw, "hw")
            pr_j = parse_notion_text_to_json(pr_raw, "pr")
            nh_j = parse_notion_text_to_json(nh_raw, "nhw")

            c.execute("""INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, 
                         homeworks, progress_list, solved_problems, feedback, next_hw_list) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (name, date, '월', sess, '14:00', '16:00', 2.0, hw_j, pr_j, "[]", feed, nh_j))
            c.execute("INSERT OR IGNORE INTO students (name, books) VALUES (?, ?)", (name, json.dumps([])))
            count += 1
        except: continue
    
    conn.commit()
    st.success(f"총 {count}개의 기록을 노션에서 100% 복구 완료했습니다.")
    st.rerun()

# --- [4. 노션 저장 및 보조 함수] ---
def save_to_notion(data):
    hw_text = "• 숙제 없음" if data['hw_df'].empty else "\n".join([f"• {r['분류']}: {r['푼 문항']}/{r['총 문항']}" for _, r in data['hw_df'].iterrows()])
    pr_text = "• 내용 없음" if data['pr_df'].empty else "\n".join([f"• {r['분류']}: {r['단원/개념']}" for _, r in data['pr_df'].iterrows()])
    nh_text = "• 다음 숙제 없음" if data['nhw_df'].empty else "\n".join([f"• {r['분류']}: {r['범위']}" for _, r in data['nhw_df'].iterrows()])

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "학생이름": {"select": {"name": data['name']}},
            "날짜": {"date": {"start": data['date']}},
            "회차": {"number": data['session']},
            "오늘숙제": {"rich_text": [{"text": {"content": hw_text}}]},
            "수업내용": {"rich_text": [{"text": {"content": pr_text}}]},
            "다음숙제": {"rich_text": [{"text": {"content": nh_text}}]},
            "피드백": {"rich_text": [{"text": {"content": data['feedback']}}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

def get_next_session(name):
    res = c.execute("SELECT MAX(session) FROM progress WHERE name=?", (name,)).fetchone()
    return (int(res[0]) + 1) if res[0] else 1

# --- [5. 사이드바 및 UI] ---
st.set_page_config(page_title="수학 과외 관리 Pro", layout="wide")
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0

with st.sidebar:
    st.header("⚙️ 시스템 관리")
    if st.button("🔄 노션 데이터 전체 복구 (누락 해결)", use_container_width=True):
        sync_from_notion()
    st.divider()
    
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
        new_b = st.text_input("교재 추가")
        if st.button("추가") and new_b:
            curr_books.append(new_b)
            c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
            conn.commit(); st.rerun()
    else:
        new_s = st.text_input("첫 학생 등록")
        if st.button("학생 등록") and new_s:
            c.execute("INSERT INTO students VALUES (?, ?)", (new_s, json.dumps([])))
            conn.commit(); st.rerun()
        st.stop()

# --- [6. 메인 화면 탭 구성] ---
all_recs = pd.read_sql_query("SELECT * FROM progress WHERE name=?", conn, params=(sel_name,))
if not all_recs.empty:
    all_recs['date'] = pd.to_datetime(all_recs['date'])

tab_in, tab_de, tab_ca, tab_an = st.tabs(["📝 수업 입력", "🔍 상세 조회", "📅 월간 일정", "📊 성취도 분석"])

# --- TAB 1: 수업 입력 ---
with tab_in:
    u_k = f"{st.session_state.reset_count}"
    c1, c2 = st.columns(2)
    in_date = c1.date_input("날짜", datetime.now(), key=f"d_{u_k}")
    in_sess = c2.number_input("회차", min_value=1, value=get_next_session(sel_name), key=f"s_{u_k}")
    
    st.markdown("##### 1. 오늘 숙제 채점")
    df_hw = st.data_editor(pd.DataFrame(columns=["분류","총 문항","푼 문항"]), num_rows="dynamic", use_container_width=True, key=f"h_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    
    st.markdown("##### 2. 수업 진도")
    df_pr = st.data_editor(pd.DataFrame(columns=["분류","단원/개념"]), num_rows="dynamic", use_container_width=True, key=f"p_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    
    st.markdown("##### 3. 다음 숙제 가이드")
    df_nh = st.data_editor(pd.DataFrame(columns=["분류","범위"]), num_rows="dynamic", use_container_width=True, key=f"n_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    
    in_feed = st.text_area("학부모 피드백", key=f"f_{u_k}")

    if st.button("💾 최종 저장 및 노션 전송", type="primary", use_container_width=True):
        c.execute("INSERT INTO progress (name, date, session, homeworks, progress_list, feedback, next_hw_list) VALUES (?,?,?,?,?,?,?)",
                  (sel_name, in_date.strftime("%Y-%m-%d"), int(in_sess), df_hw.to_json(orient='records'), df_pr.to_json(orient='records'), in_feed, df_nh.to_json(orient='records')))
        conn.commit()
        save_to_notion({"name": sel_name, "date": in_date.strftime("%Y-%m-%d"), "session": int(in_sess), "hw_df": df_hw, "pr_df": df_pr, "nhw_df": df_nh, "feedback": in_feed})
        st.session_state.reset_count += 1
        st.success("데이터가 저장되었습니다.")
        st.rerun()

# --- TAB 2: 상세 조회 ---
with tab_de:
    if not all_recs.empty:
        recs = all_recs.sort_values("date", ascending=False)
        sel_v = st.selectbox("조회할 회차 선택", [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in recs.iterrows()])
        
        # 선택된 행 찾기
        sel_date_str = sel_v.split()[0]
        sel_sess_num = int(re.search(r'\((\d+)', sel_v).group(1))
        row = recs[(recs['date'].dt.strftime('%Y-%m-%d') == sel_date_str) & (recs['session'] == sel_sess_num)].iloc[0]

        st.success(f"**피드백 메시지:**\n\n{row['feedback']}")
        c_a, c_b = st.columns(2)
        with c_a:
            st.write("**📝 숙제 결과**")
            try: st.dataframe(pd.read_json(io.StringIO(row['homeworks'])), hide_index=True, use_container_width=True)
            except: st.write("데이터 없음")
        with c_b:
            st.write("**📖 수업 진도**")
            try: st.dataframe(pd.read_json(io.StringIO(row['progress_list'])), hide_index=True, use_container_width=True)
            except: st.write("데이터 없음")
        
        if st.button("🗑️ 해당 기록 삭제"):
            c.execute("DELETE FROM progress WHERE id=?", (int(row['id']),))
            conn.commit(); st.rerun()
    else: st.info("기록이 없습니다.")

# --- TAB 3: 월간 일정 ---
with tab_ca:
    if not all_recs.empty:
        all_recs['월'] = all_recs['date'].dt.strftime('%Y-%m')
        sel_m = st.selectbox("월별 보기", sorted(all_recs['월'].unique(), reverse=True))
        m_data = all_recs[all_recs['월'] == sel_m].sort_values("date", ascending=False)
        for _, r in m_data.iterrows():
            with st.expander(f"📅 {r['date'].strftime('%m/%d')} ({r['session']}회차)"):
                st.write(f"**피드백:** {r['feedback']}")
    else: st.info("기록이 없습니다.")

# --- TAB 4: 성취도 분석 ---
with tab_an:
    if not all_recs.empty:
        an_data = []
        for _, r in all_recs.iterrows():
            try:
                h_df = pd.read_json(io.StringIO(r['homeworks']))
                if not h_df.empty:
                    t_tot = pd.to_numeric(h_df['총 문항']).sum()
                    t_sol = pd.to_numeric(h_df['푼 문항']).sum()
                    rate = (t_sol / t_tot * 100) if t_tot > 0 else 0
                    an_data.append({"date": r['date'], "rate": rate})
            except: continue
        
        if an_data:
            df_an = pd.DataFrame(an_data).sort_values("date")
            st.line_chart(df_an.set_index("date"))
            st.metric("최근 평균 성취도", f"{round(df_an['rate'].mean(), 1)}%")
        else: st.write("성취도를 분석할 숙제 기록이 없습니다.")
    else: st.info("데이터가 없습니다.")
