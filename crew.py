"""
🤖 SRE Crew — CrewAI Agent Team Definition
Defines Watchdog, Investigator, Fixer, and SLO Auditor agents.
"""

from crewai import Agent, Task, Crew, Process
from crewai_tools import tool
from langchain_community.llms import Ollama
from tools.prometheus_tools import PrometheusTools
from tools.k8s_tools import K8sTools
from utils.logger import get_logger

logger = get_logger("crew")


def get_llm():
    """Initialize local Ollama LLM — runs privately on your machine."""
    return Ollama(
        model="llama3.1",          # or mistral, codellama, etc.
        base_url="http://localhost:11434",
        temperature=0.1,           # Low temp for deterministic SRE decisions
    )


class SRECrew:
    def __init__(self, prometheus: PrometheusTools, k8s: K8sTools):
        self.prometheus = prometheus
        self.k8s = k8s
        self.llm = get_llm()
        self._build_agents()

    def _build_agents(self):
        """Define the SRE agent team."""

        # ─────────────────────────────────────────
        # 🐕 WATCHDOG AGENT — monitors golden signals
        # ─────────────────────────────────────────
        self.watchdog_agent = Agent(
            role="SRE Watchdog",
            goal=(
                "Continuously monitor Kubernetes services using golden signals "
                "(latency, error rate, traffic, saturation). "
                "Identify anomalies and escalate to the investigator immediately."
            ),
            backstory=(
                "You are a vigilant SRE watchdog with deep expertise in observability. "
                "You've been trained on thousands of production incidents at top financial firms. "
                "You never miss an anomaly and always provide clear signal data."
            ),
            llm=self.llm,
            verbose=True,
            allow_delegation=True,
            tools=[
                self.prometheus.get_golden_signals_tool(),
                self.prometheus.get_all_services_tool(),
            ]
        )

        # ─────────────────────────────────────────
        # 🔬 INVESTIGATOR AGENT — triages issues
        # ─────────────────────────────────────────
        self.investigator_agent = Agent(
            role="SRE Investigator",
            goal=(
                "Investigate anomalies detected by the Watchdog. "
                "Triage the root cause: distinguish between a code bug (high errors), "
                "zombie process (0 CPU + 0 traffic), resource saturation, or network issues. "
                "Provide a clear diagnosis with evidence."
            ),
            backstory=(
                "You are a senior SRE with 15 years of incident response experience. "
                "You specialize in root cause analysis using logs, metrics, and Kubernetes events. "
                "You are methodical, calm under pressure, and never guess — you always verify with data."
            ),
            llm=self.llm,
            verbose=True,
            allow_delegation=True,
            tools=[
                self.prometheus.get_metrics_tool(),
                self.k8s.get_pod_logs_tool(),
                self.k8s.get_events_tool(),
                self.k8s.describe_deployment_tool(),
                self.prometheus.get_error_breakdown_tool(),
            ]
        )

        # ─────────────────────────────────────────
        # 🔧 FIXER AGENT — auto-remediates
        # ─────────────────────────────────────────
        self.fixer_agent = Agent(
            role="SRE Auto-Fixer",
            goal=(
                "Execute remediation actions based on the investigator's diagnosis. "
                "For zombie processes: restart the deployment. "
                "For high errors: trigger rollback to last stable version. "
                "For resource saturation: scale up the deployment. "
                "Always verify the fix worked by re-checking metrics."
            ),
            backstory=(
                "You are an automation-focused SRE engineer who specializes in remediation. "
                "You follow runbooks precisely, never take unnecessary risks, "
                "and always verify your fixes before closing an incident."
            ),
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            tools=[
                self.k8s.rollout_restart_tool(),
                self.k8s.scale_deployment_tool(),
                self.k8s.rollback_deployment_tool(),
                self.prometheus.get_golden_signals_tool(),
            ]
        )

        # ─────────────────────────────────────────
        # 📊 SLO AUDITOR AGENT — evaluates SLOs
        # ─────────────────────────────────────────
        self.slo_auditor_agent = Agent(
            role="SLO Auditor",
            goal=(
                "Evaluate all defined SLOs against current Prometheus metrics. "
                "Calculate error budgets, identify services burning budget too fast, "
                "and generate a clear compliance report with recommendations."
            ),
            backstory=(
                "You are an SRE reliability expert who lives and breathes SLOs. "
                "You understand error budgets, burn rates, and the business impact "
                "of reliability. You produce clear, actionable reports."
            ),
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            tools=[
                self.prometheus.query_range_tool(),
                self.prometheus.get_availability_tool(),
            ]
        )

    def run_investigation(self, service: str, signals: dict, anomaly: dict) -> str:
        """Run full investigate → fix cycle for a detected anomaly."""

        logger.info(f"🚨 Launching investigation crew for {service}")

        # Task 1: Investigate
        investigate_task = Task(
            description=f"""
            Investigate the following anomaly detected on service '{service}':
            
            Anomaly Type: {anomaly['type']}
            Reason: {anomaly['reason']}
            Severity: {anomaly['severity']}
            
            Current Golden Signals:
            - Error Rate: {signals.get('error_rate', 'N/A')}
            - P99 Latency: {signals.get('latency_p99', 'N/A')}s
            - Traffic RPS: {signals.get('traffic_rps', 'N/A')}
            - CPU Usage: {signals.get('cpu_usage', 'N/A')}
            
            Steps:
            1. Fetch recent pod logs for '{service}'
            2. Check Kubernetes events for the namespace
            3. Describe the deployment to check replicas and conditions
            4. If HIGH_ERROR_RATE: analyze error breakdown by endpoint
            5. If ZOMBIE_PROCESS: confirm 0 CPU across all pods
            6. Provide a clear diagnosis with root cause
            """,
            agent=self.investigator_agent,
            expected_output="A detailed root cause analysis with evidence and recommended fix action."
        )

        # Task 2: Fix based on investigation
        fix_task = Task(
            description=f"""
            Based on the investigation findings for service '{service}':
            
            - If root cause is ZOMBIE_PROCESS: execute rollout restart
            - If root cause is CODE_BUG / HIGH_ERROR_RATE: execute rollback to previous revision
            - If root cause is RESOURCE_SATURATION: scale up by 2 replicas
            - After fix: re-query golden signals to confirm service recovered
            - Report fix status: SUCCESS or NEEDS_ESCALATION
            
            Namespace: demo
            Service/Deployment: {service}
            """,
            agent=self.fixer_agent,
            expected_output="Fix execution report with before/after metrics confirming resolution.",
            context=[investigate_task]
        )

        crew = Crew(
            agents=[self.investigator_agent, self.fixer_agent],
            tasks=[investigate_task, fix_task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        return result

    def run_slo_audit(self, slo_definitions: list, prometheus: PrometheusTools) -> list:
        """Run SLO audit across all defined services."""

        slo_descriptions = "\n".join([
            f"- {s['service']}: {s['name']} | Target: {s['target']} | Query: {s['query']}"
            for s in slo_definitions
        ])

        audit_task = Task(
            description=f"""
            Perform a full SLO compliance audit for the following SLO definitions:
            
            {slo_descriptions}
            
            For each SLO:
            1. Query Prometheus using the provided PromQL query
            2. Compare current value against the target
            3. Calculate error budget remaining (% of budget consumed)
            4. Flag any SLO burning budget faster than expected
            5. Return structured results for each SLO
            
            Time window: last 30 days
            """,
            agent=self.slo_auditor_agent,
            expected_output="Structured SLO compliance report with error budgets and recommendations."
        )

        crew = Crew(
            agents=[self.slo_auditor_agent],
            tasks=[audit_task],
            process=Process.sequential,
            verbose=True
        )

        crew.kickoff()

        # Return evaluated results (in real impl, parse agent output)
        return prometheus.evaluate_slos(slo_definitions)
