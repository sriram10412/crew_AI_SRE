from crewai import Task
from textwrap import dedent

class SRETasks:
    def monitor_health_task(self, agent, target_service="payment-service", namespace="default"):
        return Task(
            description=dedent(f"""
                **Goal**: Assess the health of '{target_service}' in namespace '{namespace}'.
                
                **Instructions**:
                1. Use the PrometheusTool to execute these EXACT queries one by one. DO NOT modify them:
                   
                   - **Error Rate Query**: 
                     `sum(rate(http_requests_total{{status=~"5.."}}[1m])) / sum(rate(http_requests_total[1m]))`
                   
                   - **Latency Query**: 
                     `histogram_quantile(0.95, sum(rate(http_requests_duration_seconds_bucket[1m])) by (le))`
                   
                   - **CPU Usage Query**: 
                     `sum(rate(container_cpu_usage_seconds_total{{pod=~"{target_service}.*"}}[1m]))`

                2. Evaluate results:
                   - Error Rate > 0.05 (5%) -> ANOMALY
                   - Latency > 2.0 (2 seconds) -> ANOMALY
                   - CPU < 0.01 AND Error Rate > 0 -> ANOMALY (Potential Zombie)
                
                **Output**: 
                - If all good, return exactly: "HEALTHY"
                - If issues found, return: "ANOMALY: [Explain which metric failed]"
            """),
            agent=agent,
            expected_output="A status string starting with 'HEALTHY' or 'ANOMALY'."
        )

    def investigate_issue_task(self, agent, issue_context, target_service="payment-service", namespace="default"):
        return Task(
            description=dedent(f"""
                **Context**: The Monitor Agent detected: "{issue_context}"
                
                **Goal**: Fix '{target_service}'.
                
                **Instructions**:
                1. Use K8sOperationsTool to 'GET_LOGS {target_service} {namespace}'.
                2. Analyze logs:
                   - If logs look normal but traffic is failing (Zombie) -> Use K8sOperationsTool: 'RESTART {target_service} {namespace}'
                   - If logs show Python/Java exceptions (Code Bug) -> Use AlertTool: 'Bug detected in {target_service}'
                
                **Output**: Final action taken.
            """),
            agent=agent,
            expected_output="Action report."
        )

    def slo_audit_task(self, agent, slo_config):
        return Task(
            description=dedent(f"""
                **Goal**: Audit SLO compliance.
                
                **Instructions**:
                1. Iterate through these targets:
                {slo_config}
                
                2. For each target, run the query provided in the config using PrometheusTool.
                3. Compare result vs target.
                
                **Output**: Pass/Fail report.
            """),
            agent=agent,
            expected_output="SLO Report."
        )