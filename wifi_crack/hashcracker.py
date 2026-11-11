import hashlib
import itertools
import string
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- Вспомогательные функции ----------
def hash_string(text, algo='md5'):
    h = hashlib.new(algo)
    h.update(text.encode('utf-8'))
    return h.hexdigest()

def index_to_phrase(index, alphabet, length):
    """Преобразует индекс в комбинацию символов заданной длины."""
    base = len(alphabet)
    chars = []
    for _ in range(length):
        chars.append(alphabet[index % base])
        index //= base
    return ''.join(reversed(chars))

# ---------- Основная логика перебора ----------
def crack_range(target_hash, algo, alphabet, length, start_idx, end_idx, stop_event, result_holder):
    """Проверяет индексы [start_idx, end_idx). При нахождении устанавливает результат и событие."""
    for idx in range(start_idx, end_idx):
        if stop_event.is_set():
            return
        phrase = index_to_phrase(idx, alphabet, length)
        if hash_string(phrase, algo) == target_hash:
            result_holder['phrase'] = phrase
            stop_event.set()
            return

def brute_force_threaded(target_hash, algo='md5', max_length=4, alphabet=None, num_workers=8):
    if alphabet is None:
        alphabet = string.ascii_letters + string.digits + string.punctuation  # 94 символа

    print(f"[*] Многопоточный перебор (алфавит: {len(alphabet)} симв., макс. длина {max_length}, потоков: {num_workers})")

    for length in range(1, max_length + 1):
        total = len(alphabet) ** length
        print(f"    Длина {length}: всего комбинаций {total:,}")
        if total == 0:
            continue

        # Общие объекты для потоков
        stop_event = threading.Event()
        result_holder = {'phrase': None}

        # Разбиваем на чанки по индексам
        chunk_size = max(1, total // num_workers)
        futures = []
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            for start in range(0, total, chunk_size):
                end = min(start + chunk_size, total)
                futures.append(executor.submit(
                    crack_range,
                    target_hash, algo, alphabet, length,
                    start, end, stop_event, result_holder
                ))

            # Ожидаем завершения или прерывания при нахождении
            for f in as_completed(futures):
                if stop_event.is_set():
                    break
                f.result()  # исключения, если будут

        if result_holder['phrase'] is not None:
            return result_holder['phrase']
    return None

# ---------- CLI ----------
def main():
    if len(sys.argv) < 2:
        print("Использование: python hash_cracker.py <хеш> [алгоритм] [число_потоков]")
        print("Пример: python hash_cracker.py 5d41402abc4b2a76b9719d911017c592 md5 8")
        sys.exit(1)

    target_hash = sys.argv[1].strip().lower()
    algo = sys.argv[2].lower() if len(sys.argv) > 2 else 'md5'
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    if algo not in ['md5', 'sha1', 'sha256']:
        print("Поддерживаются: md5, sha1, sha256")
        sys.exit(1)

    print(f"Целевой хеш ({algo}): {target_hash}")

    # Попробуем быстрый словарь (опционально, как ранее)
    # затем многопоточный перебор
    result = brute_force_threaded(target_hash, algo, max_length=4, num_workers=workers)
    if result:
        print(f"[+] Найдено: {result}")
    else:
        print("[-] Фраза не найдена.")

if __name__ == "__main__":
    main()
