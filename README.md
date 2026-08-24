# Automated Lab (K8s Auto-Healing)

An automated Kubernetes lab simulating a network service with **NGINX Ingress** routing and a **Python Recovery Agent** for real-time monitoring, automated log extraction, and self-healing.

## Disaster Simulation & Recovery

### 1. Run Monitoring Agent

python scripts/tr_recovery_agent.py


### 2. Trigger Incident

curl -X POST http://automated-lab.local/simulate-fault

### 3. Auto-Healing Actions

The Recovery Agent automatically:

* Detects HTTP failure on `/health`.
* Captures Pod logs to `incident_report.log`.
* Sends an alert via Telegram.

### 4. Restore Operations

The agent triggers `/reset-fault` to automatically restore normal operations.
