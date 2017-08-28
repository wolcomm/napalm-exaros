"""Test fixtures."""

from builtins import super

from napalm_base.test import conftest as parent_conftest
from napalm_base.test.double import BaseTestDouble
from napalm_base.utils import py23_compat

from napalm_exaros import exaros
from napalm_exaros.ssh import ExaROSSSH

import pytest


@pytest.fixture(scope='class')
def set_device_parameters(request):
    """Set up the class."""
    def fin():
        request.cls.device.close()
    request.addfinalizer(fin)

    request.cls.driver = exaros.ExaROSDriver
    request.cls.patched_driver = PatchedExaROSDriver
    request.cls.vendor = 'exaros'
    parent_conftest.set_device_parameters(request)


def pytest_generate_tests(metafunc):
    """Generate test cases dynamically."""
    parent_conftest.pytest_generate_tests(metafunc, __file__)


class PatchedExaROSDriver(exaros.ExaROSDriver):
    """Patched ExaROS Driver."""

    def __init__(self, hostname, username, password,
                 timeout=60, optional_args=None):
        """Patched ExaROS Driver constructor."""
        super().__init__(hostname, username, password, timeout, optional_args)

        self.patched_attrs = ['connection']
        self.connection = FakeExaROSDevice()

    def open(self):
        """Open a connection to the device."""
        pass

    def close(self):
        """Close the connection to the device."""
        pass

    def is_alive(self):
        """Return a flag with the state of the SSH connection."""
        return {'is_alive': True}


class FakeExaROSDevice(BaseTestDouble, ExaROSSSH):
    """ExaROS device test double."""

    def select_delay_factor(self, delay_factor):
        """Set dummy delay_factor."""
        return 1

    def config_mode(self):
        """Enter into configuration mode."""
        pass

    def send_command(self, command, **kwargs):
        """Fake send_command."""
        filename = '{}.txt'.format(self.sanitize_text(command))
        full_path = self.find_file(filename)
        result = self.read_txt_file(full_path)
        return py23_compat.text_type(result)
