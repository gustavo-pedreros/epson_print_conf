import os
import socket
import subprocess
import threading
import warnings

from epson_print_conf import EpsonPrinter

# suppress pysnmp warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

# common printer ports
PRINTER_PORTS = [9100, 515, 631]


def get_local_ipv4_addresses():
    """Return the list of non-loopback IPv4 addresses for this host.

    ``socket.gethostbyname_ex(socket.gethostname())`` is unreliable on
    Linux: many distributions (Debian/Ubuntu in particular) map the
    hostname to ``127.0.1.1`` in ``/etc/hosts``, so it returns only the
    loopback range and the subnet scan finds nothing. Discover real
    interface IPs instead by asking the kernel which source address it
    would use to reach a public destination (no packets are sent — UDP
    ``connect`` only sets the socket's local endpoint).
    """
    ips = set()
    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect((target, 80))
                ip = s.getsockname()[0]
        except OSError:
            continue
        if ip and not ip.startswith("127."):
            ips.add(ip)

    # Keep the original lookup as a fallback so multi-homed boxes with
    # additional addresses in DNS still get fully covered.
    try:
        _, _, hostname_ips = socket.gethostbyname_ex(socket.gethostname())
    except socket.gaierror:
        hostname_ips = []
    for ip in hostname_ips:
        if not ip.startswith("127."):
            ips.add(ip)

    return sorted(ips)


class PrinterScanner:

    def check_printer(self, ip, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((ip, port))
            sock.close()
            return True
        except socket.error:
            return False

    def get_printer_name(self, ip):
        printer = EpsonPrinter(hostname=ip)
        try:
            printer_info = printer.get_snmp_info("Model")
            return printer_info["Model"]
        except:
            return None

    def scan_ip(self, ip):
        for port in PRINTER_PORTS:
            if self.check_printer(ip, port):
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                except socket.herror:
                    hostname = "Unknown"

                return {
                    "ip": ip,
                    "hostname": hostname,
                }
        return None

    def get_all_printers(self, ip_addr="", local=False):
        if ip_addr:
            result = self.scan_ip(ip_addr)
            if result:
                result["name"] = self.get_printer_name(result['ip'])
                return [result]
        local_device_ip_list = get_local_ipv4_addresses()
        if local:
            return local_device_ip_list  # IP list
        printers = []
        for local_device_ip in local_device_ip_list:
            if ip_addr and not local_device_ip.startswith(ip_addr):
                continue
            base_ip = local_device_ip[:local_device_ip.rfind('.') + 1]
            ips=[f"{base_ip}{i}" for i in range(1, 255)]
            threads = []

            def worker(ip):
                result = self.scan_ip(ip)
                if result:
                    printers.append(result)

            for ip in ips:
                thread = threading.Thread(target=worker, args=(ip,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

        for i in printers:
            i["name"] = self.get_printer_name(i['ip'])
        return printers


if __name__ == "__main__":
    import sys
    ip = ""
    if len(sys.argv) > 1:
        ip = sys.argv[1]
    scanner = PrinterScanner()
    print(scanner.get_all_printers(ip))
