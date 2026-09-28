# =============================================================================
# TR recovery agent
# Flow: health-check loop -> capture K8s logs -> AI/heuristic diagnosis
#       -> Telegram approval buttons -> execute only after operator confirms
# Diagnose later: grep for the section tags below, e.g. [TELEGRAM], [AI], [MAIN]
# =============================================================================

import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv

# --- [CONFIG] Service targets and env (Telegram + Gemini) ---
APP_URL = "http://automated-lab.local/health"
RESET_URL = "http://automated-lab.local/reset-fault"
DEPLOYMENT_NAME = "network-probe-app"
POD_LABEL = "app=network-probe"

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID") or "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Whitelist of recovery commands the AI may propose. Unknown names become "none".
ALLOWED_ACTIONS = {
    "reset_fault": {
        "label": "Reset fault",
        "description": "Call /reset-fault to clear the simulated service fault",
    },
    "restart_pod": {
        "label": "Restart pods",
        "description": "kubectl rollout restart the network-probe deployment",
    },
    "none": {
        "label": "No automated action",
        "description": "Investigate manually; do not run a recovery command",
    },
}

# Runtime state (shared with the Telegram poll thread)
pending_actions = {}  # action_id -> {action, created_at}; waiting for button tap
pending_lock = threading.Lock()
telegram_offset = 0  # getUpdates cursor so we do not re-handle old callbacks
# One disaster = one Telegram until Execute/Ignore, then silence until /health is 200 again.
alert_sent = False
awaiting_decision = False


# --- [HELPERS] Time + HTML escape for Telegram messages ---
def now_str():
    return datetime.now().strftime("%d-%m-%y %H:%M:%S")


def html_escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# --- [TELEGRAM] Outbound API (mock if token is missing / placeholder) ---
def telegram_ready():
    return bool(TELEGRAM_BOT_TOKEN) and TELEGRAM_BOT_TOKEN != "TELEGRAM_BOT_TOKEN"


def telegram_api(method, payload):
    if not telegram_ready():
        print(f"[MOCK TELEGRAM] {method}: {payload.get('text', payload)}")
        return {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=35)
        return response.json()
    except Exception as e:
        print(f"Lỗi Telegram {method}: {e}")
        return {}


def send_telegram(msg, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("sendMessage", payload)


# --- [K8S LOGS] Dump recent pod logs for diagnosis (also writes incident_report.log) ---
def capture_logs():
    try:
        logs = subprocess.check_output(
            "kubectl logs -l app=network-probe --tail=50",
            shell=True,
        ).decode()
        with open("incident_report.log", "w", encoding="utf-8") as f:
            f.write(logs)
        print("📝 Đã xuất log ra file 'incident_report.log'.")
        return logs
    except Exception as e:
        print(f"Không thể cào log từ K8s: {e}")
        return f"(failed to capture logs: {e})"


# --- [AI] Heuristic fallback when Gemini is missing or the API call fails ---
def fallback_diagnosis(error_text, logs):
    combined = f"{error_text}\n{logs}".lower()
    if "simulated" in combined or "fault" in combined or "500" in combined:
        action = "reset_fault"
        diagnosis = "Health check is failing; logs look like the simulated fault rather than a pod crash."
    elif "connection" in combined or "timeout" in combined:
        action = "restart_pod"
        diagnosis = "The probe cannot reach the service. A pod restart may restore the listener."
    else:
        action = "none"
        diagnosis = "Failure is unclear; do not auto-run a recovery command."
    return {
        "diagnosis": diagnosis,
        "action": action,
        "reason": ALLOWED_ACTIONS[action]["description"],
    }


# Extract {diagnosis, action, reason} from the model reply; clamp action to whitelist.
def parse_ai_json(content):
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("AI response was not JSON")
    data = json.loads(match.group(0))
    action = str(data.get("action", "none")).strip()
    if action not in ALLOWED_ACTIONS:
        action = "none"
    return {
        "diagnosis": str(data.get("diagnosis") or "No diagnosis returned."),
        "action": action,
        "reason": str(data.get("reason") or ALLOWED_ACTIONS[action]["description"]),
    }


def gemini_text(payload):
    error = payload.get("error") or {}
    if error:
        raise ValueError(error.get("message") or str(error))
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("empty Gemini response")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts)


