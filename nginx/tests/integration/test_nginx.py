# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests using a real Juju and charm to test ContainerPath."""

from __future__ import annotations

import jubilant
import pytest

from conftest import deploy


@pytest.mark.setup
def test_deployment(juju: jubilant.Juju, charm: str):
    deploy(juju, charm)
    assert charm in juju.status().apps
    juju.wait(lambda status: jubilant.all_active(status, charm))


def test_nginx_service_running(juju: jubilant.Juju, charm: str):
    services = juju.ssh(charm+"/0", "pebble services", container="nginx")
    assert services.splitlines()[1].split()[:3] == ["nginx", "enabled", "active"]


def test_nginx_pexp_service_running(juju: jubilant.Juju, charm: str):
    services = juju.ssh(charm+"/0", "pebble services", container="nginx-pexp")
    assert services.splitlines()[1].split()[:3] == ["nginx-prometheus-exporter", "enabled", "active"]

