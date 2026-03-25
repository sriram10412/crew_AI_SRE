"""
📊 Prometheus Tools — Query golden signals, metrics, SLOs
Used by CrewAI agents as callable tools.
"""

import requests
from datetime import datetime, timedelta
from crewai_tools import tool
from utils.logger import get_logger

logger = get_logger("prometheus")


class PrometheusTools:
    def __init__(self, base_url: str = "http://localhost:9090"):
        self.base_url = base_url

    def query(self, promql: str) -> dict:
        """Execute an instant PromQL query."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/query",
                params={"query": promql},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("result", [])
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return []

    def query_range(self, promql: str, hours: int = 1) -> list:
        """Execute a range PromQL query."""
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start.timestamp(),
                    "end": end.timestamp(),
                    "step": "60s"
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("result", [])
        except Exception as e:
            logger.error(f"Prometheus range query failed: {e}")
            return []

    def get_all_services(self) -> list[str]:
        """Get all services currently tracked in Prometheus."""
        result = self.query('group by (service) (up{job="kubernetes-pods"})')
        return [r["metric"].get("service", "unknown") for r in result]

    def get_golden_signals(self, service: str) -> dict:
        """
        Fetch the 4 golden signals for a service:
        - Latency (P99)
        - Error Rate
        - Traffic (RPS)
        - CPU Usage (Saturation)
        """
        signals = {}

        # Latency P99
        latency = self.query(
            f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))'
        )
        signals["latency_p99"] = float(latency[0]["value"][1]) if latency else 0.0

        # Error Rate
        error_rate = self.query(
            f'rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]) / '
            f'rate(http_requests_total{{service="{service}"}}[5m])'
        )
        signals["error_rate"] = float(error_rate[0]["value"][1]) if error_rate else 0.0

        # Traffic RPS
        traffic = self.query(
            f'rate(http_requests_total{{service="{service}"}}[5m])'
        )
        signals["traffic_rps"] = float(traffic[0]["value"][1]) if traffic else 0.0

        # CPU Usage
        cpu = self.query(
            f'rate(container_cpu_usage_seconds_total{{container="{service}"}}[5m])'
        )
        signals["cpu_usage"] = float(cpu[0]["value"][1]) if cpu else 0.0

        logger.info(f"📊 Golden signals for {service}: {signals}")
        return signals

    def get_error_breakdown(self, service: str) -> dict:
        """Break down errors by endpoint and status code."""
        result = self.query(
            f'topk(5, rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])) by (endpoint, status)'
        )
        breakdown = {}
        for r in result:
            endpoint = r["metric"].get("endpoint", "unknown")
            status = r["metric"].get("status", "unknown")
            rate = float(r["value"][1])
            breakdown[f"{endpoint} [{status}]"] = rate
        return breakdown

    def get_availability(self, service: str, hours: int = 720) -> float:
        """Calculate availability over a time window (default 30 days)."""
        result = self.query(
            f'1 - (sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[{hours}h])) / '
            f'sum(rate(http_requests_total{{service="{service}"}}[{hours}h])))'
        )
        return float(result[0]["value"][1]) if result else 1.0

    def evaluate_slos(self, slo_definitions: list) -> list:
        """Evaluate all SLOs against Prometheus and return compliance results."""
        results = []
        for slo in slo_definitions:
            result = self.query(slo["query"])
            current_value = float(result[0]["value"][1]) if result else 0.0
            target = slo["target"]
            compliant = current_value >= target
            error_budget_consumed = max(0, (target - current_value) / (1 - target)) if not compliant else 0.0

            results.append({
                "service": slo["service"],
                "slo_name": slo["name"],
                "current_value": current_value,
                "target": target,
                "compliant": compliant,
                "error_budget_consumed_pct": error_budget_consumed * 100,
            })
        return results

    # ─── CrewAI Tool wrappers ───────────────────────────────────────────────

    def get_golden_signals_tool(self):
        prometheus_ref = self

        @tool("Get Golden Signals")
        def get_golden_signals_tool(service: str) -> str:
            """Fetch latency, error rate, traffic, and CPU signals for a service from Prometheus."""
            signals = prometheus_ref.get_golden_signals(service)
            return (
                f"Golden Signals for {service}:\n"
                f"  P99 Latency: {signals['latency_p99']:.3f}s\n"
                f"  Error Rate:  {signals['error_rate']:.2%}\n"
                f"  Traffic RPS: {signals['traffic_rps']:.2f}\n"
                f"  CPU Usage:   {signals['cpu_usage']:.4f}"
            )
        return get_golden_signals_tool

    def get_all_services_tool(self):
        prometheus_ref = self

        @tool("List All Services")
        def get_all_services_tool() -> str:
            """List all services being monitored in Prometheus."""
            services = prometheus_ref.get_all_services()
            return f"Monitored services: {', '.join(services)}"
        return get_all_services_tool

    def get_metrics_tool(self):
        prometheus_ref = self

        @tool("Query Prometheus Metrics")
        def get_metrics_tool(promql: str) -> str:
            """Execute a PromQL query against Prometheus and return results."""
            result = prometheus_ref.query(promql)
            return str(result)
        return get_metrics_tool

    def get_error_breakdown_tool(self):
        prometheus_ref = self

        @tool("Get Error Breakdown")
        def get_error_breakdown_tool(service: str) -> str:
            """Get error breakdown by endpoint and status code for a service."""
            breakdown = prometheus_ref.get_error_breakdown(service)
            lines = [f"  {endpoint}: {rate:.4f} rps" for endpoint, rate in breakdown.items()]
            return f"Error breakdown for {service}:\n" + "\n".join(lines)
        return get_error_breakdown_tool

    def query_range_tool(self):
        prometheus_ref = self

        @tool("Query Prometheus Range")
        def query_range_tool(promql: str, hours: int = 24) -> str:
            """Execute a Prometheus range query for time-series data."""
            result = prometheus_ref.query_range(promql, hours)
            return f"Range query returned {len(result)} series"
        return query_range_tool

    def get_availability_tool(self):
        prometheus_ref = self

        @tool("Get Service Availability")
        def get_availability_tool(service: str) -> str:
            """Calculate availability percentage for a service over the last 30 days."""
            avail = prometheus_ref.get_availability(service)
            return f"Availability for {service} (30d): {avail:.4%}"
        return get_availability_tool