# Ask Gemini for one recovery action; on any failure use fallback_diagnosis.
def diagnose_with_ai(error_text, logs):
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY missing — using heuristic diagnosis.")
        return fallback_diagnosis(error_text, logs)

    prompt = (
        "You are an SRE for a Kubernetes lab service named network-probe.\n"
        "The health endpoint failed. Propose exactly one recovery action.\n"
        "Allowed action values: reset_fault, restart_pod, none.\n"
        "reset_fault clears a simulated app fault via POST /reset-fault.\n"
        "restart_pod runs kubectl rollout restart on the deployment.\n"
        "Use none if a command would be unsafe or unclear.\n"
        "Reply with JSON only: {\"diagnosis\": string, \"action\": string, \"reason\": string}.\n\n"
        f"Error:\n{error_text}\n\nLogs:\n{logs[-4000:]}"
    )
    url = (
        f"{GEMINI_BASE_URL.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
    )
    try:
        response = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {
                    "parts": [{"text": "Return valid JSON only."}]
                },
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
            timeout=30,
        )
        payload = response.json()
        if not response.ok:
            raise ValueError(
                payload.get("error", {}).get("message")
                or f"Gemini HTTP {response.status_code}"
            )
        return parse_ai_json(gemini_text(payload))
    except Exception as e:
        print(f"AI diagnosis failed, using fallback: {e}")
        return fallback_diagnosis(error_text, logs)


def list_app_pods():
    output = subprocess.check_output(
        [
            "kubectl",
            "get",
            "pods",
            "-l",
            POD_LABEL,
            "-o",
            "jsonpath={.items[*].metadata.name}",
        ],
        text=True,
    )
    return [name for name in output.split() if name]


def post_on_pod(pod, path):
    # In-memory is_faulty is per process. Ingress reset only hits one replica.
    script = (
        "import urllib.request; "
        f"urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000{path}', method='POST'))"
    )
    subprocess.check_call(["kubectl", "exec", pod, "--", "python", "-c", script])


def reset_fault_all_pods():
    pods = list_app_pods()
    if not pods:
        raise RuntimeError("No network-probe pods found")
    failed = []
    for pod in pods:
        try:
            post_on_pod(pod, "/reset-fault")
        except Exception as e:
            failed.append(f"{pod}: {e}")
    if failed:
        raise RuntimeError("reset-fault failed on: " + "; ".join(failed))
    return f"Fault flag cleared on {len(pods)} pod(s): {', '.join(pods)}."


# --- [RECOVERY] Run a whitelisted action only (called after Telegram Approve) ---
def execute_action(action):
    if action == "reset_fault":
        try:
            return reset_fault_all_pods()
        except Exception as exec_error:
            response = requests.post(RESET_URL, timeout=5)
            if response.status_code != 200:
                raise RuntimeError(
                    f"kubectl reset failed ({exec_error}); "
                    f"Ingress reset-fault HTTP {response.status_code}"
                )
            return (
                "Fault reset via Ingress only (one replica). "
                f"kubectl path failed: {exec_error}"
            )
    if action == "restart_pod":
        subprocess.check_call(
            ["kubectl", "rollout", "restart", f"deployment/{DEPLOYMENT_NAME}"]
        )
        return f"Rollout restart triggered for {DEPLOYMENT_NAME}."
    if action == "none":
        return "No recovery command was run."
    raise ValueError(f"Blocked unknown action: {action}")


# --- [TELEGRAM APPROVAL] Send incident + inline buttons; store pending action_id ---
def send_approval_request(error_text, logs, diagnosis):
    action_id = uuid.uuid4().hex[:10]
    action = diagnosis["action"]
    label = ALLOWED_ACTIONS[action]["label"]
    with pending_lock:
        pending_actions[action_id] = {
            "action": action,
            "created_at": time.time(),
        }

    buttons = []
    if action != "none":
        buttons.append(
            {"text": f"✅ Execute: {label}", "callback_data": f"ok:{action_id}"}
        )
    buttons.append({"text": "❌ Ignore", "callback_data": f"no:{action_id}"})

    msg = (
        f"⏱ <b>[{html_escape(now_str())}]</b>\n"
        f"⚠️ <b>[TR REPORT]</b> Fault detected.\n"
        f"<b>Error:</b> {html_escape(error_text)}\n\n"
        f"<b>AI diagnosis:</b> {html_escape(diagnosis['diagnosis'])}\n"
        f"<b>Proposed action:</b> {html_escape(label)}\n"
        f"<b>Why:</b> {html_escape(diagnosis['reason'])}\n\n"
        "Tap a button to execute or ignore. Nothing runs until you confirm."
    )
    send_telegram(msg, reply_markup={"inline_keyboard": [buttons]})
    print(f"📨 Sent Telegram approval for action={action} id={action_id}")


