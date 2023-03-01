# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops import testing
from ops.model import ActiveStatus

from charm import AUSFOperatorCharm


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(AUSFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _nrf_is_available(self) -> str:
        nrf_url = "http://1.1.1.1"
        nrf_relation_id = self.harness.add_relation("nrf", "nrf-operator")
        self.harness.add_relation_unit(
            relation_id=nrf_relation_id, remote_unit_name="nrf-operator/0"
        )
        self.harness.update_relation_data(
            relation_id=nrf_relation_id, app_or_unit="nrf-operator", key_values={"url": nrf_url}
        )
        return nrf_url

    @patch("charm.check_output")
    @patch("ops.model.Container.push")
    def test_given_nrf_is_available_when_databases_are_created_then_config_file_is_written(
        self,
        patch_push,
        patch_check_output,
    ):
        patch_check_output.return_value = b"1.2.3.4"
        self.harness.set_can_connect(container="ausf", val=True)

        nrf_url = self._nrf_is_available()

        patch_push.assert_called_with(
            path="/etc/ausf/ausfcfg.conf",
            source=f'configuration:\n  groupId: ausfGroup001\n  nrfUri: { nrf_url }\n  plmnSupportList:\n  - mcc: "208"\n    mnc: "93"\n  sbi:\n    bindingIPv4: 0.0.0.0\n    port: 29509\n    registerIPv4: ausf-operator.whatever.svc.cluster.local\n    scheme: http\n  serviceNameList:\n  - nausf-auth\ninfo:\n  description: AUSF initial local configuration\n  version: 1.0.0\nlogger:\n  AMF:\n    ReportCaller: false\n    debugLevel: info\n  AUSF:\n    ReportCaller: false\n    debugLevel: info\n  Aper:\n    ReportCaller: false\n    debugLevel: info\n  CommonConsumerTest:\n    ReportCaller: false\n    debugLevel: info\n  FSM:\n    ReportCaller: false\n    debugLevel: info\n  MongoDBLibrary:\n    ReportCaller: false\n    debugLevel: info\n  N3IWF:\n    ReportCaller: false\n    debugLevel: info\n  NAS:\n    ReportCaller: false\n    debugLevel: info\n  NGAP:\n    ReportCaller: false\n    debugLevel: info\n  NRF:\n    ReportCaller: false\n    debugLevel: info\n  NamfComm:\n    ReportCaller: false\n    debugLevel: info\n  NamfEventExposure:\n    ReportCaller: false\n    debugLevel: info\n  NsmfPDUSession:\n    ReportCaller: false\n    debugLevel: info\n  NudrDataRepository:\n    ReportCaller: false\n    debugLevel: info\n  OpenApi:\n    ReportCaller: false\n    debugLevel: info\n  PCF:\n    ReportCaller: false\n    debugLevel: info\n  PFCP:\n    ReportCaller: false\n    debugLevel: info\n  PathUtil:\n    ReportCaller: false\n    debugLevel: info\n  SMF:\n    ReportCaller: false\n    debugLevel: info\n  UDM:\n    ReportCaller: false\n    debugLevel: info\n  UDR:\n    ReportCaller: false\n    debugLevel: info\n  WEBUI:\n    ReportCaller: false\n    debugLevel: info',  # noqa: E501
        )

    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_all_relations_are_ready_when_pebble_ready_then_pebble_plan_is_applied(
        self,
        patch_exists,
        patch_check_output,
    ):
        pod_ip = "1.1.1.1"
        patch_exists.return_value = True
        patch_check_output.return_value = pod_ip.encode()

        self._nrf_is_available()

        self.harness.container_pebble_ready(container_name="ausf")

        expected_plan = {
            "services": {
                "ausf": {
                    "override": "replace",
                    "command": "/free5gc/ausf/ausf --ausfcfg /etc/ausf/ausfcfg.conf",
                    "startup": "enabled",
                    "environment": {
                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                        "GRPC_TRACE": "all",
                        "GRPC_VERBOSITY": "debug",
                        "POD_IP": pod_ip,
                        "MANAGED_BY_CONFIG_POD": "true",
                    },
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("ausf").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_all_relations_are_ready_when_pebble_ready_then_status_is_active(
        self, patch_exists, patch_check_output
    ):
        patch_exists.return_value = True
        patch_check_output.return_value = b"1.2.3.4"

        self._nrf_is_available()

        self.harness.container_pebble_ready("ausf")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
