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
import scp
import socket
import tempfile

from napalm_base.base import NetworkDriver
from napalm_base.exceptions import (
    # CommandErrorException,
    # ConnectionException,
    ConnectionClosedException,
    MergeConfigException,
    ReplaceConfigException,
    # SessionLockedException,
    )
from napalm_base.utils import py23_compat
from netmiko import ConnectHandler, SCPConn

MERGE_CONFIG = 'merge'
REPLACE_CONFIG = 'replace'


class ExaROSDriver(NetworkDriver):
    """Napalm driver for ExaROS."""

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
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
        self.connection = ConnectHandler(device_type='cisco_xr',
                                         host=self.hostname,
                                         username=self.username,
                                         password=self.password,
                                         **self.netmiko_optional_args)
        # disable output pagination
        self._send_command("session paginate disable")

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
            # If unable to send, we can tell for sure that the connection is unusable,
            # hence return False.
            return {'is_alive': False}
        return {'is_alive': self.connection.remote_conn.transport.is_active()}

    def load_replace_candidate(self, filename=None, config=None):
        """load replace candidate config file to device."""
        self.config_replace = True
        return_status, msg = self._load_candidate(source_file=filename,
                                                  source_config=config,
                                                  operation=REPLACE_CONFIG)
        if not return_status:
            raise ReplaceConfigException(msg)

    def load_merge_candidate(self, filename=None, config=None):
        """load merge candidate config file to device."""
        self.config_replace = False
        return_status, msg = self._load_candidate(source_file=filename,
                                                  source_config=config,
                                                  operation=MERGE_CONFIG)
        if not return_status:
            raise MergeConfigException(msg)

    def _load_candidate(self, source_file=None, source_config=None, operation=MERGE_CONFIG):
        """Load candidate config"""
        (return_status, msg) = self._put_candidate(source_file=source_file,
                                                   source_config=source_config)
        if return_status:
            try:
                self._send_command("configure private")
                self._send_command("load %s %s" % (operation, self.candidate))
            except Exception as e:
                return_status = False
                msg = e.message
        return (return_status, msg)

    def _put_candidate(self, source_file=None, source_config=None):
        """Transfer file to remote device for either merge or replace operations"""
        return_status = False
        msg = ''
        if source_file and source_config:
            raise ValueError("Cannot simultaneously set source_file and source_config")
        if source_config:
            tmp_file = self._create_tmp_file(source_config)
            (return_status, msg) = self._scp_put_file(source_file=tmp_file,
                                                      dest_file=self.candidate)
            if tmp_file and os.path.isfile(tmp_file):
                os.remove(tmp_file)
        if source_file:
            (return_status, msg) = self._scp_put_file(source_file=source_file,
                                                      dest_file=self.candidate)
        if not return_status:
            if msg == '':
                msg = "Transfer to remote device failed"
        return (return_status, msg)

    @staticmethod
    def _create_tmp_file(config):
        """Write temp file and for use with SCP."""
        tmp_dir = tempfile.gettempdir()
        rand_fname = py23_compat.text_type(uuid.uuid4())
        filename = os.path.join(tmp_dir, rand_fname)
        with open(filename, 'wt') as fobj:
            fobj.write(config)
        return filename

    def _scp_put_file(self, source_file, dest_file):
        """Put file using SCP"""
        return_status = False
        msg = ""
        try:
            scp = SCPConn(ssh_conn=self.connection)
            scp.scp_put_file(source_file=source_file, dest_file=dest_file)
            return_status = True
            msg = "SCP transfer successfully completed"
        except Exception as e:
            msg = e.message
        finally:
            scp.close()
        return (return_status, msg)
