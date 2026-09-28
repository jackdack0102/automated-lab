import os, time
from fastapi import FastAPI, Response, status
import redis


app = FastAPI(title="Network Probing & Quality Service")
is_faulty = False

# Connect to Redis Service in K8s via environment variables (default host is 'redis-service')
REDIS_HOST = os.getenv("REDIS_HOST", "redis-service")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

@app.get("/health")
def health_check(response: Response):
    # Read the status from Redis
    try:
        is_faulty = redis_client.get("is_faulty") == "true"
    except Exception as e:
        # If Redis is disconnected, default to an error or log
        is_faulty = False

    if is_faulty:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Simulated hardware/network fault!"}
    
    return {"status": "OK", "latency_ms": 12}

@app.post("/simulate-fault")
def trigger_fault():
    # save state fault = true to Redis
    redis_client.set("is_faulty", "true")
    return {"message": "Trouble injected! System entering FAULT state across all replicas."}

@app.post("/reset-fault")
def reset_fault():
    # Reset state
    redis_client.set("is_faulty", "false")
    return {"message": "System state restored across all replicas."}
