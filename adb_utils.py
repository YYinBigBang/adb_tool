# Import modules for AdbManager
import re
import time
import shlex
from subprocess import STDOUT, PIPE, Popen, TimeoutExpired
# UsbViewer is a Python file for mapping slot to SN on Windows system.
import UsbViewer
# Import modules for logger
import sys
import logging


class AdbManager:
    """Manager class for creating and storing ADB command instances over USB."""
    def __init__(self, logger, timeout=30):
        self.sn = None
        self.logger = logger
        self.timeout = timeout
        self._shell = False
        self.retry_times = 3

    def cmd_start(self, command: str):
        """Creates a command subprocess."""
        start_time = time.time()
        self.logger.debug(f"ADB command: {command}")
        if not self._shell:
            command = shlex.split(command)
        proc = Popen(command, stdout=PIPE, stderr=STDOUT,
                     shell=self._shell, encoding="utf-8")
        return proc, start_time

    def cmd_stop(self, response: tuple):
        """Communicates with a previous command Popen object."""
        stdout = None
        proc, start_time = response
        try:
            stdout, _ = proc.communicate(timeout=self.timeout)
        except TimeoutExpired as err:
            proc.kill()
            stdout, _ = proc.communicate()
            stdout += str(err)
        finally:
            total = time.time() - start_time
            if proc.returncode == 0:
                self.logger.debug(f"ADB end: {total:.5f}(s), {stdout}")
            else:
                self.logger.error(f"ADB stop: {total:.5f}(s), err={proc.returncode}, {stdout}")
        return stdout.strip(), proc.returncode

    def popen(self, command: str):
        """Execute command by using subprocess popen."""
        response = self.cmd_start(command)
        return self.cmd_stop(response)

    def cmd_retry(self, command: str):
        """Retry ADB command if device lose connection."""
        for _ in range(self.retry_times):
            self.logger.warning(f'ADB retry: {command}')
            ret, returncode = self.popen(command)
            if returncode == 0:
                return ret
            time.sleep(1)
        self.logger.error(f'Retry command failed: {command}')
        return f'Retry command failed: {command}'

    def _adb(self, command: str):
        """Prepends ADB and SN to the command."""
        if self.sn:
            cmd = f'adb -s {self.sn} {command}'
        else:
            cmd = f'adb {command}'
        ret, returncode = self.popen(cmd)
        if returncode != 0 and re.search(f"device '{self.sn}' not found", ret):
            ret = self.cmd_retry(cmd)
        return ret

    def shell(self, command: str):
        """Prepends shell to the command if not present."""
        if command.startswith('shell '):
            return self._adb(command)
        return self._adb(f'shell {command}')

    def reboot(self):
        """Restart the device."""
        return self._adb('reboot')

    def boot_completed(self):
        """Checks that the device completed boot."""
        # adb wait-for-device shell "while [ 1 != $(getprop sys.boot_completed) ]; do sleep 1; done"
        return True if self.shell('getprop sys.boot_completed') == 1 else False

    def wait_for_device(self):
        """Wait for device to be ready.(Only one device)"""
        return self._adb('wait-for-device')

    def devices(self, usb_slot: str):
        """Get SN through ADB command on the Ubuntu system."""
        ret = self._adb('devices -l')
        for dut_info in ret.split('\n'):
            if usb_slot in dut_info:
                self.sn = re.search(r'[0-9A-Z]{14}', dut_info)
                break
        return self.sn

    def get_sn(self, usb_slot: str):
        """Get SN through UsbTreeView.exe on the Windows system."""
        file_path = 'slot_mapping/'
        usb_manager = UsbViewer(file_path, file_path)
        usb_manager.update_usb_port_list()
        self.sn = usb_manager.get_serial_num_by_usb_port(usb_slot)
        self.logger.info(f'USB slot:{usb_slot}, SN:{self.sn}')
        return self.sn
    
    def versions(self):
        """Get firmware version and software version."""
        return self.shell('versions')

    def battery_capacity(self):
        """Return current battery level of the device."""
        return int(self.shell('cat /sys/class/power_supply/battery/capacity'))

    def battery_voltage(self):
        """Return current battery voltage of the device."""
        return int(self.shell('cat /sys/class/power_supply/battery/voltage_now'))


def get_logger():
    """Function for creating logger."""
    _logger = logging.getLogger()
    _logger.setLevel(logging.DEBUG)
    stdout_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler("output.log")
    _logger.addHandler(stdout_handler)
    _logger.addHandler(file_handler)
    return _logger


# Example for using AdbManager class.
if __name__ == "__main__":
    logger = get_logger()
    # Initial class of AdbManager.
    adb = AdbManager(logger, 10)
    # Wait for device to be ready.
    adb.wait_for_device()
    # Get serial number by USB port and store SN into AdbManager.
    sn = adb.devices('2-1')
    print(sn)
    # List all apk by using "adb shell".
    adb.shell('pm list packages')
