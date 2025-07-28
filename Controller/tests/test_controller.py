from pathlib import Path
from unittest.mock import MagicMock
import sys
import types
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

# Provide dummy modules required by controller without installing heavy deps
for name in [
    "fastapi",
    "pydantic",
    "kubernetes",
    "kubernetes.client",
    "kubernetes.config",
    "kubernetes.client.rest",
    "starlette.responses",
    "yaml",
    "requests",
]:
    if name not in sys.modules:
        module = types.ModuleType(name)
        sys.modules[name] = module

# Minimal attributes used by controller
sys.modules["fastapi"].Request = object

class _HTTPException(Exception):
    pass

sys.modules["fastapi"].HTTPException = _HTTPException
sys.modules["pydantic"].BaseModel = object
sys.modules["starlette.responses"].JSONResponse = object
sys.modules["kubernetes.client.rest"].ApiException = Exception


class _DummyFastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def middleware(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def post(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator


sys.modules["fastapi"].FastAPI = _DummyFastAPI

import controller as ctrl  # noqa: E402


@pytest.fixture(autouse=True)
def restore_globals(monkeypatch):
    # Save originals
    orig_load_service_data = ctrl.load_service_data
    orig_save_service_data = ctrl.save_service_data
    orig_load_subscription_data = ctrl.load_subscription_data
    orig_save_subscription_data = ctrl.save_subscription_data
    orig_deploy_service = ctrl.deploy_service
    orig_communicate_with_agent = ctrl.communicate_with_agent
    orig_optimize = ctrl.optimize
    yield
    # Restore
    monkeypatch.setattr(ctrl, "load_service_data", orig_load_service_data, raising=False)
    monkeypatch.setattr(ctrl, "save_service_data", orig_save_service_data, raising=False)
    monkeypatch.setattr(ctrl, "load_subscription_data", orig_load_subscription_data, raising=False)
    monkeypatch.setattr(ctrl, "save_subscription_data", orig_save_subscription_data, raising=False)
    monkeypatch.setattr(ctrl, "deploy_service", orig_deploy_service, raising=False)
    monkeypatch.setattr(ctrl, "communicate_with_agent", orig_communicate_with_agent, raising=False)
    monkeypatch.setattr(ctrl, "optimize", orig_optimize, raising=False)


def test_compute_frequency_no_autoscale(monkeypatch):
    service_list = [
        {
            "podIP": "10.0.0.1",
            "hostPort": 1,
            "serviceType": "pose",
            "currentConnection": 0,
            "nodeName": "node1",
            "hostIP": "10.0.0.1",
            "frequencyLimit": [5, 3],
            "currentFrequency": 5,
            "workloadLimit": 10,
        }
    ]

    def fake_load_service_data():
        return service_list

    def fake_optimize(serviceType, agentCounter, services):
        return "success", services

    monkeypatch.setattr(ctrl, "load_service_data", fake_load_service_data)
    monkeypatch.setattr(ctrl, "optimize", fake_optimize)
    monkeypatch.setattr(ctrl, "deploy_service", MagicMock())

    result = ctrl.compute_frequnecy("pose", 1)
    assert result == service_list
    ctrl.deploy_service.assert_not_called()


def test_adjust_frequency(monkeypatch):
    service_list = [
        {
            "podIP": "10.0.0.1",
            "hostPort": 1,
            "serviceType": "pose",
            "currentConnection": 1,
            "nodeName": "node1",
            "hostIP": "10.0.0.1",
            "frequencyLimit": [5, 3],
            "currentFrequency": 5,
            "workloadLimit": 10,
        },
        {
            "podIP": "10.0.0.2",
            "hostPort": 2,
            "serviceType": "pose",
            "currentConnection": 0,
            "nodeName": "node2",
            "hostIP": "10.0.0.2",
            "frequencyLimit": [5, 3],
            "currentFrequency": 5,
            "workloadLimit": 10,
        },
    ]

    subscription_list = [
        {
            "agentIP": "192.168.0.1",
            "agentPort": 1234,
            "podIP": "10.0.0.1",
            "serviceType": "pose",
            "nodeName": "node1",
        }
    ]

    monkeypatch.setattr(ctrl, "load_service_data", lambda: service_list)
    monkeypatch.setattr(ctrl, "load_subscription_data", lambda: subscription_list)
    saved_subscriptions = []
    monkeypatch.setattr(ctrl, "save_subscription_data", lambda data: saved_subscriptions.append(data))
    communicate_calls = []

    def fake_communicate(data, ip, port):
        communicate_calls.append((data, ip, port))
        return 200, "ok"

    monkeypatch.setattr(ctrl, "communicate_with_agent", fake_communicate)

    result = ctrl.adjust_frequency("pose")

    assert result is None
    assert saved_subscriptions[0] == subscription_list
    assert communicate_calls[0][0]["ip"] == "null"
    assert communicate_calls[0][0]["port"] == 0
