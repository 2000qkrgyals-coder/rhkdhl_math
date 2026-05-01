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

def save_to_notion(data):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    hw_summary = "".join([f"• {r.get('분류','')}: {r.get('푼 문항',0)}/{r.get('총 문항',0)} (모름:{r.get('모름',0)})\n" for _, r in data['hw_df'].iterrows()])
    pr_summary = f"메모: {data['memo']}\n" + "".join([f"• {r.get('분류','')}: {r.get('단원/개념','')} ({r.get('특이사항','')})\n" for _, r in data['pr_df'].iterrows()])
    nhw_summary = "".join([f"• {r.get('분류','')}: {r.get('범위','')} ({r.get('세부지시','')})\n" for _, r in data['nhw_df'].iterrows()])

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "학생이름": {"select": {"name": data['name']}},
            "날짜": {"date": {"start": data['date']}},
            "회차": {"number": data['session']},
            "오늘숙제": {"rich_text": [{"text": {"content": hw_summary}}]},
            "수업내용": {"rich_text": [{"text": {"content": pr_summary}}]},
            "다음숙제": {"rich_text": [{"text": {"content": nhw_summary}}]},
            "피드백": {"rich_text": [{"text": {"content": data['feedback']}}]}
        }
    }
    try:
        res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
        return res.status_code
    except: return 500

def init_db():
    conn = sqlite3.connect('tutoring_final_v51.db', check_same_thread=False)
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

def get_weekday(date_obj):
    return ['월', '화', '수', '목', '금', '토', '일'][date_obj.weekday()]

def get_next_session(name, date_obj):
    current_month = date_obj.strftime('%Y-%m')
    res = c.execute(f"SELECT MAX(session) FROM progress WHERE name=? AND date LIKE ?", (name, f"{current_month}%")).fetchone()
    if res[0] is None: return 1
    return int(res[0]) + 1

st.set_page_config(page_title="수학 과외 관리 시스템", layout="wide")

if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'edit_target_id' not in st.session_state: st.session_state.edit_target_id = None
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0
if 'temp_hw_data' not in st.session_state: st.session_state.temp_hw_data = None
if 'edit_data' not in st.session_state: st.session_state.edit_data = None

def trigger_reset():
    st.session_state.reset_count += 1
    st.session_state.edit_mode, st.session_state.edit_target_id, st.session_state.temp_hw_data, st.session_state.edit_data = False, None, None, None

# --- [4. 사이드바] ---
with st.sidebar:
    st.header("👤 학생 및 교재 관리")
    with st.expander("➕ 학생 신규 등록"):
        new_s_name = st.text_input("새 학생 이름", key="reg_new_std")
        if st.button("학생 등록"):
            if new_s_name:
                try:
                    c.execute("INSERT INTO students VALUES (?, ?)", (new_s_name, json.dumps([])))
                    conn.commit(); st.success(f"{new_s_name} 등록 완료!"); st.rerun()
                except: st.error("이미 등록된 이름입니다.")
    
    res = c.execute("SELECT name, books FROM students").fetchall()
    s_list = [r[0] for r in res]
    if not s_list: st.warning("학생을 먼저 등록하세요."); st.stop()

    sel_name = st.selectbox("학생 선택", s_list, index=0)
    curr_books = json.loads([r[1] for r in res if r[0] == sel_name][0])

    st.subheader(f"📚 {sel_name}의 교재")
    for b in curr_books: st.text(f"• {b}")
    nb = st.text_input("새 교재 추가")
    if st.button("교재 저장") and nb:
        curr_books.append(nb)
        c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
        conn.commit(); st.rerun()
    
    st.divider()
    if st.button("🔄 새 수업 입력으로 전환", use_container_width=True): trigger_reset(); st.rerun()

all_recs = pd.read_sql_query(f"SELECT * FROM progress WHERE name='{sel_name}'", conn)
all_recs['date'] = pd.to_datetime(all_recs['date'])

# --- [5. 메인 화면] ---
st.title(f"📖 {sel_name} 학생 관리")
tab_input, tab_search, tab_analysis = st.tabs(["📝 수업 기록 및 수정", "🔍 상세 내역 조회", "📊 성취도 분석 리포트"])

