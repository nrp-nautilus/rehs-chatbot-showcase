import os
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes import client

apps_api = client.AppsV1Api()

NAMESPACE = os.environ.get(
    "POD_NAMESPACE",
    "rehs-2026-chatbot",
)


def load_kubernetes_client() -> None:
    """
    Use the pod's ServiceAccount when running in Kubernetes.
    Fall back to ~/.kube/config for local development.
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


load_kubernetes_client()

core_api = client.CoreV1Api()
apps_api = client.AppsV1Api()

def describe_deployment(name: str) -> str:
    deployment = apps_api.read_namespaced_deployment(
        name=name,
        namespace=NAMESPACE,
    )

    return (
        f"Name: {deployment.metadata.name}\n"
        f"Namespace: {deployment.metadata.namespace}\n"
        f"Replicas: {deployment.status.ready_replicas or 0}/"
        f"{deployment.spec.replicas}\n"
        f"Image: {deployment.spec.template.spec.containers[0].image}"
    )


def list_pods() -> str:
    try:
        pods = core_api.list_namespaced_pod(namespace=NAMESPACE)

        if not pods.items:
            return f"No pods found in namespace {NAMESPACE}."

        rows = ["NAME\tSTATUS\tRESTARTS"]

        for pod in pods.items:
            statuses = pod.status.container_statuses or []
            restarts = sum(status.restart_count for status in statuses)

            rows.append(
                f"{pod.metadata.name}\t"
                f"{pod.status.phase}\t"
                f"{restarts}"
            )

        return "\n".join(rows)

    except ApiException as error:
        return format_api_error(error)


def list_deployments() -> str:
    try:
        deployments = apps_api.list_namespaced_deployment(
            namespace=NAMESPACE
        )

        if not deployments.items:
            return f"No deployments found in namespace {NAMESPACE}."

        rows = ["NAME\tREADY\tDESIRED"]

        for deployment in deployments.items:
            ready = deployment.status.ready_replicas or 0
            desired = deployment.spec.replicas or 0

            rows.append(
                f"{deployment.metadata.name}\t"
                f"{ready}\t"
                f"{desired}"
            )

        return "\n".join(rows)

    except ApiException as error:
        return format_api_error(error)


def get_pod_logs(pod_name: str, tail_lines: int = 100) -> str:
    try:
        return core_api.read_namespaced_pod_log(
            name=pod_name,
            namespace=NAMESPACE,
            tail_lines=min(max(tail_lines, 1), 200),
            timestamps=True,
        )

    except ApiException as error:
        return format_api_error(error)


def describe_pod(pod_name: str) -> str:
    try:
        pod = core_api.read_namespaced_pod(
            name=pod_name,
            namespace=NAMESPACE,
        )

        container_statuses = pod.status.container_statuses or []

        details = [
            f"Name: {pod.metadata.name}",
            f"Namespace: {pod.metadata.namespace}",
            f"Status: {pod.status.phase}",
            f"Node: {pod.spec.node_name or 'Not assigned'}",
            f"Pod IP: {pod.status.pod_ip or 'Not assigned'}",
        ]

        for status in container_statuses:
            details.extend(
                [
                    f"Container: {status.name}",
                    f"Ready: {status.ready}",
                    f"Restarts: {status.restart_count}",
                    f"Image: {status.image}",
                ]
            )

        return "\n".join(details)

    except ApiException as error:
        return format_api_error(error)


def format_api_error(error: ApiException) -> str:
    if error.status == 403:
        return (
            "The bot's ServiceAccount is not authorized to perform "
            "this Kubernetes operation."
        )

    if error.status == 404:
        return "The requested Kubernetes resource was not found."

    return f"Kubernetes API error: {error.reason}"