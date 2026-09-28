# Automated Lab (K8s Auto-Healing)

An automated Kubernetes lab simulating a network service with NGINX Ingress routing, Redis shared state, and a Python recovery agent powered by Gemini AI for real-time monitoring, automated log extraction, and self-healing.

## Overview

This project demonstrates a simple self-healing Kubernetes environment:

- a FastAPI app exposes health and fault endpoints
- Redis stores the fault state across replicas
- a monitoring agent watches `/health`
- Gemini AI analyzes logs and recommends a recovery action
- Telegram sends approval prompts before any recovery command runs

---

## Prerequisites

Start the Minikube tunnel:

```bash
minikube tunnel
```

Configure `/etc/hosts`:

```bash
127.0.0.1 automated-lab.local
```

---

## Environment Setup

Create a `.env` file and add the following values:

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.5-flash
```

---

## Run the Lab

### 1. Start the monitoring agent

```bash
source venv/bin/activate
python scripts/tr_recovery_agent.py
```

### 2. Trigger the incident

```bash
curl -X POST http://automated-lab.local/simulate-fault
```

### 3. Observe the recovery flow

The recovery agent will:

- detect an HTTP 500 failure on `/health`
- capture pod logs into `incident_report.log`
- send logs to Gemini AI for diagnosis
- propose one recovery action: `reset_fault`, `restart_pod`, or `none`
- send the proposal to Telegram with interactive Execute / Ignore buttons
- execute the action only after operator confirmation
- keep Redis state synchronized across all replicas

---

## Core Components

- `main.py` — FastAPI application with health and fault endpoints
- `scripts/tr_recovery_agent.py` — monitoring, diagnosis, Telegram approval, and recovery logic
- `k8s/` — Kubernetes deployment and service manifests
- `redis` — shared state for fault simulation across replicas
- `Ingress` — routes traffic through `automated-lab.local`

---

## Useful Commands

Check app health:

```bash
curl http://automated-lab.local/health
```

Reset the fault manually:

```bash
curl -X POST http://automated-lab.local/reset-fault
```

View running pods:

```bash
kubectl get pods
```

View pod logs:

```bash
kubectl logs -l app=network-probe
```

---

## Notes

This project is intended for local Kubernetes experimentation and automated recovery testing. It is designed as a lab/demo environment rather than a production-ready system.
