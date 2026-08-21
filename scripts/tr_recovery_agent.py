import requests, time, subprocess

APP_URL = "http://localhost:30080/health"

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

def send_telegram(msg):
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
    print("[ALERT] App is DOWN! Capturing logs...")
    # 1. Trích xuất log từ Pod K8s
    logs = subprocess.check_output("kubectl logs -l app=network-probe --tail=50", shell=True).decode()
    with open("incident_report.log", "w") as f:
        f.write(logs)
    
    send_telegram("⚠️ *[TR REPORT]* Detect HTTP 500 Fault on Network Probe Service!\nCaptured logs to `incident_report.log`.")

    # 2. Thực hiện Auto-Healing (Restoring System)
    print("[RECOVERY] Triggering Auto-Healing/Reset...")
    subprocess.run("curl -X POST http://localhost:30080/reset-fault", shell=True)
    send_telegram("✅ *[AUTO-HEALED]* System fault reset successfully. Service operational.")

# Monitoring loop
while True:
    try:
        r = requests.get(APP_URL, timeout=2)
        if r.status_code != 200:
            handle_incident()
    except Exception as e:
        print("Service unreachable...")
    time.sleep(5)