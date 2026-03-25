"""
🤖 AI-Powered SRE Agent Team — CrewAI + Ollama + Kubernetes
Main entry point for the SRE agent system.
"""

import time
import schedule
import threading
from crew import SRECrew
from tools.prometheus_tools import PrometheusTools
from tools.k8s_tools import K8sTools
from config.slo_config import load_slo_definitions
from utils.logger import get_logger

logger = get_logger("main")


def watchdog_loop(crew: SRECrew, prometheus: PrometheusTools):
    """
    Continuously monitors golden signals and triggers
    investigator agent when anomalies are detected.
    """
    logger.info("🐕 Watchdog loop started — monitoring golden signals...")

    services = prometheus.get_all_services()

    for service in services:
        logger.info(f"🔍 Checking service: {service}")

        signals = prometheus.get_golden_signals(service)
        anomaly = detect_anomaly(signals, service)

        if anomaly:
            logger.warning(f"⚠️  Anomaly detected on {service}: {anomaly['reason']}")
            result = crew.run_investigation(service=service, signals=signals, anomaly=anomaly)
            logger.info(f"✅ Investigation complete: {result}")
        else:
            logger.info(f"✅ {service} — all signals healthy")


def detect_anomaly(signals: dict, service: str) -> dict | None:
    """
    Detects anomalies from golden signals.
    Returns anomaly dict or None if healthy.
    """
    # High error rate → likely code bug
    if signals.get("error_rate", 0) > 0.05:
        return {
            "type": "HIGH_ERROR_RATE",
            "reason": f"Error rate {signals['error_rate']:.2%} exceeds 5% threshold",
            "severity": "critical"
        }

    # High latency → performance issue
    if signals.get("latency_p99", 0) > 2.0:
        return {
            "type": "HIGH_LATENCY",
            "reason": f"P99 latency {signals['latency_p99']:.2f}s exceeds 2s SLO",
            "severity": "warning"
        }

    # Zero traffic + zero CPU → zombie process
    if signals.get("traffic_rps", 1) == 0 and signals.get("cpu_usage", 1) == 0:
        return {
            "type": "ZOMBIE_PROCESS",
            "reason": "Zero traffic AND zero CPU — pod is stuck/zombie",
            "severity": "critical"
        }

    # Sudden traffic drop (>80% drop)
    if signals.get("traffic_drop_pct", 0) > 80:
        return {
            "type": "TRAFFIC_DROP",
            "reason": f"Traffic dropped {signals['traffic_drop_pct']:.0f}% — possible outage",
            "severity": "critical"
        }

    return None


def slo_audit_job(crew: SRECrew, prometheus: PrometheusTools):
    """
    Scheduled SLO audit — runs every hour.
    Reads SLO definitions from YAML and evaluates against Prometheus.
    """
    logger.info("📊 Running scheduled SLO audit...")
    slo_definitions = load_slo_definitions("config/slos.yaml")
    results = crew.run_slo_audit(slo_definitions=slo_definitions, prometheus=prometheus)
    logger.info(f"📋 SLO Audit complete: {len(results)} SLOs evaluated")
    for r in results:
        status = "✅" if r["compliant"] else "❌"
        logger.info(f"  {status} {r['service']} — {r['slo_name']}: {r['current_value']:.2%} (target: {r['target']:.2%})")


def main():
    logger.info("🚀 Starting AI-Powered SRE Agent System")
    logger.info("=" * 60)

    # Initialize tools
    prometheus = PrometheusTools(base_url="http://localhost:9090")
    k8s = K8sTools()

    # Initialize CrewAI SRE team
    crew = SRECrew(prometheus=prometheus, k8s=k8s)

    # Schedule SLO audit every hour
    schedule.every(1).hour.do(slo_audit_job, crew=crew, prometheus=prometheus)

    # Run SLO audit immediately on start
    slo_audit_job(crew, prometheus)

    # Start watchdog in background thread
    def run_watchdog():
        while True:
            try:
                watchdog_loop(crew, prometheus)
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(30)  # Check every 30 seconds

    watchdog_thread = threading.Thread(target=run_watchdog, daemon=True)
    watchdog_thread.start()

    # Run scheduler loop
    logger.info("⏰ Scheduler running — Ctrl+C to stop")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
