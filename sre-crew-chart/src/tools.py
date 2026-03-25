from crewai.tools import BaseTool
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect
import os
import requests

try:
    config.load_incluster_config()
except:
    config.load_kube_config()

class PrometheusTool(BaseTool):
    name: str = "Prometheus Query Tool"
    description: str = "Queries Prometheus for Golden Signals (Latency, Error Rate, Traffic). Input: 'query_string'"

    def _run(self, query: str) -> str:
        prom_url = os.getenv("PROMETHEUS_URL", "http://prometheus-operated.observability.svc.cluster.local:9090")
        prom = PrometheusConnect(url=prom_url, disable_ssl=True)
        
        try:
            result = prom.custom_query(query=query)
            return str(result)
        except Exception as e:
            return f"Error querying Prometheus: {e}"

class K8sOperationsTool(BaseTool):
    name: str = "Kubernetes Operations Tool"
    description: str = "Performs K8s actions. Input string format: 'ACTION target_name namespace'. Actions: 'RESTART', 'GET_LOGS'."

    def _run(self, operation: str) -> str:
        try:
            parts = operation.split(" ")
            action, target, namespace = parts[0], parts[1], parts[2]
            v1 = client.CoreV1Api()
            apps_v1 = client.AppsV1Api()

            if action == "RESTART":
                import datetime
                patch_body = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubectl.kubernetes.io/restartedAt": str(datetime.datetime.now())
                                }
                            }
                        }
                    }
                }
                apps_v1.patch_namespaced_deployment(target, namespace, patch_body)
                return f"Successfully triggered rollout restart for {target} in {namespace}."
            
            elif action == "GET_LOGS":
                pods = v1.list_namespaced_pod(namespace, label_selector=f"app={target}")
                if not pods.items:
                    return "No pods found."
                pod_name = pods.items[0].metadata.name
                return v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=50)

        except Exception as e:
            return f"K8s Operation Failed: {e}"
        return "Invalid Operation format."

class AlertTool(BaseTool):
    name: str = "Alert Webhook Tool"
    description: str = "Sends alerts to the team via Webhook. Input: 'Message string'"

    def _run(self, message: str) -> str:
        # Simulate a Slack/PagerDuty Webhook
        print(f"🔴 [ALERT SENT]: {message}")
        return "Alert Sent Successfully."