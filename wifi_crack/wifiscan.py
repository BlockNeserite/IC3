#!/usr/bin/env python3
import subprocess
import re
import sys

def get_wifi_interface():
    """Определяет имя беспроводного интерфейса (обычно wlan0)."""
    try:
        result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if line.strip().startswith('Interface'):
                return line.split()[1]
    except:
        pass
    # fallback
    return 'wlan0'

def scan_wifi(interface):
    """Запускает сканирование iwlist и возвращает список сетей (BSSID, SSID)."""
    try:
        # iwlist требует прав root
        result = subprocess.run(['sudo', 'iwlist', interface, 'scan'], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Ошибка сканирования: {e.stderr}")
        print("Убедитесь, что интерфейс существует и у вас есть права (запустите с sudo).")
        sys.exit(1)

    # Разбиваем вывод на блоки, каждый начинается с "Cell "
    cells = re.split(r'Cell \d+ - ', result.stdout)[1:]

    networks = []
    for cell in cells:
        bssid_match = re.search(r'Address: ([0-9A-Fa-f:]{17})', cell)
        essid_match = re.search(r'ESSID:"(.*?)"', cell)
        if bssid_match:
            bssid = bssid_match.group(1)
            ssid = essid_match.group(1) if essid_match else ""
            if not ssid:   # скрытая сеть
                ssid = "<hidden>"
            networks.append({'ssid': ssid, 'bssid': bssid})
    return networks

def main():
    interface = get_wifi_interface()
    print(f"Сканируем сети через {interface}...")
    networks = scan_wifi(interface)

    if not networks:
        print("Сети не найдены или сканирование не дало результатов.")
        return

    print("\nДоступные сети:")
    for idx, net in enumerate(networks, start=1):
        print(f"{idx}. {net['ssid']}")

    try:
        choice = int(input("\nВведите номер сети: "))
        if 1 <= choice <= len(networks):
            selected = networks[choice-1]
            print(f"\nSSID: {selected['ssid']}")
            print(f"MAC (BSSID): {selected['bssid']}")
        else:
            print("Неверный номер.")
    except ValueError:
        print("Пожалуйста, введите число.")

if __name__ == "__main__":
    main()
