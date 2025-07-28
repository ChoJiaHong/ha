import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Create minimal kubernetes stubs for import
kube = types.ModuleType("kubernetes")
client_mod = types.ModuleType("kubernetes.client")
config_mod = types.ModuleType("kubernetes.config")
rest_mod = types.ModuleType("kubernetes.client.rest")

class DummyApiException(Exception):
    def __init__(self, status=None):
        self.status = status

client_mod.CustomObjectsApi = MagicMock
client_mod.V1DeleteOptions = MagicMock
config_mod.load_kube_config = MagicMock()
config_mod.load_incluster_config = MagicMock()
rest_mod.ApiException = DummyApiException

kube.client = client_mod
kube.config = config_mod
sys.modules['kubernetes'] = kube
sys.modules['kubernetes.client'] = client_mod
sys.modules['kubernetes.config'] = config_mod
sys.modules['kubernetes.client.rest'] = rest_mod

from Controller import crd_utils

class TestCRDUtils(unittest.TestCase):
    @patch('Controller.crd_utils.client.CustomObjectsApi')
    def test_crud_operations(self, api_cls):
        api = MagicMock()
        api_cls.return_value = api

        # create
        crd_utils.create_crd('foos', 'foo', {'a': 1})
        body = {
            'apiVersion': f"{crd_utils.CRD_GROUP}/{crd_utils.CRD_VERSION}",
            'kind': 'Data',
            'metadata': {'name': 'foo'},
            'data': {'a': 1},
        }
        api.create_namespaced_custom_object.assert_called_with(
            crd_utils.CRD_GROUP,
            crd_utils.CRD_VERSION,
            crd_utils.CRD_NAMESPACE,
            'foos',
            body,
        )

        # read success
        api.get_namespaced_custom_object.return_value = {'data': {'a': 1}}
        data = crd_utils.read_crd('foos', 'foo')
        self.assertEqual(data, {'a': 1})

        # read not found
        api.get_namespaced_custom_object.side_effect = DummyApiException(status=404)
        self.assertIsNone(crd_utils.read_crd('foos', 'bar'))
        api.get_namespaced_custom_object.side_effect = None

        # update existing
        crd_utils.update_crd('foos', 'foo', {'a': 2})
        api.replace_namespaced_custom_object.assert_called_with(
            crd_utils.CRD_GROUP,
            crd_utils.CRD_VERSION,
            crd_utils.CRD_NAMESPACE,
            'foos',
            'foo',
            body | {'data': {'a': 2}},
        )

        # update when not found
        api.replace_namespaced_custom_object.side_effect = DummyApiException(status=404)
        crd_utils.update_crd('foos', 'foo', {'a': 3})
        api.create_namespaced_custom_object.assert_called_with(
            crd_utils.CRD_GROUP,
            crd_utils.CRD_VERSION,
            crd_utils.CRD_NAMESPACE,
            'foos',
            body | {'data': {'a': 3}},
        )
        api.replace_namespaced_custom_object.side_effect = None

        # delete
        crd_utils.delete_crd('foos', 'foo')
        api.delete_namespaced_custom_object.assert_called_with(
            crd_utils.CRD_GROUP,
            crd_utils.CRD_VERSION,
            crd_utils.CRD_NAMESPACE,
            'foos',
            'foo',
            api.delete_namespaced_custom_object.call_args[0][5],
        )

if __name__ == '__main__':
    unittest.main()

