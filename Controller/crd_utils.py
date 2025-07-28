from typing import Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Kubernetes CRD settings
CRD_GROUP = "ha.example.com"
CRD_VERSION = "v1"
CRD_NAMESPACE = "default"

SERVICE_PLURAL = "services"
SERVICE_NAME = "service-info"

SERVICESPEC_PLURAL = "servicespecs"
SERVICESPEC_NAME = "servicespec-info"

SUBSCRIPTION_PLURAL = "subscriptions"
SUBSCRIPTION_NAME = "subscription-info"

NODESTATUS_PLURAL = "nodestatuses"
NODESTATUS_NAME = "nodestatus-info"

IN_CLUSTER = True


def _load_config() -> None:
    config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()


def _get_api() -> client.CustomObjectsApi:
    _load_config()
    return client.CustomObjectsApi()


def _build_body(name: str, data: Any) -> dict:
    return {
        "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
        "kind": "Data",
        "metadata": {"name": name},
        "data": data,
    }


def create_crd(plural: str, name: str, data: Any) -> Any:
    api = _get_api()
    body = _build_body(name, data)
    return api.create_namespaced_custom_object(
        CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, body
    )


def read_crd(plural: str, name: str) -> Any | None:
    api = _get_api()
    try:
        obj = api.get_namespaced_custom_object(
            CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, name
        )
        return obj.get("data", {})
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def update_crd(plural: str, name: str, data: Any) -> None:
    api = _get_api()
    body = _build_body(name, data)
    try:
        api.replace_namespaced_custom_object(
            CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, name, body
        )
    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_custom_object(
                CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, body
            )
        else:
            raise


def delete_crd(plural: str, name: str) -> None:
    api = _get_api()
    try:
        api.delete_namespaced_custom_object(
            CRD_GROUP,
            CRD_VERSION,
            CRD_NAMESPACE,
            plural,
            name,
            client.V1DeleteOptions(),
        )
    except ApiException as e:
        if e.status != 404:
            raise


# Convenience wrappers for controller usage

def load_service_data() -> list:
    return read_crd(SERVICE_PLURAL, SERVICE_NAME) or []


def save_service_data(data: Any) -> None:
    update_crd(SERVICE_PLURAL, SERVICE_NAME, data)


def load_servicespec_data() -> list:
    return read_crd(SERVICESPEC_PLURAL, SERVICESPEC_NAME) or []


def save_servicespec_data(data: Any) -> None:
    update_crd(SERVICESPEC_PLURAL, SERVICESPEC_NAME, data)


def load_subscription_data() -> list:
    return read_crd(SUBSCRIPTION_PLURAL, SUBSCRIPTION_NAME) or []


def save_subscription_data(data: Any) -> None:
    update_crd(SUBSCRIPTION_PLURAL, SUBSCRIPTION_NAME, data)


def load_nodestatus_data() -> dict:
    return read_crd(NODESTATUS_PLURAL, NODESTATUS_NAME) or {}


def save_nodestatus_data(data: Any) -> None:
    update_crd(NODESTATUS_PLURAL, NODESTATUS_NAME, data)

