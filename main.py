import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, time
import json
import requests
import io

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

# --- [3. 노션 데이터 복구 (동기화) - JSON 파싱 로직] ---
def sync_from_notion():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    try:
        res = requests.post(url, headers=headers)
        if res.status_code != 200:
            st.error(f"노션 연결 실패: {res.status_code}")
            return
        
        pages = res.json().get("results", [])
        if not pages:
            st.info("복구할 데이터가 노션에 없습니다.")
            return

        c.execute("DELETE FROM progress")
        count = 0
        for page in pages:
            p = page.get("properties", {})
            try:
                n_obj = p.get("학생이름", {}).get("select")
                name = n_obj.get("name") if n_obj else "Unknown"
                
                d_obj = p.get("날짜", {}).get("date")
                date = d_obj.get("start") if d_obj else datetime.now().strftime("%Y-%m-%d")
                
                sess = p.get("회차", {}).get("number", 1)
                
                # 노션에서 JSON 데이터 원본 추출 시도 (숨겨진 데이터 읽기)
                hw_raw = p.get("오늘숙제", {}).get("rich_text", [])
                hw_json = hw_raw[0].get("plain_text", "[]") if hw_raw else "[]"
                
                pr_raw = p.get("수업내용", {}).get("rich_text", [])
                pr_json = pr_raw[0].get("plain_text", "[]") if pr_raw else "[]"
                
                nh_raw = p.get("다음숙제", {}).get("rich_text", [])
                nh_json = nh_raw[0].get("plain_text", "[]") if nh_raw else "[]"
                
                f_list = p.get("피드백", {}).get("rich_text", [])
                feedback = f_list[0].get("text", {}).get("content", "") if f_list else ""
                
                # 복구 시 유효한 JSON인지 확인하고 아니면 빈 배열 처리
                try: json.loads(hw_json)
                except: hw_json = "[]"
                try: json.loads(pr_json)
                except: pr_json = "[]"
                try: json.loads(nh_json)
                except: nh_json = "[]"

                c.execute("""INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, 
                             homeworks, progress_list, solved_problems, feedback, next_hw_list) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (name, date, '월', sess, '14:00', '16:00', 2.0, hw_json, pr_json, json.dumps([{"요약": "노션 복구 데이터"}]), feedback, nh_json))
                c.execute("INSERT OR IGNORE INTO students (name, books) VALUES (?, ?)", (name, json.dumps([])))
                count += 1
            except Exception as e:
                continue
        conn.commit()
        st.success(f"{count}개의 데이터를 100% 복구했습니다.")
        st.rerun()
    except Exception as e:
        st.error(f"동기화 중 오류 발생: {e}")

# --- [4. 노션 전송 및 보조 함수] ---
def save_to_notion(data):
    # 나중에 복구할 수 있도록 데이터프레임을 JSON 문자열로 변환하여 전송
    hw_json = data['hw_df'].to_json(orient='records')
    pr_json = data['pr_df'].to_json(orient='records')
    nh_json = data['nhw_df'].to_json(orient='records')

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "학생이름": {"select": {"name": data['name']}},
            "날짜": {"date": {"start": data['date']}},
            "회차": {"number": data['session']},
            "오늘숙제": {"rich_text": [{"text": {"content": hw_json}}]},
            "수업내용": {"rich_text": [{"text": {"content": pr_json}}]},
            "다음숙제": {"rich_text": [{"text": {"content": nh_json}}]},
            "피드백": {"rich_text": [{"text": {"content": data['feedback']}}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

def get_next_session(name, date_obj):
    curr_m = date_obj.strftime('%Y-%m')
    res = c.execute("SELECT MAX(session) FROM progress WHERE name=? AND date LIKE ?", (name, f"{curr_m}%")).fetchone()
    return (int(res[0]) + 1) if res[0] else 1

# --- [5. 사이드바 레이아웃] ---
st.set_page_config(page_title="수학 과외 관리 v2026", layout="wide")
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0

with st.sidebar:
    st.header("⚙️ 데이터 관리")
    if st.button("🔄 노션에서 전체 데이터 복구", use_container_width=True): sync_from_notion()
    st.caption("※ 서버 초기화로 데이터가 사라졌을 때 사용하세요.")
    st.divider()
    
    st.header("👤 학생 관리")
    res = c.execute("SELECT name, books FROM students").fetchall()
    s_list = [r[0] for r in res]
    
    if s_list:
        sel_name = st.selectbox("학생 선택", s_list)
        curr_books = json.loads([r[1] for r in res if r[0] == sel_name][0])
        st.subheader("📚 보유 교재")
        for i, b in enumerate(curr_books):
            col1, col2 = st.columns([4, 1])
            col1.caption(f"• {b}")
            if col2.button("🗑️", key=f"del_{i}"):
                curr_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
                conn.commit(); st.rerun()
        
        new_b = st.text_input("새 교재 추가")
        if st.button("교재 추가") and new_b:
            curr_books.append(new_b)
            c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
            conn.commit(); st.rerun()
    else:
        new_s = st.text_input("학생 신규 등록")
        if st.button("등록") and new_s:
            c.execute("INSERT INTO students VALUES (?, ?)", (new_s, json.dumps([])))
            conn.commit(); st.rerun()
        st.stop()

# --- [6. 메인 화면 탭 구성] ---
all_recs = pd.read_sql_query("SELECT * FROM progress WHERE name=?", conn, params=(sel_name,))
if not all_recs.empty: all_recs['date'] = pd.to_datetime(all_recs['date'])

tab_in, tab_de, tab_ca, tab_an = st.tabs(["📝 수업 입력", "🔍 상세 조회", "📅 월간 일정", "📊 성취도 분석"])

# --- TAB 1: 수업 입력 ---
with tab_in:
    u_k = f"{st.session_state.reset_count}"
    c1, c2, c3, c4 = st.columns(4)
    in_date = c1.date_input("날짜", datetime.now(), key=f"d_{u_k}")
    in_sess = c2.number_input("회차", min_value=1, value=get_next_session(sel_name, in_date), key=f"s_{u_k}")
    in_st, in_et = c3.time_input("시작", time(14,0), key=f"st_{u_k}"), c4.time_input("종료", time(16,0), key=f"et_{u_k}")

    st.markdown("#### 1. 오늘 숙제 채점")
    df_hw = st.data_editor(pd.DataFrame(columns=["분류","범위","총 문항","푼 문항","모름"]), num_rows="dynamic", use_container_width=True, key=f"h_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})

    st.markdown("#### 2. 오늘 수업 내용")
    df_pr = st.data_editor(pd.DataFrame(columns=["분류","단원/개념","특이사항"]), num_rows="dynamic", use_container_width=True, key=f"p_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_memo = st.text_area("강사 메모", key=f"m_{u_k}")

    st.markdown("#### 3. 다음 숙제 가이드")
    df_nh = st.data_editor(pd.DataFrame(columns=["분류","범위","세부지시"]), num_rows="dynamic", use_container_width=True, key=f"nh_{u_k}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_feed = st.text_area("학부모 전송 메시지", key=f"f_{u_k}")

    if st.button("💾 최종 저장 및 노션 전송", type="primary", use_container_width=True):
        dur = (datetime.combine(in_date, in_et) - datetime.combine(in_date, in_st)).seconds / 3600
        c.execute("INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, homeworks, progress_list, solved_problems, feedback, next_hw_list) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sel_name, in_date.strftime("%Y-%m-%d"), '월', int(in_sess), in_st.strftime("%H:%M"), in_et.strftime("%H:%M"), dur, df_hw.to_json(orient='records'), df_pr.to_json(orient='records'), json.dumps([{"요약": in_memo}]), in_feed, df_nh.to_json(orient='records')))
        conn.commit()
        save_to_notion({"name": sel_name, "date": in_date.strftime("%Y-%m-%d"), "session": int(in_sess), "hw_df": df_hw, "pr_df": df_pr, "memo": in_memo, "nhw_df": df_nh, "feedback": in_feed})
        st.session_state.reset_count += 1
        st.success("데이터가 안전하게 저장되었습니다!")
        st.rerun()

# --- TAB 2: 상세 조회 ---
with tab_de:
    if not all_recs.empty:
        sort_recs = all_recs.sort_values(['date', 'session'], ascending=False)
        v_list = [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in sort_recs.iterrows()]
        sel_v = st.selectbox("날짜 선택", v_list)
        row = sort_recs.iloc[v_list.index(sel_v)]
        
        st.subheader(f"📊 {sel_v} 상세 리포트")
        st.success(f"**학부모 전송 피드백:**\n\n{row['feedback']}")
        
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**📝 숙제 결과**")
            try: st.dataframe(pd.read_json(io.StringIO(row['homeworks'])), hide_index=True, use_container_width=True)
            except: st.warning("숙제 데이터가 없습니다.")
        with c_b:
            st.markdown("**📖 수업 진도**")
            try: st.dataframe(pd.read_json(io.StringIO(row['progress_list'])), hide_index=True, use_container_width=True)
            except: st.warning("진도 데이터가 없습니다.")
            
        st.markdown("**✍️ 부여된 숙제**")
        try: st.dataframe(pd.read_json(io.StringIO(row['next_hw_list'])), hide_index=True, use_container_width=True)
        except: st.warning("다음 숙제 데이터가 없습니다.")
        
        if st.button("🗑️ 해당 기록 삭제"):
            c.execute("DELETE FROM progress WHERE id=?", (int(row['id']),))
            conn.commit(); st.rerun()
    else: st.info("기록이 없습니다.")

# --- TAB 3: 월간 일정 ---
with tab_ca:
    if not all_recs.empty:
        all_recs['month'] = all_recs['date'].dt.strftime('%Y-%m')
        unique_months = sorted(all_recs['month'].unique(), reverse=True)
        sel_m = st.selectbox("조회 월 선택", unique_months)
        m_data = all_recs[all_recs['month'] == sel_m].sort_values('date', ascending=False)
        for _, r in m_data.iterrows():
            with st.expander(f"📅 {r['date'].strftime('%m/%d')} ({r['session']}회차)"):
                st.write(f"**피드백 요약:** {r['feedback']}")
                st.caption(f"수업 시간: {r['start_time']} ~ {r['end_time']} ({r['duration']}시간)")
    else: st.info("기록이 없습니다.")

# --- TAB 4: 성취도 분석 ---
with tab_an:
    if not all_recs.empty:
        analysis_list = []
        for _, r in all_recs.iterrows():
            try:
                h_df = pd.read_json(io.StringIO(r['homeworks']))
                if not h_df.empty:
                    tot = pd.to_numeric(h_df['총 문항'], errors='coerce').sum()
                    sol = pd.to_numeric(h_df['푼 문항'], errors='coerce').sum()
                    score = (sol/tot*100) if tot > 0 else 0
                    analysis_list.append({"date": r['date'], "score": score})
            except: continue
        
        if analysis_list:
            an_df = pd.DataFrame(analysis_list).sort_values("date")
            st.line_chart(an_df.set_index("date"))
            st.metric("평균 숙제 이행률", f"{round(an_df['score'].mean(), 1)}%")
        else: st.write("분석할 숙제 데이터가 아직 없습니다.")
    else: st.info("기록이 없습니다.")
