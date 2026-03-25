## Autonomous AI SRE Crew: Implementation Guide

This solution deploys an Autonomous AI Crew directly into the Kubernetes cluster. It acts as a "Level 1 SRE Team" that never sleeps. It continuously monitors Golden Signals, autonomously investigates anomalies using Pod logs, and executes remediation actions (Restart or Alert) based on the root cause.

### Architecture Overview

The system runs entirely inside Kubernetes as a set of microservices. It follows an Event-Driven Agentic Workflow.
Core Components:

1. The "Target Application" (payment-service):
    - A Python-based web application instrumented with prometheus-client.
    - Exposes metrics on port 8000 (e.g., http_requests_total).
    - Designed to simulate faults: Code Bugs (500 Errors) and Zombie Processes (503 Hangs).

2. The "Observability Stack":
    - Prometheus Operator: Scrapes metrics from the application via ServiceMonitor.
    - ServiceMonitor: The "glue" that auto-discovers the target app and feeds data to Prometheus.

3. The "SRE Crew" (The Brain):
    - Monitor Agent: A "Watchdog" that polls Prometheus every 60s. It looks for Golden Signal violations (Error Rate > 5%, High Latency).
    - Investigator Agent: Triggered only when an anomaly is found. It acts as a senior engineer:
        - Fetches Logs from Kubernetes.
        - Analyzes patterns (Stack traces vs. Silence).
        - Decides on action: Restart Pod (for stuck processes) or Escalate/Alert (for code bugs).
    - Local LLM (Ollama): A 4B parameter model (e.g., gemma3:4b) running locally or remotely, providing the reasoning capabilities without sending data to the cloud.

### Verify prmoetheus connectivity 
```sh
kubectl run prom-test --image=curlimages/curl -n sre-crew -it --restart=Never --rm -- \
curl -v http://prometheus-operated.observability.svc.cluster.local:9090/-/ready
```

### Run a temporary curl pod to test LLM
```sh
kubectl run curl-test --image=curlimages/curl -n sre-crew -it --restart=Never --rm -- \
  curl -X POST http://ollama.ollama.svc.cluster.local:11434/api/generate \
  -d '{"model": "gemma3:4b", "prompt": "Define CrewAI in 5 words", "stream": false}'
```

### Deployment Guide

- Step 1: Deploy Observability & App

```sh
# Deploy the Target App
kubectl apply -f k8s/smart-app.yaml

# Deploy the ServiceMonitor (Connects App to Prometheus)
kubectl apply -f k8s/payment-monitor.yaml
```

- Step 2: Deploy the SRE Crew
```sh
# Install via Helm (injects the Python logic)
helm upgrade --install sre-crew ./sre-crew-chart -n sre-crew --create-namespace
```

- Step 3: Run Simulations
```sh
# Hitting /freeze generates 503s but NO Error Logs
kubectl run traffic-gen -it --rm --image=curlimages/curl -n default -- /bin/sh -c "while true; do curl -s http://payment-service.default.svc.cluster.local/freeze; sleep 0.5; done"
```

### Final Cleanup

When you are done, restore the system to a clean state:
```sh
# Stop the noise
kubectl delete pod traffic-gen -n default

# Delete the SRE Crew
helm uninstall sre-crew -n sre-crew

# Delete the target app components
kubectl delete deployment payment-service
kubectl delete servicemonitor payment-service-monitor
kubectl delete service payment-service
```
