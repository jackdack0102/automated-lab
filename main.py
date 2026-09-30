import os, time
from fastapi import FastAPI, Response, status
import redis
import logging
from pythonjsonlogger import jsonlogger

#Config Logger stdout as JSON
POD_NAME = os.getenv("POD_NAME", os.getenv("HOSTNAME", "unknown-pod"))

logger = logging.getLogger("network-probe")
logHandler = logging.StreamHandler()
# Dùng asctime cho timestamp và %(message)s cho nội dung
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(pod_name)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

app = FastAPI(title="Network Probing & Quality Service")

# Connect to Redis Service in K8s
REDIS_HOST = os.getenv("REDIS_HOST", "redis-service")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

@app.get("/health")
def health_check(response: Response):
    try:
        is_faulty = redis_client.get("is_faulty") == "true"
    except Exception as e:
        logger.error("Failed to connect to Redis", extra={"pod_name": POD_NAME, "error": str(e)})
        is_faulty = False

    if is_faulty:
        # write log in JSON when having Inject Fault
        logger.error("Simulated hardware/network fault detected on /health check", extra={"pod_name": POD_NAME, "status_code": 500})
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Simulated hardware/network fault!"}
    
    # Log status OK 
    logger.info("Health check OK", extra={"pod_name": POD_NAME, "status_code": 200})
    return {"status": "OK", "latency_ms": 12}

@app.post("/simulate-fault")
def trigger_fault():
    redis_client.set("is_faulty", "true")
    logger.warning("Fault injection triggered", extra={"pod_name": POD_NAME, "action": "simulate-fault"})
    return {"message": "Trouble injected! System entering FAULT state across all replicas."}

@app.post("/reset-fault")
def reset_fault():
    redis_client.set("is_faulty", "false")
    logger.info("Fault reset triggered", extra={"pod_name": POD_NAME, "action": "reset-fault"})
    return {"message": "System state restored across all replicas."}