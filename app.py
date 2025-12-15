from flask import Flask, render_template, request, jsonify
import csv
import datetime
import requests
import os
import json
import time
import threading

app = Flask(__name__)

# ==========================================
# [설정] 테스트 모드
# ==========================================
REALTIME_MODE = False  # True면 즉시 전송
TELEGRAM_TOKEN = "8182951488:AAF_d6T3G39QD6elLJkEHhxkbsOPYkeandM"
MY_CHAT_ID = "-1003620187316"
SEND_INTERVAL = 600

# 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VISIT_LOG_PATH = os.path.join(BASE_DIR, "visitor_log.csv")
SEARCH_LOG_PATH = os.path.join(BASE_DIR, "search_log.csv")
DASHBOARD_STATE_PATH = os.path.join(BASE_DIR, "dashboard_state.json")

# ==========================================
# [데이터 저장]
# ==========================================
def save_visitor_log(user_id):
    now = datetime.datetime.now()
    try:
        if not os.path.exists(VISIT_LOG_PATH):
            with open(VISIT_LOG_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f).writerow(['Date', 'Time', 'User_ID'])
        
        with open(VISIT_LOG_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), user_id])
        print("✅ 방문자 로그 저장 성공")
    except Exception as e:
        print(f"❌ 방문자 저장 실패: {e}")

def save_search_log(user_id, keyword):
    now = datetime.datetime.now()
    
    # [수정됨] 단어가 2개 이상이면 '랜덤(RANDOM)'으로 판정 (테스트 쉽게 하려고 기준 낮춤)
    # 예: "비트코인" -> 수동 / "비트코인 전망" -> 랜덤
    search_type = "TEXT"
    if keyword and len(keyword.strip().split()) >= 2:
        search_type = "RANDOM"
    
    try:
        if not os.path.exists(SEARCH_LOG_PATH):
            with open(SEARCH_LOG_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f).writerow(['Date', 'Time', 'User_ID', 'Type', 'Keyword'])
        
        with open(SEARCH_LOG_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), user_id, search_type, keyword])
        print(f"✅ 검색 로그 저장 성공: {keyword} ({search_type})")
    except Exception as e:
        print(f"❌ 검색 저장 실패: {e}")

def get_today_stats():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    stats = {
        "visit_total": 0, "visit_today": 0,
        "search_total_text": 0, "search_total_random": 0, 
        "search_today_text": 0, "search_today_random": 0, 
        "recent_keywords": []
    }

    # 방문자 읽기
    if os.path.exists(VISIT_LOG_PATH):
        try:
            with open(VISIT_LOG_PATH, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    stats["visit_total"] += 1
                    if row.get('Date') == today_str: stats["visit_today"] += 1
        except Exception as e: print(f"⚠️ 방문자 CSV 읽기 에러: {e}")

    # 검색어 읽기
    if os.path.exists(SEARCH_LOG_PATH):
        try:
            with open(SEARCH_LOG_PATH, 'r', encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
                for row in rows:
                    sType = row.get('Type', 'TEXT')
                    sDate = row.get('Date')
                    
                    # 누적
                    if sType == 'RANDOM': stats["search_total_random"] += 1
                    else: stats["search_total_text"] += 1
                    
                    # 오늘
                    if sDate == today_str:
                        if sType == 'RANDOM': stats["search_today_random"] += 1
                        else: stats["search_today_text"] += 1
                
                # 최근 검색어
                recent = rows[-3:]
                recent.reverse()
                for r in recent:
                    k = r.get('Keyword', '')
                    t = r.get('Type', 'TEXT')
                    # 랜덤은 🎲, 수동은 ⌨️ 아이콘 붙여서 보여줌
                    icon = "🎲" if t == "RANDOM" else "⌨️"
                    stats['recent_keywords'].append(f"{icon} {k}")
        except Exception as e: print(f"⚠️ 검색 CSV 읽기 에러: {e}")
    
    return stats

def update_telegram_dashboard():
    stats = get_today_stats()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    recent_str = "\n".join([f"• {k}" for k in stats['recent_keywords']]) or "(기록 없음)"

    msg = (
        f"📊 **[DASHBOARD] {today_str}**\n"
        f"🕒 Updated: {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
        f"👥 **방문자 (Visitors)**\n"
        f" • Total: `{stats['visit_total']:,}`\n"
        f" • Today: `{stats['visit_today']:,}`\n\n"
        f"🔍 **검색 (Searches)**\n"
        f"__All Time (누적)__\n"
        f" • ⌨️수동: `{stats['search_total_text']:,}`\n"
        f" • 🎲랜덤: `{stats['search_total_random']:,}`\n"
        f"__Today (오늘)__\n"
        f" • ⌨️수동: `{stats['search_today_text']:,}`\n"
        f" • 🎲랜덤: `{stats['search_today_random']:,}`\n\n"
        f"👀 **최근 검색어**\n{recent_str}"
    )

    last_data = {}
    if os.path.exists(DASHBOARD_STATE_PATH):
        try:
            with open(DASHBOARD_STATE_PATH, 'r') as f: last_data = json.load(f)
        except: pass

    try:
        # 메시지가 없거나 날짜가 바뀌었으면 -> 새 메시지 전송
        if last_data.get('date') != today_str:
            res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                                json={"chat_id": MY_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).json()
            if res.get('ok'):
                with open(DASHBOARD_STATE_PATH, 'w') as f:
                    json.dump({"date": today_str, "message_id": res['result']['message_id']}, f)
                print(">>> 텔레그램: 새 메시지 전송됨")
        else:
            # 기존 메시지 수정
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", 
                          json={"chat_id": MY_CHAT_ID, "message_id": last_data.get('message_id'), "text": msg, "parse_mode": "Markdown"})
            print(">>> 텔레그램: 기존 메시지 업데이트됨")
            
    except Exception as e: print(f"❌ 텔레그램 전송 에러: {e}")

def background_scheduler():
    print(">>> [배포 모드] 스케줄러 가동")
    while True:
        update_telegram_dashboard()
        time.sleep(SEND_INTERVAL)

# ==========================================
# [라우트]
# ==========================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/log_visit', methods=['POST'])
def log_visit():
    save_visitor_log('Guest')
    if REALTIME_MODE: update_telegram_dashboard()
    return jsonify({"status": "ok"})

@app.route('/log_search', methods=['POST'])
def log_search():
    data = request.get_json()
    print(f"📩 데이터 수신됨: {data}") # [디버깅용 출력]
    
    save_search_log(data.get('user_id'), data.get('keyword'))
    
    if REALTIME_MODE: update_telegram_dashboard()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    if not REALTIME_MODE:
        t = threading.Thread(target=background_scheduler)
        t.daemon = True
        t.start()
    
    print(f"\n>>> 현재 모드: {'[실시간/TEST]' if REALTIME_MODE else '[배포/10분단위]'}")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)