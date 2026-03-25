from crewai import Agent, LLM
from tools import PrometheusTool, K8sOperationsTool, AlertTool
import os

llm = LLM(
    model=f"openai/{os.getenv('OPENAI_MODEL_NAME', 'gemma3:4b')}", 
    base_url=os.getenv("OPENAI_API_BASE"),
    api_key=os.getenv("OPENAI_API_KEY", "NA")
)

# Tools
prom_tool = PrometheusTool()
k8s_tool = K8sOperationsTool()
alert_tool = AlertTool()

def get_monitor_agent():
    return Agent(
        role='SRE Watchdog',
        goal='Monitor system health via Prometheus Golden Signals.',
        backstory='You are a vigilant site reliability engineer. You interpret raw metrics. You are paranoid about latency spikes and error rates.',
        tools=[prom_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

def get_investigator_agent():
    return Agent(
        role='Root Cause Investigator',
        goal='Analyze anomalies and Fix them.',
        backstory='You are a senior site reliability engineer. You look at logs and metrics to distinguish between zombie processes and code bugs.',
        tools=[k8s_tool, alert_tool, prom_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

def get_slo_agent():
    return Agent(
        role='SLO Auditor',
        goal='Ensure compliance with targets.',
        backstory='You are a compliance officer. You check if the system meets the defined availability and latency targets.',
        tools=[prom_tool, alert_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False
    )