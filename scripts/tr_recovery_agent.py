import requests
import time
import subprocess
import os
from datetime import datetime
from dotenv import load_dotenv


now = datetime.now().strftime("%d-%m-%y %H:%M:%S")

# 1. Cập nhật URL chuẩn theo Ingress Domain đã config trong file /etc/hosts
APP_URL = "http://automated-lab.local/health"
RESET_URL = "http://automated-lab.local/reset-fault"

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN == "TELEGRAM_BOT_TOKEN":
        print(f"[MOCK TELEGRAM] {msg}")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"  
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

def handle_incident():
    print("🚨 [ALERT] Phát hiện sự cố (HTTP Status != 200)! Đang cào log từ Pod...")
    
    # 1. Trích xuất log từ Pod K8s
    try:
        logs = subprocess.check_output("kubectl logs -l app=network-probe --tail=50", shell=True).decode()
        with open("incident_report.log", "w", encoding="utf-8") as f:
            f.write(logs)
        print("📝 Đã xuất log ra file 'incident_report.log'.")
    except Exception as e:
        print(f"Không thể cào log từ K8s: {e}")

    # Bắn cảnh báo
    send_telegram(f"⏱ *[{now}]*\n⚠️ *[TR REPORT]* Detect Fault on Network Probe Service!\nCaptured logs to `incident_report.log`")

    # 2. Thực hiện Auto-Healing (Tự động kích hoạt Reset Fault)
    print("🔧 [RECOVERY] Đang thực hiện Auto-Healing (Reset Fault)...")
    try:
        response = requests.post(RESET_URL, timeout=5)
        if response.status_code == 200:
            print("✅ Auto-Healing thành công! Hệ thống đã phục hồi.")
            send_telegram(f"⏱ *[{now}]*\n✅ *[AUTO-HEALED]* System fault reset successfully via Ingress. Service operational.")
        else:
            print(f"❌ Reset thất bại, HTTP Code: {response.status_code}")
    except Exception as e:
        print(f"Lỗi khi gửi lệnh reset: {e}")

# Vòng lặp giám sát (Health Check Loop)
print(f"🔍 Bắt đầu giám sát Service tại: {APP_URL}")
while True:
    try:
        r = requests.get(APP_URL, timeout=2)
        if r.status_code == 200:
            print("🟢 [OK] Service hoạt động bình thường...", end="\r")
        else:
            print(f"\n🔴 [FAIL] Service trả về HTTP {r.status_code}")
            handle_incident()
    except Exception as e:
        print(f"\n🔴 [FAIL] Không thể kết nối tới Service: {e}")
        handle_incident()
        
    time.sleep(3)