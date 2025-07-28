import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Provide a minimal kubernetes module when the real package is not available
if 'kubernetes' not in sys.modules:
    kubernetes = types.ModuleType('kubernetes')
    kubernetes.client = types.ModuleType('client')
    kubernetes.config = types.ModuleType('config')
    kubernetes.client.rest = types.ModuleType('rest')
    kubernetes.client.rest.ApiException = Exception
    class CustomObjectsApi:
        pass
    kubernetes.client.CustomObjectsApi = CustomObjectsApi
    sys.modules['kubernetes'] = kubernetes
    sys.modules['kubernetes.client'] = kubernetes.client
    sys.modules['kubernetes.config'] = kubernetes.config
    sys.modules['kubernetes.client.rest'] = kubernetes.client.rest

import crd_crud

CRD_GROUP = crd_crud.CRD_GROUP
CRD_VERSION = crd_crud.CRD_VERSION
CRD_NAMESPACE = crd_crud.CRD_NAMESPACE


class CrudTestCase(unittest.TestCase):
    def setUp(self):
        self.api_mock = MagicMock()
        patcher = patch('crd_crud._get_api', return_value=self.api_mock)
        self.get_api = patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_crd(self):
        data = {'foo': 'bar'}
        crd_crud.create_crd('services', 'test', data)
        expected_body = {
            'apiVersion': f'{CRD_GROUP}/{CRD_VERSION}',
            'kind': 'Data',
            'metadata': {'name': 'test'},
            'data': data,
        }
        self.api_mock.create_namespaced_custom_object.assert_called_once_with(
            CRD_GROUP,
            CRD_VERSION,
            CRD_NAMESPACE,
            'services',
            expected_body,
        )

    def test_read_crd(self):
        self.api_mock.get_namespaced_custom_object.return_value = {'data': {'k': 'v'}}
        result = crd_crud.read_crd('services', 'test')
        self.api_mock.get_namespaced_custom_object.assert_called_once_with(
            CRD_GROUP,
            CRD_VERSION,
            CRD_NAMESPACE,
            'services',
            'test',
        )
        self.assertEqual(result, {'k': 'v'})

    def test_update_crd(self):
        data = {'k': 'v'}
        crd_crud.update_crd('services', 'test', data)
        expected_body = {
            'apiVersion': f'{CRD_GROUP}/{CRD_VERSION}',
            'kind': 'Data',
            'metadata': {'name': 'test'},
            'data': data,
        }
        self.api_mock.replace_namespaced_custom_object.assert_called_once_with(
            CRD_GROUP,
            CRD_VERSION,
            CRD_NAMESPACE,
            'services',
            'test',
            expected_body,
        )

    def test_delete_crd(self):
        crd_crud.delete_crd('services', 'test')
        self.api_mock.delete_namespaced_custom_object.assert_called_once_with(
            CRD_GROUP,
            CRD_VERSION,
            CRD_NAMESPACE,
            'services',
            'test',
        )


if __name__ == '__main__':
    unittest.main()