# --- [TAB 1: 수업 기록] ---
with tab_input:
    u_key = f"{st.session_state.reset_count}"
    if st.session_state.edit_mode and st.session_state.edit_data is not None:
        ed = st.session_state.edit_data
        st.info(f"수정 모드: {pd.to_datetime(ed['date']).strftime('%Y-%m-%d')} ({ed['session']}회차)")
        i_date, i_sess = pd.to_datetime(ed['date']), int(ed['session'])
        i_hw = pd.read_json(io.StringIO(ed['homeworks']))
        i_pr = pd.read_json(io.StringIO(ed['progress_list']))
        i_memo = json.loads(ed['solved_problems'])[0]['요약']
        i_feed, i_nhw = ed['feedback'], pd.read_json(io.StringIO(ed['next_hw_list']))
        try:
            i_st = datetime.strptime(ed['start_time'], "%H:%M").time()
            i_et = datetime.strptime(ed['end_time'], "%H:%M").time()
        except: i_st, i_et = time(14,0), time(16,0)
    else:
        i_date = datetime.now()
        i_sess = get_next_session(sel_name, i_date)
        i_hw = st.session_state.temp_hw_data if st.session_state.temp_hw_data is not None else pd.DataFrame(columns=["분류", "범위", "총 문항", "푼 문항", "모름", "안함"])
        i_pr = pd.DataFrame(columns=["분류", "단원/개념", "특이사항"])
        i_memo, i_feed = "", ""
        i_nhw = pd.DataFrame(columns=["분류", "범위", "세부지시"])
        i_st, i_et = time(14,0), time(16,0)

    st.markdown("#### 1️⃣ 기본 수업 정보")
    c1, c2, c3, c4 = st.columns(4)
    sel_date = c1.date_input("수업 날짜", i_date, key=f"d_{u_key}")
    if not st.session_state.edit_mode: auto_sess = get_next_session(sel_name, sel_date)
    else: auto_sess = i_sess
    in_sess = c2.number_input("수업 회차", min_value=1, value=auto_sess, key=f"s_{u_key}")
    in_st, in_et = c3.time_input("시작", i_st, key=f"st_{u_key}"), c4.time_input("종료", i_et, key=f"et_{u_key}")

    st.divider()
    st.markdown("#### 2️⃣ 오늘 숙제 달성도 확인")
    if not st.session_state.edit_mode and not all_recs.empty:
        if st.button("💡 지난번 내준 숙제 양식 가져오기"):
            raw_next = pd.read_json(io.StringIO(all_recs.sort_values(['date', 'session']).iloc[-1]['next_hw_list']))
            st.session_state.temp_hw_data = pd.DataFrame({"분류": raw_next["분류"], "범위": raw_next["범위"], "총 문항":0, "푼 문항":0, "모름":0, "안함":0})
            st.rerun()
    ed_hw = st.data_editor(i_hw, num_rows="dynamic", use_container_width=True, key=f"hw_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    
    st.divider()
    st.markdown("#### 3️⃣ 오늘 진도 및 수업 메모")
    ed_pr = st.data_editor(i_pr, num_rows="dynamic", use_container_width=True, key=f"pr_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_memo = st.text_area("상세 피드백", value=i_memo, key=f"m_{u_key}")

    st.divider()
    st.markdown("#### 4️⃣ 다음 숙제 및 피드백")
    ed_nhw = st.data_editor(i_nhw, num_rows="dynamic", use_container_width=True, key=f"nhw_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_feed = st.text_area("학부모 메시지", value=i_feed, key=f"f_{u_key}")

    if st.button("💾 최종 저장 및 노션 공유", type="primary", use_container_width=True):
        hw_j, pr_j, nh_j = ed_hw.to_json(orient='records'), ed_pr.to_json(orient='records'), ed_nhw.to_json(orient='records')
        memo_j = json.dumps([{"요약": in_memo}])
        dur = (datetime.combine(sel_date, in_et) - datetime.combine(sel_date, in_st)).seconds / 3600
        
        if st.session_state.edit_mode:
            c.execute("UPDATE progress SET date=?, session=?, start_time=?, end_time=?, duration=?, homeworks=?, progress_list=?, solved_problems=?, feedback=?, next_hw_list=? WHERE id=?",
                      (sel_date.strftime("%Y-%m-%d"), int(in_sess), in_st.strftime("%H:%M"), in_et.strftime("%H:%M"), dur, hw_j, pr_j, memo_j, in_feed, nh_j, st.session_state.edit_target_id))
        else:
            c.execute("INSERT INTO progress (name, date, weekday, session, start_time, end_time, duration, homeworks, progress_list, solved_problems, feedback, next_hw_list) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sel_name, sel_date.strftime("%Y-%m-%d"), get_weekday(sel_date), int(in_sess), in_st.strftime("%H:%M"), in_et.strftime("%H:%M"), dur, hw_j, pr_j, memo_j, in_feed, nh_j))
        conn.commit()

        st_code = save_to_notion({"name": sel_name, "date": sel_date.strftime("%Y-%m-%d"), "session": int(in_sess), "hw_df": ed_hw, "pr_df": ed_pr, "memo": in_memo, "nhw_df": ed_nhw, "feedback": in_feed})
        
        if st_code == 200: st.success("✅ 저장 및 노션 공유 완료!")
        else: st.warning(f"⚠️ 저장 완료(노션 연동 실패 {st_code}). 연결 확인 필요.")
        trigger_reset(); st.rerun()

# --- [TAB 2: 상세 내역 조회] ---
with tab_search:
    if not all_recs.empty:
        sort_recs = all_recs.sort_values(['date', 'session'], ascending=False)
        v_list = [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in sort_recs.iterrows()]
        sel_v = st.selectbox("조회할 수업 날짜 선택", v_list)
        row = sort_recs.iloc[v_list.index(sel_v)]
        
        if st.button("✏️ 이 기록 수정하기"):
            st.session_state.edit_mode, st.session_state.edit_target_id, st.session_state.edit_data = True, row['id'], row
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            st.write("**📝 숙제 수행 결과**")
            st.dataframe(pd.read_json(io.StringIO(row['homeworks'])), use_container_width=True)
        with c2:
            st.write("**📖 진도 및 상세 피드백**")
            st.dataframe(pd.read_json(io.StringIO(row['progress_list'])), use_container_width=True)
            st.info(json.loads(row['solved_problems'])[0]['요약'])
        
        st.write("**📋 다음 수업 숙제**")
        st.dataframe(pd.read_json(io.StringIO(row['next_hw_list'])), use_container_width=True)
        st.write("**✉️ 학부모 전송 피드백**")
        st.success(row['feedback'] if row['feedback'] else "입력된 피드백이 없습니다.")
    else:
        st.write("조회할 수업 기록이 없습니다.")

# --- [TAB 3: 성취도 분석 리포트] ---
with tab_analysis:
    if not all_recs.empty:
        analysis_data = []
        for _, r in all_recs.iterrows():
            hw = pd.read_json(io.StringIO(r['homeworks']))
            tot = pd.to_numeric(hw['총 문항']).sum() if not hw.empty else 0
            sol = (pd.to_numeric(hw['푼 문항']).sum() + pd.to_numeric(hw['모름']).sum()) if not hw.empty else 0
            analysis_data.append({
                "날짜": r['date'], 
                "회차": f"{r['session']}회", 
                "성취도": round(sol/tot*100, 1) if tot > 0 else 0,
                "주별": r['date'].to_period('W').start_time.strftime('%Y-%m-%d'),
                "월별": r['date'].strftime('%Y-%m')
            })
        df_an = pd.DataFrame(analysis_data).sort_values("날짜")
        
        opt = st.radio("분석 단위", ["일별 전체", "주별 상세", "월별 상세"], horizontal=True)
        
        if opt == "일별 전체":
            st.line_chart(df_an.set_index('날짜')['성취도'])
            st.dataframe(df_an.sort_values("날짜", ascending=False), use_container_width=True)
        elif opt == "주별 상세":
            target_w = st.selectbox("주 선택", sorted(df_an['주별'].unique(), reverse=True))
            filtered = df_an[df_an['주별'] == target_w]
            st.bar_chart(filtered.set_index('회차')['성취도'])
            st.dataframe(filtered, use_container_width=True)
        elif opt == "월별 상세":
            target_m = st.selectbox("월 선택", sorted(df_an['월별'].unique(), reverse=True))
            filtered = df_an[df_an['월별'] == target_m]
            st.bar_chart(filtered.set_index('회차')['성취도'])
            st.dataframe(filtered, use_container_width=True)
    else:
        st.write("분석할 데이터가 부족합니다.")
