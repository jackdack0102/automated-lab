# Automated Lab (K8s Auto-Healing)

An automated Kubernetes lab simulating a network service with **NGINX Ingress** routing and a **Python Recovery Agent** for real-time monitoring, automated log extraction, and self-healing.

## Disaster Simulation & Recovery

### 1. Run Monitoring Agent

```bash
source venv/bin/activate
python scripts/tr_recovery_agent.py
```

Or without activating: `./venv/bin/python scripts/tr_recovery_agent.py`


### 2. Trigger Incident

curl -X POST http://automated-lab.local/simulate-fault

### 3. AI diagnosis + Telegram approval

The Recovery Agent:

* Detects HTTP failure on `/health`.
* Captures Pod logs to `incident_report.log`.
* Sends the error and logs to Gemini for a diagnosis and a proposed action (`reset_fault`, `restart_pod`, or `none`).
* Posts that proposal to Telegram **once** with **Execute** / **Ignore** buttons.
* Runs the command **only after you tap Execute**. It does not treat a later `/health` 200 as recovery while that decision is still pending (Ingress can hit a healthy replica even though the fault is still on).
* After you tap a button, it stays silent until `/health` is 200, then the next outage can alert again.

Set these in `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.8-flash
```

If `GEMINI_API_KEY` is missing, the agent falls back to a simple heuristic diagnosis. Buttons still require your confirmation.

### 4. Restore operations

After you approve **Reset fault**, the agent clears `is_faulty` **inside every pod** (`kubectl exec` → `POST /reset-fault`). A curl through Ingress only reaches one replica, so `/reset-fault` (alias `/reset-default`) via the browser can look “broken” while the other pod is still faulty. This lab uses **1 replica** so health is consistent.

After you approve **Restart pods**, it runs `kubectl rollout restart deployment/network-probe-app`.
