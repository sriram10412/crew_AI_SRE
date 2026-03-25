import time
import schedule
import yaml
from crewai import Crew
from agents import get_monitor_agent, get_investigator_agent, get_slo_agent
from tasks import SRETasks

try:
    with open("slos.yaml", 'r') as stream:
        SLO_CONFIG = yaml.safe_load(stream)
except FileNotFoundError:
    print("Warning: slos.yaml not found, using empty config.")
    SLO_CONFIG = {}

tasks = SRETasks()

def run_monitor_cycle():
    print("\n--- 🔍 Starting Monitor Cycle ---")
    monitor_agent = get_monitor_agent()
    monitor_task = tasks.monitor_health_task(
        agent=monitor_agent,
        target_service="payment-service",
        namespace="default"
    )
    crew = Crew(
        agents=[monitor_agent], 
        tasks=[monitor_task], 
        verbose=False 
    )
    result = crew.kickoff()
    
    output = str(result).strip()
    print(f"Monitor Output: {output}")

    if "ANOMALY" in output:
        trigger_investigation(output)

def trigger_investigation(issue_context):
    print("\n--- 🚨 Anomaly Detected! Triggering Investigator ---")
    investigator_agent = get_investigator_agent()
    investigation_task = tasks.investigate_issue_task(
        agent=investigator_agent,
        issue_context=issue_context,
        target_service="payment-service",
        namespace="default"
    )
    
    crew = Crew(
        agents=[investigator_agent], 
        tasks=[investigation_task]
    )
    crew.kickoff()

def run_slo_audit():
    print("\n--- 📊 Starting SLO Audit ---")
    auditor_agent = get_slo_agent()
    
    audit_task = tasks.slo_audit_task(
        agent=auditor_agent, 
        slo_config=SLO_CONFIG
    )
    
    crew = Crew(
        agents=[auditor_agent], 
        tasks=[audit_task]
    )
    crew.kickoff()

schedule.every(60).seconds.do(run_monitor_cycle)
schedule.every(5).minutes.do(run_slo_audit)

print("🚀 Autonomous SRE Crew Started...")
print("   - Monitor: Every 60s")
print("   - SLO Audit: Every 5m")

if __name__ == "__main__":
    run_monitor_cycle()
    
    while True:
        schedule.run_pending()
        time.sleep(1)