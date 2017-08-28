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

import os
import socket
import tempfile
import uuid

from napalm_base.base import NetworkDriver
from napalm_base.exceptions import (
    # CommandErrorException,
    # ConnectionException,
    CommitError,
    ConnectionClosedException,
    MergeConfigException,
    ReplaceConfigException,
    # SessionLockedException,
    )
from napalm_base.utils import py23_compat

from napalm_exaros.ssh import ExaROSSSH

MERGE_CONFIG = 'merge'
REPLACE_CONFIG = 'replace'


class ExaROSDriver(NetworkDriver):
    """Napalm driver for ExaROS."""

    def __init__(self, hostname, username, password,
                 timeout=60, optional_args=None):
        """Constructor."""
        self.connection = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout

        if optional_args is None:
            optional_args = {}

        self.candidate = "candidate.conf"

        # Netmiko possible arguments
        netmiko_argument_map = {
            'port': None,
            'secret': '',
            'verbose': False,
            'keepalive': 30,
            'global_delay_factor': 1,
            'use_keys': False,
            'key_file': None,
            'ssh_strict': False,
            'system_host_keys': False,
            'alt_host_keys': False,
            'alt_key_file': '',
            'ssh_config_file': None,
            'allow_agent': False
        }

        # Build dict of any optional Netmiko args
        self.netmiko_optional_args = {}
        for k, v in netmiko_argument_map.items():
            try:
                self.netmiko_optional_args[k] = optional_args[k]
            except KeyError:
                pass
        self.global_delay_factor = optional_args.get('global_delay_factor', 1)
        self.port = optional_args.get('port', 22)

    def open(self):
        """Open a connection to the device."""
        self.connection = ExaROSSSH(host=self.hostname, username=self.username,
                                    password=self.password,
                                    **self.netmiko_optional_args)

    def close(self):
        """Close the connection to the device."""
        self.connection.disconnect()

    def _send_command(self, command):
        """Wrap self.device.send_command()."""
        try:
            return self.connection.send_command(command)
        except (socket.error, EOFError) as e:
            raise ConnectionClosedException(str(e))

    def is_alive(self):
        """Return a flag with the state of the SSH connection."""
        null = chr(0)
        try:
            if self.connection is None:
                return {'is_alive': False}
            else:
                # Try sending ASCII null byte to maintain the connection alive
                self.connection.send_command(null)
        except (socket.error, EOFError):
            # If unable to send, we can tell for sure that the connection
            # is unusable, hence return False.
            return {'is_alive': False}
        return {'is_alive': self.connection.remote_conn.transport.is_active()}

    def load_replace_candidate(self, filename=None, config=None):
        """Load replace candidate config file to device."""
        try:
            return self._load_candidate(source_file=filename,
                                        source_config=config,
                                        operation=REPLACE_CONFIG)
        except Exception as e:
            raise ReplaceConfigException(e)

    def load_merge_candidate(self, filename=None, config=None):
        """Load merge candidate config file to device."""
        try:
            return self._load_candidate(source_file=filename,
                                        source_config=config,
                                        operation=MERGE_CONFIG)
        except Exception as e:
            raise MergeConfigException(e)

    def _load_candidate(self, source_file=None, source_config=None,
                        operation=MERGE_CONFIG):
        """Load candidate config."""
        self._put_candidate(source_file=source_file,
                            source_config=source_config)
        self.connection.load(operation=operation, file=self.candidate)
        return True

    def _put_candidate(self, source_file=None, source_config=None):
        """Transfer file to remote device for merge or replace operations."""
        if source_file:
            self.connection.scp_put_file(source_file=source_file,
                                         dest_file=self.candidate)
            return True
        if source_config:
            tmp_file = self._create_tmp_file(source_config)
            self.connection.scp_put_file(source_file=tmp_file,
                                         dest_file=self.candidate)
            if tmp_file and os.path.isfile(tmp_file):
                os.remove(tmp_file)
            return True
        raise ValueError("Must provide either source_file or source_config")

    def discard_config(self):
        """Discard the configuration loaded into the candidate."""
        self.connection.exit_config_mode()

    def compare_config(self):
        """Compare the candidate and running configurations."""
        return self.connection.compare()

    def commit_config(self):
        """Commit the candidate configuration."""
        commit_label = "configured using napalm_exaros"
        try:
            return self.connection.commit(label=commit_label)
        except Exception as e:
            raise CommitError(e)

    @staticmethod
    def _create_tmp_file(config):
        """Write temp file and for use with SCP."""
        tmp_dir = tempfile.gettempdir()
        rand_fname = py23_compat.text_type(uuid.uuid4())
        filename = os.path.join(tmp_dir, rand_fname)
        with open(filename, 'wt') as fobj:
            fobj.write(config)
        return filename

    def get_config(self, retrieve="all"):
        """Get the device configuration."""
        stores = ["all", "running", "candidate", "startup"]
        if retrieve not in stores:
            raise ValueError("retrieve should be one of {0}".format(stores))
        output = {
            "running": "",
            "candidate": "",
            "startup": ""
        }
        if retrieve in ("all", "running"):
            output["running"] = self.connection.get_config(store="running")
        if retrieve in ("all", "candidate"):
            output["candidate"] = self.connection.get_config(store="candidate")
        return output
