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
    
    # 데이터 요약 생성 시 비어있는 경우 처리
    if data['hw_df'].empty:
        hw_summary = "• 숙제 없음"
    else:
        hw_summary = "".join([f"• {r.get('분류','')}: {r.get('푼 문항',0)}/{r.get('총 문항',0)} (모름:{r.get('모름',0)})\n" for _, r in data['hw_df'].iterrows()])
    
    pr_summary = f"메모: {data['memo']}\n" + "".join([f"• {r.get('분류','')}: {r.get('단원/개념','')} ({r.get('특이사항','')})\n" for _, r in data['pr_df'].iterrows()])
    
    if data['nhw_df'].empty:
        nhw_summary = "• 다음 숙제 없음"
    else:
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

# 세션 상태 초기화
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'edit_target_id' not in st.session_state: st.session_state.edit_target_id = None
if 'reset_count' not in st.session_state: st.session_state.reset_count = 0
if 'temp_hw_data' not in st.session_state: st.session_state.temp_hw_data = None
if 'edit_data' not in st.session_state: st.session_state.edit_data = None

def trigger_reset():
    st.session_state.reset_count += 1
    st.session_state.edit_mode, st.session_state.edit_target_id, st.session_state.temp_hw_data, st.session_state.edit_data = False, None, None, None

# --- [4. 사이드바: 학생 및 교재 삭제 기능] ---
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
    if not curr_books:
        st.caption("등록된 교재가 없습니다.")
    else:
        for i, b in enumerate(curr_books):
            col_b1, col_b2 = st.columns([4, 1])
            col_b1.text(f"• {b}")
            if col_b2.button("🗑️", key=f"del_book_{i}"):
                curr_books.pop(i)
                c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
                conn.commit()
                st.rerun()

    nb = st.text_input("새 교재 추가")
    if st.button("교재 저장") and nb:
        curr_books.append(nb)
        c.execute("UPDATE students SET books=? WHERE name=?", (json.dumps(curr_books), sel_name))
        conn.commit(); st.rerun()
    
    st.divider()
    if st.button("🔄 새 수업 입력으로 전환", use_container_width=True): trigger_reset(); st.rerun()

all_recs = pd.read_sql_query(f"SELECT * FROM progress WHERE name='{sel_name}'", conn)
if not all_recs.empty:
    all_recs['date'] = pd.to_datetime(all_recs['date'])

# --- [5. 메인 화면] ---
st.title(f"📖 {sel_name} 학생 관리")
tab_input, tab_search, tab_calendar, tab_analysis = st.tabs(["📝 수업 기록", "🔍 상세 내역", "📅 월간 일정", "📊 성취도 분석"])

