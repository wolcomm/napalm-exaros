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
"""SSH handler module for ExaROS."""

from __future__ import print_function
from __future__ import unicode_literals

import re

from netmiko import BaseConnection, SCPConn


class ExaROSSSH(BaseConnection):
    """Class for ExaROS SSH connection handling."""

    def session_preparation(self):
        """Prepare the session after the connection has been established."""
        self._test_channel_read()
        self.set_base_prompt()
        self.disable_paging(command="session paginate disable")
        self.set_terminal_width(command='terminal width 511')

    def check_enable_mode(self, check_string='#'):
        """Check if in enable mode. Return boolean."""
        return True

    def enable(self, cmd='enable', pattern='password', re_flags=re.IGNORECASE):
        """Enter enable mode."""
        return ""

    def exit_enable_mode(self, exit_command='disable'):
        """Exit enable mode."""
        return ""

    def check_config_mode(self, check_string=')#', pattern=''):
        """Check if the device is in configuration mode. Return boolean."""
        if not pattern:
            pattern = re.escape(self.base_prompt[:16])
        return super(ExaROSSSH, self).check_config_mode(
            check_string=check_string, pattern=pattern)

    def config_mode(self, config_command='configure private', pattern=''):
        """Enter into configuration mode on remote device."""
        if not pattern:
            pattern = re.escape(self.base_prompt[:16])
        return super(ExaROSSSH, self).config_mode(
            config_command=config_command, pattern=pattern)

    def exit_config_mode(self, exit_config='abort', pattern=''):
        """Exit configuration mode."""
        if not pattern:
            pattern = re.escape(self.base_prompt[:16])
        return super(ExaROSSSH, self).exit_config_mode(exit_config=exit_config,
                                                       pattern=pattern)

    def send_config_set(self, config_commands=None, exit_config_mode=False,
                        **kwargs):
        """Send configuration commands down the SSH channel."""
        return super(ExaROSSSH, self).send_config_set(
            config_commands=config_commands, exit_config_mode=exit_config_mode,
            **kwargs)

    def get_config(self, store=None, delay_factor=1):
        """Get configuration store."""
        delay_factor = self.select_delay_factor(delay_factor)
        stores = {
            "running": "show configuration running all",
            "candidate": "show candidate all"
        }
        if store not in stores:
            raise ValueError("store should be one of {0}".format(
                stores.iterkeys()))
        self.config_mode()
        output = self.send_command(stores[store])
        return output

    def load(self, operation=None, file=None, delay_factor=1):
        """Load the candidate configuration from a file."""
        delay_factor = self.select_delay_factor(delay_factor)
        # check args
        if operation not in ("replace", "merge"):
            raise ValueError("Invalid operation type: {0}".format(operation))
        if not file:
            raise ValueError("No filename provided")
        # load configuration
        load_command = "load {0} {1}".format(operation, file)
        load_success = 'Operation completed successfully'
        self.config_mode()
        output = self.send_command(load_command, strip_prompt=False,
                                   strip_command=False,
                                   delay_factor=delay_factor)
        if load_success not in output:
            raise Exception("Load failed:\n\n{0}".format(output))
        return output

    def compare(self, delay_factor=1):
        """Compare the candidate and running configurations."""
        delay_factor = self.select_delay_factor(delay_factor)
        compare_command = "show candidate diff all"
        no_changes = '% No configuration changes found.'
        self.config_mode()
        output = self.send_command(compare_command, delay_factor=delay_factor)
        if no_changes in output:
            return ""
        return output

    def commit(self, comment=None, label=None, delay_factor=1):
        """Commit the candidate configuration."""
        delay_factor = self.select_delay_factor(delay_factor)
        # wrap the comment and label in quotes
        if comment:
            if '"' in comment:
                raise ValueError("Invalid comment contains double quote")
            comment = '"{0}"'.format(comment)
        if label:
            if '"' in label:
                raise ValueError("Invalid label contains double quote")
            label = '"{0}"'.format(label)

        # Select proper command string based on arguments provided
        commit_command = 'commit'
        if comment:
            commit_command += ' comment {0}'.format(comment)
        if label:
            commit_command += ' label {0}'.format(label)

        # Enter config mode (if necessary)
        output = self.config_mode()

        # Validate the pending changes
        check_command = 'commit check'
        is_valid = 'Validation complete'
        output = self.send_command(check_command, strip_prompt=False,
                                   strip_command=False,
                                   delay_factor=delay_factor)
        if is_valid not in output:
            raise ValueError("Commit check failed:\n\n{0}".format(output))

        # Commit changes
        no_changes = '% No modifications to commit.'
        commit_complete = 'Commit complete.'
        output = self.send_command(commit_command, strip_prompt=False,
                                   strip_command=False,
                                   delay_factor=delay_factor)
        if commit_complete not in output:
            if no_changes not in output:
                raise ValueError("Commit failed:\n\n{0}".format(output))

        return output

    def scp_put_file(self, source_file=None, dest_file=None):
        """Put file using SCP."""
        try:
            scp = SCPConn(ssh_conn=self)
            scp.scp_put_file(source_file=source_file, dest_file=dest_file)
        except Exception:
            raise
        finally:
            scp.close()

    def cleanup(self):
        """Gracefully exit the SSH session."""
        self.exit_config_mode()

    def telnet_login(self, **kwargs):
        """Telnet login is not supported."""
        raise NotImplementedError
