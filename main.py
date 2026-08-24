import os, time
from fastapi import FastAPI, Response, status

app = FastAPI(title="Network Probing & Quality Service")
is_faulty = False

@app.get("/health")
def health_check(response: Response):
    global is_faulty
    if is_faulty:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Simulated hardware/network fault!"}
    return {"status": "OK", "latency_ms": 12}

@app.post("/simulate-fault")
def trigger_fault():
    global is_faulty
    is_faulty = True
    return {"message": "Trouble injected! System entering FAULT state."}

@app.post("/reset-fault")
def reset_fault():
    global is_faulty
    is_faulty = False
    return {"message": "System state restored."}

