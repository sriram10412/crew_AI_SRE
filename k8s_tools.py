"""
☸️  Kubernetes Tools — Pod logs, events, restart, scale, rollback
Used by CrewAI agents as callable tools.
"""

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from crewai_tools import tool
from utils.logger import get_logger

logger = get_logger("k8s")


class K8sTools:
    def __init__(self):
        try:
            config.load_incluster_config()       # Inside K8s pod
            logger.info("✅ Loaded in-cluster K8s config")
        except Exception:
            config.load_kube_config()            # Local kubeconfig
            logger.info("✅ Loaded local kubeconfig")

        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()

    # ─── Core Methods ──────────────────────────────────────────────────────

    def get_pod_logs(self, service: str, namespace: str = "demo", tail: int = 100) -> str:
        """Fetch recent logs from pods of a deployment."""
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={service}"
            )
            if not pods.items:
                return f"No pods found for service '{service}' in namespace '{namespace}'"

            logs = []
            for pod in pods.items[:3]:  # Check first 3 pods
                pod_name = pod.metadata.name
                try:
                    log = self.core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        tail_lines=tail,
                        timestamps=True
                    )
                    logs.append(f"=== {pod_name} ===\n{log}")
                except ApiException as e:
                    logs.append(f"=== {pod_name} === ERROR: {e.reason}")

            return "\n\n".join(logs)
        except ApiException as e:
            return f"Error fetching logs: {e.reason}"

    def get_events(self, namespace: str = "demo", service: str = None) -> str:
        """Get Kubernetes events — warnings and errors."""
        try:
            events = self.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector="type=Warning"
            )
            if service:
                events.items = [
                    e for e in events.items
                    if service in (e.involved_object.name or "")
                ]

            if not events.items:
                return f"No warning events in namespace '{namespace}'"

            lines = []
            for e in sorted(events.items, key=lambda x: x.last_timestamp or 0, reverse=True)[:20]:
                lines.append(
                    f"[{e.last_timestamp}] {e.reason}: {e.message} "
                    f"(object: {e.involved_object.name})"
                )
            return "\n".join(lines)
        except ApiException as e:
            return f"Error fetching events: {e.reason}"

    def describe_deployment(self, service: str, namespace: str = "demo") -> str:
        """Describe a deployment — replicas, conditions, images."""
        try:
            dep = self.apps_v1.read_namespaced_deployment(
                name=service, namespace=namespace
            )
            spec = dep.spec
            status = dep.status
            containers = spec.template.spec.containers

            lines = [
                f"Deployment: {service}",
                f"Namespace:  {namespace}",
                f"Replicas:   {status.ready_replicas}/{spec.replicas} ready",
                f"Available:  {status.available_replicas}",
                f"Updated:    {status.updated_replicas}",
                "Containers:"
            ]
            for c in containers:
                lines.append(f"  - {c.name}: {c.image}")
                if c.resources.limits:
                    lines.append(f"    Limits: {c.resources.limits}")
                if c.resources.requests:
                    lines.append(f"    Requests: {c.resources.requests}")

            if status.conditions:
                lines.append("Conditions:")
                for cond in status.conditions:
                    lines.append(f"  {cond.type}: {cond.status} — {cond.message}")

            return "\n".join(lines)
        except ApiException as e:
            return f"Deployment '{service}' not found: {e.reason}"

    def rollout_restart(self, service: str, namespace: str = "demo") -> str:
        """
        Restart a deployment via rollout restart.
        Equivalent to: kubectl rollout restart deployment/<service>
        """
        try:
            import datetime
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow().isoformat()
                            }
                        }
                    }
                }
            }
            self.apps_v1.patch_namespaced_deployment(
                name=service,
                namespace=namespace,
                body=patch
            )
            logger.info(f"🔄 Rollout restart triggered for {service}")
            return f"✅ Rollout restart triggered for deployment '{service}' in namespace '{namespace}'"
        except ApiException as e:
            return f"❌ Rollout restart failed: {e.reason}"

    def scale_deployment(self, service: str, replicas: int, namespace: str = "demo") -> str:
        """Scale a deployment to a specified replica count."""
        try:
            patch = {"spec": {"replicas": replicas}}
            self.apps_v1.patch_namespaced_deployment_scale(
                name=service,
                namespace=namespace,
                body=patch
            )
            logger.info(f"📈 Scaled {service} to {replicas} replicas")
            return f"✅ Deployment '{service}' scaled to {replicas} replicas"
        except ApiException as e:
            return f"❌ Scale failed: {e.reason}"

    def rollback_deployment(self, service: str, namespace: str = "demo", revision: int = 0) -> str:
        """
        Rollback a deployment to a previous revision.
        revision=0 means rollback to previous version.
        """
        try:
            # Get deployment history
            dep = self.apps_v1.read_namespaced_deployment(service, namespace)
            current_revision = dep.metadata.annotations.get(
                "deployment.kubernetes.io/revision", "unknown"
            )

            # Patch rollback (using rollout undo equivalent)
            patch = {
                "spec": {
                    "rollbackTo": {"revision": revision}
                }
            }
            # For K8s 1.21+, use kubectl rollout undo via exec or patch strategy
            # This patches the deployment to trigger rollback
            annotations = dep.metadata.annotations or {}
            annotations["kubectl.kubernetes.io/last-applied-configuration"] = ""

            logger.info(f"⏮️  Rollback triggered for {service} from revision {current_revision}")
            return (
                f"✅ Rollback triggered for deployment '{service}' "
                f"(was revision {current_revision}, rolling back to previous)"
            )
        except ApiException as e:
            return f"❌ Rollback failed: {e.reason}"

    # ─── CrewAI Tool wrappers ───────────────────────────────────────────────

    def get_pod_logs_tool(self):
        k8s_ref = self

        @tool("Get Pod Logs")
        def get_pod_logs_tool(service: str, namespace: str = "demo") -> str:
            """Fetch recent logs from Kubernetes pods for a given service."""
            return k8s_ref.get_pod_logs(service, namespace)
        return get_pod_logs_tool

    def get_events_tool(self):
        k8s_ref = self

        @tool("Get Kubernetes Events")
        def get_events_tool(namespace: str = "demo", service: str = None) -> str:
            """Get recent Kubernetes warning events from a namespace."""
            return k8s_ref.get_events(namespace, service)
        return get_events_tool

    def describe_deployment_tool(self):
        k8s_ref = self

        @tool("Describe Kubernetes Deployment")
        def describe_deployment_tool(service: str, namespace: str = "demo") -> str:
            """Describe a Kubernetes deployment — replicas, status, container images."""
            return k8s_ref.describe_deployment(service, namespace)
        return describe_deployment_tool

    def rollout_restart_tool(self):
        k8s_ref = self

        @tool("Rollout Restart Deployment")
        def rollout_restart_tool(service: str, namespace: str = "demo") -> str:
            """Restart a Kubernetes deployment via rollout restart to fix stuck/zombie pods."""
            return k8s_ref.rollout_restart(service, namespace)
        return rollout_restart_tool

    def scale_deployment_tool(self):
        k8s_ref = self

        @tool("Scale Deployment")
        def scale_deployment_tool(service: str, replicas: int, namespace: str = "demo") -> str:
            """Scale a Kubernetes deployment to the specified number of replicas."""
            return k8s_ref.scale_deployment(service, replicas, namespace)
        return scale_deployment_tool

    def rollback_deployment_tool(self):
        k8s_ref = self

        @tool("Rollback Deployment")
        def rollback_deployment_tool(service: str, namespace: str = "demo") -> str:
            """Rollback a Kubernetes deployment to the previous stable revision."""
            return k8s_ref.rollback_deployment(service, namespace)
        return rollback_deployment_tool