def close_operator_prompt():
    global awaiting_decision
    with pending_lock:
        awaiting_decision = False
        pending_actions.clear()


# Operator tapped Execute (ok:<id>) or Ignore (no:<id>) on the approval message.
def handle_callback(query):
    callback_id = query.get("id")
    data = query.get("data") or ""
    message = query.get("message") or {}
    chat = (message.get("chat") or {}).get("id")
    from_user = (query.get("from") or {}).get("id")
    authorized = str(chat) == TELEGRAM_CHAT_ID or str(from_user) == TELEGRAM_CHAT_ID

    telegram_api("answerCallbackQuery", {"callback_query_id": callback_id})
    if not authorized:
        print(f"Ignored callback from unauthorized chat={chat} user={from_user}")
        return

    kind, _, action_id = data.partition(":")
    with pending_lock:
        pending = pending_actions.pop(action_id, None)

    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    original = message.get("text") or ""

    if not pending:
        telegram_api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": original + "\n\n⚠️ This decision is no longer valid.",
            },
        )
        return

    if kind == "no":
        close_operator_prompt()
        telegram_api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": original + "\n\n❌ Ignored. No recovery command was run.",
            },
        )
        print("❌ Operator ignored. No recovery command was run.")
        return

    if kind != "ok":
        return

    action = pending["action"]
    close_operator_prompt()
    try:
        result = execute_action(action)
        telegram_api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": original + f"\n\n✅ Executed: {ALLOWED_ACTIONS[action]['label']}",
            },
        )
        print(f"✅ Executed {action}: {result}")
    except Exception as e:
        telegram_api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": original + f"\n\n❌ Execute failed: {e}",
            },
        )
        print(f"❌ Execute failed: {e}")


# Drop queued Telegram updates so a leftover Execute tap cannot run on startup.
def skip_telegram_backlog():
    global telegram_offset
    if not telegram_ready():
        return
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 0, "allowed_updates": json.dumps(["callback_query"])},
            timeout=15,
        )
        data = response.json()
        updates = data.get("result") or []
        if updates:
            telegram_offset = updates[-1]["update_id"] + 1
            print(f"⏭ Skipped {len(updates)} queued Telegram update(s).")
    except Exception as e:
        print(f"Could not skip Telegram backlog: {e}")


# Background thread: long-poll getUpdates for button taps only.
def poll_telegram_callbacks():
    global telegram_offset
    while True:
        if not telegram_ready():
            time.sleep(5)
            continue
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={
                    "offset": telegram_offset,
                    "timeout": 25,
                    "allowed_updates": json.dumps(["callback_query"]),
                },
                timeout=35,
            )
            data = response.json()
            for update in data.get("result", []):
                telegram_offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
        except Exception as e:
            print(f"Telegram poll error: {e}")
            time.sleep(3)


# --- [INCIDENT] One alert cycle: logs -> diagnosis -> wait for Telegram confirm ---
def handle_incident(error_text):
    print("🚨 [ALERT] Phát hiện sự cố! Đang cào log từ Pod...")
    logs = capture_logs()
    diagnosis = diagnose_with_ai(error_text, logs)
    print(
        f"🤖 Diagnosis: {diagnosis['diagnosis']}\n"
        f"➡️  Proposed: {diagnosis['action']} ({diagnosis['reason']})"
    )
    send_approval_request(error_text, logs, diagnosis)


# --- [MAIN] Start Telegram listener, then poll /health every 3s ---
print(f"🔍 Bắt đầu giám sát Service tại: {APP_URL}")
skip_telegram_backlog()
threading.Thread(target=poll_telegram_callbacks, daemon=True).start()

while True:
    error_text = None
    try:
        r = requests.get(APP_URL, timeout=2)
        healthy = r.status_code == 200
        if not healthy:
            error_text = f"HTTP {r.status_code} from {APP_URL}: {r.text[:300]}"
    except Exception as e:
        healthy = False
        error_text = str(e)

    with pending_lock:
        waiting = awaiting_decision
        already_alerted = alert_sent

    if waiting:
        print("⏳ [WAIT] Telegram decision pending (no new alert).   ", end="\r")
    elif healthy:
        if already_alerted:
            print("\n🟢 [RECOVERED] /health is HTTP 200 OK after operator decision.")
            with pending_lock:
                alert_sent = False
        else:
            print("🟢 [OK] /health 200", end="\r")
    elif not already_alerted:
        print(f"\n🔴 [FAIL] /health failed — sending one Telegram alert.")
        handle_incident(error_text)
        with pending_lock:
            alert_sent = True
            awaiting_decision = True

    time.sleep(3)
