#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed operator for the 5G AUSF service."""

import logging
from ipaddress import IPv4Address
from subprocess import check_output
from typing import Optional, Union

from charms.nrf_operator.v0.nrf import NRFAvailableEvent, NRFRequires
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from jinja2 import Environment, FileSystemLoader
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/ausf"
CONFIG_FILE_NAME = "ausfcfg.conf"


class AUSFOperatorCharm(CharmBase):
    """Main class to describe juju event handling for the 5G AUSF operator."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "ausf"
        self._container = self.unit.get_container(self._container_name)
        self._nrf_requires = NRFRequires(charm=self, relationship_name="nrf")
        self.framework.observe(self.on.ausf_pebble_ready, self._on_ausf_pebble_ready)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._on_ausf_pebble_ready)
        self.framework.observe(self.on.nrf_relation_joined, self._on_ausf_pebble_ready)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="sbi", port=29509),
            ],
        )

    def _write_config_file(self, nrf_url: str) -> None:
        jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
        template = jinja2_environment.get_template("ausfcfg.conf.j2")
        content = template.render(
            nrf_url=nrf_url,
            ausf_url=self._ausf_hostname,
        )
        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info(f"Pushed {CONFIG_FILE_NAME} config file")

    @property
    def _nrf_data_is_available(self) -> bool:
        """Returns whether the NRF data is available.

        Returns:
            bool: Whether the NRF data is available.
        """
        if not self._nrf_requires.get_nrf_url():
            return False
        return True

    @property
    def _config_file_is_written(self) -> bool:
        if not self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"):
            logger.info(f"Config file is not written: {CONFIG_FILE_NAME}")
            return False
        logger.info("Config file is written")
        return True

    def _on_ausf_pebble_ready(self, event: Union[PebbleReadyEvent, NRFAvailableEvent]) -> None:
        if not self._nrf_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for NRF relation to be created")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._nrf_data_is_available:
            self.unit.status = WaitingStatus("Waiting for NRF data to be available")
            return
        if not self._config_file_is_written:
            self._write_config_file(
                nrf_url=self._nrf_requires.get_nrf_url(),
            )
        self._container.add_layer("ausf", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

    @property
    def _nrf_relation_is_created(self) -> bool:
        return self._relation_created("nrf")

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            str: Whether the relation was created.
        """
        if not self.model.get_relation(relation_name):
            return False
        return True

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": "ausf layer",
                "description": "pebble config layer for ausf",
                "services": {
                    "ausf": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": f"/free5gc/ausf/ausf --ausfcfg {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}",
                        "environment": self._environment_variables,
                    },
                },
            }
        )

    @property
    def _environment_variables(self) -> dict:
        return {
            "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
            "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
            "GRPC_TRACE": "all",
            "GRPC_VERBOSITY": "debug",
            "POD_IP": str(self._pod_ip),
            "MANAGED_BY_CONFIG_POD": "true",
        }

    @property
    def _pod_ip(self) -> Optional[IPv4Address]:
        """Get the IP address of the Kubernetes pod."""
        return IPv4Address(check_output(["unit-get", "private-address"]).decode().strip())

    @property
    def _ausf_hostname(self) -> str:
        return f"{self.model.app.name}.{self.model.name}.svc.cluster.local"


if __name__ == "__main__":
    main(AUSFOperatorCharm)
