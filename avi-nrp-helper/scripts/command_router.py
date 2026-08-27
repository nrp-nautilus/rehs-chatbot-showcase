import re

from kubernetes_tools import (
    describe_pod,
    get_pod_logs,
    list_deployments,
    list_pods,
    describe_deployment,
)


def run_kubernetes_command(question: str) -> tuple[bool, str]:
    normalized = " ".join(question.lower().strip().split())

    pod_list_phrases = (
        "list pods",
        "get pods",
        "show pods",
        "check pods",
        "pods running",
        "what pods",
        "which pods",
    )

    if any(phrase in normalized for phrase in pod_list_phrases):
        return True, list_pods()

    deployment_phrases = (
        "list deployments",
        "get deployments",
        "show deployments",
        "check deployments",
        "what deployments",
        "which deployments",
    )

    if any(phrase in normalized for phrase in deployment_phrases):
        return True, list_deployments()

    log_match = re.fullmatch(
        r"(?:kubectl )?(?:get|show|check)?\s*logs?"
        r"(?: for| of| from)?\s+([a-z0-9.-]+)",
        normalized,
    )

    if log_match:
        return True, get_pod_logs(log_match.group(1))

    describe_match = re.fullmatch(
        r"(?:kubectl )?describe pod\s+([a-z0-9.-]+)",
        normalized,
    )

    if describe_match:
        return True, describe_pod(describe_match.group(1))

    deployment_match = re.fullmatch(
    r"(?:kubectl )?describe (?:the )?([a-z0-9.-]+) deployment",
    normalized,
)

    if deployment_match:
        return True, describe_deployment(deployment_match.group(1))

    return False, ""