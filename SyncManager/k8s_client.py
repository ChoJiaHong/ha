"""Utility wrapper around the Kubernetes Python client."""

from kubernetes import client, config
from kubernetes.client.rest import ApiException


def create_api_client():
    """Create a CustomObjectsApi instance and load configuration.

    Tries in-cluster config first and falls back to kubeconfig for
    development environments.
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CustomObjectsApi()


def get_custom_object(api, group, version, namespace, plural, name):
    return api.get_namespaced_custom_object(group, version, namespace, plural, name)


def patch_custom_object(api, group, version, namespace, plural, name, body):
    return api.patch_namespaced_custom_object(group, version, namespace, plural, name, body)


def replace_custom_object(api, group, version, namespace, plural, name, body):
    return api.replace_namespaced_custom_object(group, version, namespace, plural, name, body)