# --- [TAB 1: 수업 기록] ---
with tab_input:
    u_key = f"{st.session_state.reset_count}"
    if st.session_state.edit_mode and st.session_state.edit_data is not None:
        ed = st.session_state.edit_data
        st.info(f"📍 수정 중: {pd.to_datetime(ed['date']).strftime('%Y-%m-%d')} ({ed['session']}회차)")
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

    st.markdown("#### 1️⃣ 기본 정보")
    c1, c2, c3, c4 = st.columns(4)
    sel_date = c1.date_input("수업 날짜", i_date, key=f"d_{u_key}")
    if not st.session_state.edit_mode: auto_sess = get_next_session(sel_name, sel_date)
    else: auto_sess = i_sess
    in_sess = c2.number_input("수업 회차", min_value=1, value=auto_sess, key=f"s_{u_key}")
    in_st, in_et = c3.time_input("시작", i_st, key=f"st_{u_key}"), c4.time_input("종료", i_et, key=f"et_{u_key}")

    st.divider()
    st.markdown("#### 2️⃣ 오늘 숙제 달성도")
    no_hw_today = st.checkbox("오늘 확인한 숙제 없음", key=f"no_hw_today_{u_key}")
    if not no_hw_today:
        if not st.session_state.edit_mode and not all_recs.empty:
            if st.button("💡 지난번 숙제 가져오기"):
                raw_next = pd.read_json(io.StringIO(all_recs.sort_values(['date', 'session']).iloc[-1]['next_hw_list']))
                st.session_state.temp_hw_data = pd.DataFrame({"분류": raw_next["분류"], "범위": raw_next["범위"], "총 문항":0, "푼 문항":0, "모름":0, "안함":0})
                st.rerun()
        ed_hw = st.data_editor(i_hw, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"hw_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    else:
        ed_hw = pd.DataFrame(columns=["분류", "범위", "총 문항", "푼 문항", "모름", "안함"])

    st.divider()
    st.markdown("#### 3️⃣ 오늘 진도 및 메모")
    ed_pr = st.data_editor(i_pr, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"pr_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    in_memo = st.text_area("수업 상세 피드백", value=i_memo, key=f"m_{u_key}")

    st.divider()
    st.markdown("#### 4️⃣ 다음 숙제 및 학부모 피드백")
    no_hw_next = st.checkbox("다음 숙제 없음", key=f"no_hw_next_{u_key}")
    if not no_hw_next:
        ed_nhw = st.data_editor(i_nhw, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"nhw_{u_key}", column_config={"분류": st.column_config.SelectboxColumn("교재", options=curr_books)})
    else:
        ed_nhw = pd.DataFrame(columns=["분류", "범위", "세부지시"])
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
        save_to_notion({"name": sel_name, "date": sel_date.strftime("%Y-%m-%d"), "session": int(in_sess), "hw_df": ed_hw, "pr_df": ed_pr, "memo": in_memo, "nhw_df": ed_nhw, "feedback": in_feed})
        trigger_reset(); st.rerun()

# --- [TAB 2: 상세 내역 조회] ---
with tab_search:
    if not all_recs.empty:
        sort_recs = all_recs.sort_values(['date', 'session'], ascending=False)
        v_list = [f"{r['date'].strftime('%Y-%m-%d')} ({r['session']}회차)" for _, r in sort_recs.iterrows()]
        sel_v = st.selectbox("날짜 선택", v_list, key="search_box")
        row = sort_recs.iloc[v_list.index(sel_v)]
        
        col_btn1, col_btn2, _ = st.columns([1, 1, 2])
        if col_btn1.button("✏️ 수정", use_container_width=True):
            st.session_state.edit_mode, st.session_state.edit_target_id, st.session_state.edit_data = True, row['id'], row
            st.rerun()
        with col_btn2:
            with st.popover("🗑️ 삭제", use_container_width=True):
                if st.button("영구 삭제 확인"):
                    c.execute("DELETE FROM progress WHERE id=?", (int(row['id']),))
                    conn.commit(); st.rerun()

        st.divider()
        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("##### 📝 지난 숙제 결과")
            if not row['homeworks'] or row['homeworks'] == '[]':
                st.info("지난 숙제가 없었습니다.")
            else:
                try:
                    hw_view = pd.read_json(io.StringIO(row['homeworks']))
                    if hw_view.empty: st.info("지난 숙제가 없었습니다.")
                    else: st.dataframe(hw_view, use_container_width=True, hide_index=True)
                except: st.error("데이터 오류")
        with sc2:
            st.markdown("##### 📖 진도")
            pr_view = pd.read_json(io.StringIO(row['progress_list']))
            st.dataframe(pr_view, use_container_width=True, hide_index=True)
        
        st.info(f"**상세 피드백:** {json.loads(row['solved_problems'])[0]['요약']}")
        st.success(f"**학부모 메시지:** {row['feedback']}")
    else:
        st.write("기록이 없습니다.")

# --- [TAB 3: 월간 일정] ---
with tab_calendar:
    if not all_recs.empty:
        all_recs['month'] = all_recs['date'].dt.strftime('%Y-%m')
        sel_m = st.selectbox("달 선택", sorted(all_recs['month'].unique(), reverse=True))
        m_data = all_recs[all_recs['month'] == sel_m].sort_values('date')
        
        for _, r in m_data.iterrows():
            with st.expander(f"📍 {r['date'].strftime('%m/%d')} - {r['session']}회차"):
                c_c1, c_c2 = st.columns(2)
                with c_c1:
                    st.write("**[진도]**")
                    pv = pd.read_json(io.StringIO(r['progress_list']))
                    for _, p in pv.iterrows(): st.write(f"- {p['분류']}: {p['단원/개념']}")
                with c_c2:
                    st.write("**[다음 숙제]**")
                    if not r['next_hw_list'] or r['next_hw_list'] == '[]':
                        st.write("숙제 없음")
                    else:
                        nv = pd.read_json(io.StringIO(r['next_hw_list']))
                        if nv.empty: st.write("숙제 없음")
                        else:
                            for _, n in nv.iterrows(): st.write(f"- {n['분류']}: {n['범위']}")
    else:
        st.write("기록이 없습니다.")

# --- [TAB 4: 성취도 분석 리포트] ---
with tab_analysis:
    if not all_recs.empty:
        analysis_data = []
        for _, r in all_recs.iterrows():
            try:
                hw = pd.read_json(io.StringIO(r['homeworks']))
                if hw.empty or pd.to_numeric(hw['총 문항'], errors='coerce').sum() == 0:
                    score = 100.0
                else:
                    tot = pd.to_numeric(hw['총 문항']).sum()
                    sol = pd.to_numeric(hw['푼 문항']).sum() + pd.to_numeric(hw['모름']).sum()
                    score = round(sol/tot*100, 1)
                analysis_data.append({
                    "날짜": r['date'], "회차": f"{r['date'].strftime('%m/%d')} ({r['session']}회)", 
                    "성취도": score, "월별": r['date'].strftime('%Y-%m')
                })
            except: continue
        
        if analysis_data:
            df_an = pd.DataFrame(analysis_data).sort_values("날짜")
            avg_s = round(df_an['성취도'].mean(), 1)
            st.metric("평균 성취도", f"{avg_s}%")
            
            mode = st.radio("보기", ["전체", "월별"], horizontal=True)
            if mode == "전체":
                st.area_chart(df_an.set_index('회차')['성취도'])
                st.dataframe(df_an, use_container_width=True, hide_index=True)
            else:
                m_target = st.selectbox("월 선택", sorted(df_an['월별'].unique(), reverse=True), key="an_m")
                m_filtered = df_an[df_an['월별'] == m_target]
                st.bar_chart(m_filtered.set_index('회차')['성취도'])
    else:
        st.write("분석할 데이터가 없습니다.")
