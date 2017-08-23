# Copyright 2017 Workonline Communications (Pty) Ltd. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""Napalm driver module for ExaROS."""

from __future__ import print_function
from __future__ import unicode_literals

from napalm_base.base import NetworkDriver
from napalm_base.exceptions import (
    CommandErrorException,
    ConnectionException,
    MergeConfigException,
    ReplaceConfigException,
    SessionLockedException,
    )


class ExaROSDriver(NetworkDriver):
    """Napalm driver for ExaROS."""

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
        """Constructor."""
        self.device = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout

        if optional_args is None:
            optional_args = {}

    def open(self):
        """Open a connection to the device."""
        pass

    def close(self):
        """Close the connection to the device."""
        pass
