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

from netmiko import ConnectHandler, FileTransfer, InLineTransfer
from netmiko import __version__ as netmiko_version
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
        self.device = ConnectHandler(device_type='cisco_xr',
                                     host=self.hostname,
                                     username=self.username,
                                     password=self.password,
                                     **self.netmiko_optional_args)

    def close(self):
        """Close the connection to the device."""
        self.device.disconnect()

    def _send_command(self, command):
        """Wrapper for self.device.send.command()."""
        try:
            return self.device.send_command(command)
        except (socket.error, EOFError) as e:
            raise ConnectionClosedException(str(e))

    def is_alive(self):
        """Returns a flag with the state of the SSH connection."""
        null = chr(0)
        try:
            if self.device is None:
                return {'is_alive': False}
            else:
                # Try sending ASCII null byte to maintain the connection alive
                self.device.send_command(null)
        except (socket.error, EOFError):
            # If unable to send, we can tell for sure that the connection is unusable,
            # hence return False.
            return {'is_alive': False}
        return {'is_alive': self.device.remote_conn.transport.is_active()}

    @staticmethod
    def _create_tmp_file(config):
        """Write temp file and for use with inline config and SCP."""
        tmp_dir = tempfile.gettempdir()
        rand_fname = py23_compat.text_type(uuid.uuid4())
        filename = os.path.join(tmp_dir, rand_fname)
        with open(filename, 'wt') as fobj:
            fobj.write(config)
        return filename

    def _load_candidate_wrapper(self, source_file=None, source_config=None, dest_file=None,
                                file_system=None):
        """
        Transfer file to remote device for either merge or replace operations

        Returns (return_status, msg)
        """
        return_status = False
        msg = ''
        if source_file and source_config:
            raise ValueError("Cannot simultaneously set source_file and source_config")

        if source_config:
            if self.inline_transfer:
                (return_status, msg) = self._inline_tcl_xfer(source_config=source_config,
                                                             dest_file=dest_file,
                                                             file_system=file_system)
            else:
                # Use SCP
                tmp_file = self._create_tmp_file(source_config)
                (return_status, msg) = self._scp_file(source_file=tmp_file, dest_file=dest_file,
                                                      file_system=file_system)
                if tmp_file and os.path.isfile(tmp_file):
                    os.remove(tmp_file)
        if source_file:
            if self.inline_transfer:
                (return_status, msg) = self._inline_tcl_xfer(source_file=source_file,
                                                             dest_file=dest_file,
                                                             file_system=file_system)
            else:
                (return_status, msg) = self._scp_file(source_file=source_file, dest_file=dest_file,
                                                      file_system=file_system)
        if not return_status:
            if msg == '':
                msg = "Transfer to remote device failed"
        return (return_status, msg)

    def load_replace_candidate(self, filename=None, config=None):
        """
        SCP file to device filesystem, defaults to candidate_config.

        Return None or raise exception
        """
        self.config_replace = True
        return_status, msg = self._load_candidate_wrapper(source_file=filename,
                                                          source_config=config,
                                                          dest_file=self.candidate_cfg,
                                                          file_system=self.dest_file_system)
        if not return_status:
            raise ReplaceConfigException(msg)

    def load_merge_candidate(self, filename=None, config=None):
        """
        SCP file to remote device.

        Merge configuration in: copy <file> running-config
        """
        self.config_replace = False
        return_status, msg = self._load_candidate_wrapper(source_file=filename,
                                                          source_config=config,
                                                          dest_file=self.merge_cfg,
                                                          file_system=self.dest_file_system)
        if not return_status:
            raise MergeConfigException(msg)

    @staticmethod
    def _normalize_compare_config(diff):
        """Filter out strings that should not show up in the diff."""
        ignore_strings = ['Contextual Config Diffs', 'No changes were found',
                          'file prompt quiet', 'ntp clock-period']

        new_list = []
        for line in diff.splitlines():
            for ignore in ignore_strings:
                if ignore in line:
                    break
            else:  # nobreak
                new_list.append(line)
        return "\n".join(new_list)

    @staticmethod
    def _normalize_merge_diff_incr(diff):
        """Make the compare config output look better.

        Cisco IOS incremental-diff output

        No changes:
        !List of Commands:
        end
        !No changes were found
        """
        new_diff = []

        changes_found = False
        for line in diff.splitlines():
            if re.search(r'order-dependent line.*re-ordered', line):
                changes_found = True
            elif 'No changes were found' in line:
                # IOS in the re-order case still claims "No changes were found"
                if not changes_found:
                    return ''
                else:
                    continue

            if line.strip() == 'end':
                continue
            elif 'List of Commands' in line:
                continue
            # Filter blank lines and prepend +sign
            elif line.strip():
                if re.search(r"^no\s+", line.strip()):
                    new_diff.append('-' + line)
                else:
                    new_diff.append('+' + line)
        return "\n".join(new_diff)

    @staticmethod
    def _normalize_merge_diff(diff):
        """Make compare_config() for merge look similar to replace config diff."""
        new_diff = []
        for line in diff.splitlines():
            # Filter blank lines and prepend +sign
            if line.strip():
                new_diff.append('+' + line)
        if new_diff:
            new_diff.insert(0, '! incremental-diff failed; falling back to echo of merge file')
        else:
            new_diff.append('! No changes specified in merge file.')
        return "\n".join(new_diff)

    def compare_config(self):
        """
        show archive config differences <base_file> <new_file>.

        Default operation is to compare system:running-config to self.candidate_cfg
        """
        # Set defaults
        base_file = 'running-config'
        base_file_system = 'system:'
        if self.config_replace:
            new_file = self.candidate_cfg
        else:
            new_file = self.merge_cfg
        new_file_system = self.dest_file_system

        base_file_full = self._gen_full_path(filename=base_file, file_system=base_file_system)
        new_file_full = self._gen_full_path(filename=new_file, file_system=new_file_system)

        if self.config_replace:
            cmd = 'show archive config differences {} {}'.format(base_file_full, new_file_full)
            diff = self.device.send_command_expect(cmd)
            diff = self._normalize_compare_config(diff)
        else:
            # merge
            cmd = 'show archive config incremental-diffs {} ignorecase'.format(new_file_full)
            diff = self.device.send_command_expect(cmd)
            if '% Invalid' not in diff:
                diff = self._normalize_merge_diff_incr(diff)
            else:
                cmd = 'more {}'.format(new_file_full)
                diff = self.device.send_command_expect(cmd)
                diff = self._normalize_merge_diff(diff)

        return diff.strip()

    def _commit_hostname_handler(self, cmd):
        """Special handler for hostname change on commit operation."""
        try:
            current_prompt = self.device.find_prompt()
            # Wait 12 seconds for output to come back (.2 * 60)
            output = self.device.send_command_expect(cmd, delay_factor=.2, max_loops=60)
        except IOError:
            # Check if hostname change
            if current_prompt == self.device.find_prompt():
                raise
            else:
                self.device.set_base_prompt()
                output = ''
        return output

    def commit_config(self):
        """
        If replacement operation, perform 'configure replace' for the entire config.

        If merge operation, perform copy <file> running-config.
        """
        # Always generate a rollback config on commit
        self._gen_rollback_cfg()

        if self.config_replace:
            # Replace operation
            filename = self.candidate_cfg
            cfg_file = self._gen_full_path(filename)
            if not self._check_file_exists(cfg_file):
                raise ReplaceConfigException("Candidate config file does not exist")
            if self.auto_rollback_on_error:
                cmd = 'configure replace {} force revert trigger error'.format(cfg_file)
            else:
                cmd = 'configure replace {} force'.format(cfg_file)
            output = self._commit_hostname_handler(cmd)
            if ('Failed to apply command' in output) or \
               ('original configuration has been successfully restored' in output) or \
               ('Error' in output):
                msg = "Candidate config could not be applied\n{}".format(output)
                raise ReplaceConfigException(msg)
            elif '%Please turn config archive on' in output:
                msg = "napalm-ios replace() requires Cisco 'archive' feature to be enabled."
                raise ReplaceConfigException(msg)
        else:
            # Merge operation
            filename = self.merge_cfg
            cfg_file = self._gen_full_path(filename)
            if not self._check_file_exists(cfg_file):
                raise MergeConfigException("Merge source config file does not exist")
            cmd = 'copy {} running-config'.format(cfg_file)
            self._disable_confirm()
            output = self._commit_hostname_handler(cmd)
            self._enable_confirm()
            if 'Invalid input detected' in output:
                self.rollback()
                err_header = "Configuration merge failed; automatic rollback attempted"
                merge_error = "{0}:\n{1}".format(err_header, output)
                raise MergeConfigException(merge_error)

        # Save config to startup (both replace and merge)
        output += self.device.send_command_expect("write mem")

    def discard_config(self):
        """Set candidate_cfg to current running-config. Erase the merge_cfg file."""
        discard_candidate = 'copy running-config {}'.format(self._gen_full_path(self.candidate_cfg))
        discard_merge = 'copy null: {}'.format(self._gen_full_path(self.merge_cfg))
        self._disable_confirm()
        self.device.send_command_expect(discard_candidate)
        self.device.send_command_expect(discard_merge)
        self._enable_confirm()

    def rollback(self):
        """Rollback configuration to filename or to self.rollback_cfg file."""
        filename = self.rollback_cfg
        cfg_file = self._gen_full_path(filename)
        if not self._check_file_exists(cfg_file):
            raise ReplaceConfigException("Rollback config file does not exist")
        cmd = 'configure replace {} force'.format(cfg_file)
        self.device.send_command_expect(cmd)

        # Save config to startup
        self.device.send_command_expect("write mem")

    def _inline_tcl_xfer(self, source_file=None, source_config=None, dest_file=None,
                         file_system=None):
        """
        Use Netmiko InlineFileTransfer (TCL) to transfer file or config to remote device.

        Return (status, msg)
        status = boolean
        msg = details on what happened
        """
        if source_file:
            return self._xfer_file(source_file=source_file, dest_file=dest_file,
                                   file_system=file_system, TransferClass=InLineTransfer)
        if source_config:
            return self._xfer_file(source_config=source_config, dest_file=dest_file,
                                   file_system=file_system, TransferClass=InLineTransfer)
        raise ValueError("File source not specified for transfer.")

    def _scp_file(self, source_file, dest_file, file_system):
        """
        SCP file to remote device.

        Return (status, msg)
        status = boolean
        msg = details on what happened
        """
        return self._xfer_file(source_file=source_file, dest_file=dest_file,
                               file_system=file_system, TransferClass=FileTransfer)

    def _xfer_file(self, source_file=None, source_config=None, dest_file=None, file_system=None,
                   TransferClass=FileTransfer):
        """Transfer file to remote device.

        By default, this will use Secure Copy if self.inline_transfer is set, then will use
        Netmiko InlineTransfer method to transfer inline using either SSH or telnet (plus TCL
        onbox).

        Return (status, msg)
        status = boolean
        msg = details on what happened
        """
        if not source_file and not source_config:
            raise ValueError("File source not specified for transfer.")
        if not dest_file or not file_system:
            raise ValueError("Destination file or file system not specified.")

        if source_file:
            kwargs = dict(ssh_conn=self.device, source_file=source_file, dest_file=dest_file,
                          direction='put', file_system=file_system)
        elif source_config:
            kwargs = dict(ssh_conn=self.device, source_config=source_config, dest_file=dest_file,
                          direction='put', file_system=file_system)
        enable_scp = True
        if self.inline_transfer:
            enable_scp = False
        with TransferClass(**kwargs) as transfer:

            # Check if file already exists and has correct MD5
            if transfer.check_file_exists() and transfer.compare_md5():
                msg = "File already exists and has correct MD5: no SCP needed"
                return (True, msg)
            if not transfer.verify_space_available():
                msg = "Insufficient space available on remote device"
                return (False, msg)

            if enable_scp:
                transfer.enable_scp()

            # Transfer file
            transfer.transfer_file()

            # Compares MD5 between local-remote files
            if transfer.verify_file():
                msg = "File successfully transferred to remote device"
                return (True, msg)
            else:
                msg = "File transfer to remote device failed"
                return (False, msg)
            return (False, '')

    def _enable_confirm(self):
        """Enable IOS confirmations on file operations (global config command)."""
        cmd = 'no file prompt quiet'
        self.device.send_config_set([cmd])

    def _disable_confirm(self):
        """Disable IOS confirmations on file operations (global config command)."""
        cmd = 'file prompt quiet'
        self.device.send_config_set([cmd])

    def _gen_full_path(self, filename, file_system=None):
        """Generate full file path on remote device."""
        if file_system is None:
            return '{}/{}'.format(self.dest_file_system, filename)
        else:
            if ":" not in file_system:
                raise ValueError("Invalid file_system specified: {}".format(file_system))
            return '{}/{}'.format(file_system, filename)

    def _gen_rollback_cfg(self):
        """Save a configuration that can be used for rollback."""
        cfg_file = self._gen_full_path(self.rollback_cfg)
        cmd = 'copy running-config {}'.format(cfg_file)
        self._disable_confirm()
        self.device.send_command_expect(cmd)
        self._enable_confirm()

    def _check_file_exists(self, cfg_file):
        """
        Check that the file exists on remote device using full path.

        cfg_file is full path i.e. flash:/file_name

        For example
        # dir flash:/candidate_config.txt
        Directory of flash:/candidate_config.txt

        33  -rw-        5592  Dec 18 2015 10:50:22 -08:00  candidate_config.txt

        return boolean
        """
        cmd = 'dir {}'.format(cfg_file)
        success_pattern = 'Directory of {}'.format(cfg_file)
        output = self.device.send_command_expect(cmd)
        if 'Error opening' in output:
            return False
        elif success_pattern in output:
            return True
        return False
