from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Default CRD configuration used by the controller
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


def _load_config():
    """Load the Kubernetes config depending on environment."""
    if IN_CLUSTER:
        config.load_incluster_config()
    else:
        config.load_kube_config()


def _get_api() -> client.CustomObjectsApi:
    """Return a CustomObjectsApi instance."""
    _load_config()
    return client.CustomObjectsApi()


def create_crd(plural: str, name: str, data: dict):
    """Create a custom resource."""
    api = _get_api()
    body = {
        "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
        "kind": "Data",
        "metadata": {"name": name},
        "data": data,
    }
    return api.create_namespaced_custom_object(
        CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, body
    )


def read_crd(plural: str, name: str):
    """Read a custom resource and return the stored data or None."""
    api = _get_api()
    try:
        obj = api.get_namespaced_custom_object(
            CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, name
        )
        return obj.get("data")
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def update_crd(plural: str, name: str, data: dict):
    """Replace the custom resource with new data."""
    api = _get_api()
    body = {
        "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
        "kind": "Data",
        "metadata": {"name": name},
        "data": data,
    }
    return api.replace_namespaced_custom_object(
        CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, name, body
    )


def delete_crd(plural: str, name: str):
    """Delete a custom resource."""
    api = _get_api()
    return api.delete_namespaced_custom_object(
        CRD_GROUP, CRD_VERSION, CRD_NAMESPACE, plural, name
    )

