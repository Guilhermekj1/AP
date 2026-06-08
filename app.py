#!/usr/bin/env python3
"""
XMRig Auto-Manager for Windows
--------------------------------
Automates download, install, config, and execution of XMRig via CLI.
"""

import os
import sys
import json
import time
import socket
import logging
import zipfile
import tempfile
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional


# ─── Constants ────────────────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com/repos/xmrig/xmrig/releases/latest"
WORK_DIR = Path("C:/xmrig")
CONFIG_FILE = WORK_DIR / "config.json"
LOG_FILE = WORK_DIR / "xmrig_manager.log"

STATE_FILE = WORK_DIR / ".state.json"

process: Optional[subprocess.Popen] = None
process_lock = threading.Lock()


# ─── Logging Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("xmrig_manager")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def separator(title: str = "") -> None:
    line = "=" * 60
    if title:
        print(f"\n{line}\n    {title}\n{line}")
    else:
        print(line)


def wait_enter() -> None:
    input("\nPressione ENTER para continuar...")


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        log.warning("Nao foi possivel salvar estado: %s", e)


def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Nao foi possivel ler estado: %s", e)
    return {}


# ─── Requirement Checks ──────────────────────────────────────────────────────

def check_os() -> bool:
    if os.name != "nt":
        log.error("Este script funciona apenas no Windows.")
        return False
    log.info("Sistema operacional: Windows detectado.")
    return True


def check_internet() -> bool:
    log.info("Verificando conexao com a Internet...")
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5).close()
        log.info("Conexao com a Internet OK.")
        return True
    except OSError:
        log.error("Sem conexao com a Internet.")
        return False


def check_dependencies() -> bool:
    log.info("Verificando dependencias Python...")
    missing = []
    for mod in ("json", "os", "sys", "socket", "logging", "zipfile",
                 "tempfile", "subprocess", "threading", "urllib.request",
                 "pathlib", "datetime", "typing"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        log.error("Dependencias faltando: %s", ", ".join(missing))
        return False
    log.info("Todas as dependencias Python estao disponiveis.")
    return True


# ─── Install XMRig ───────────────────────────────────────────────────────────

def get_latest_release() -> Optional[dict]:
    log.info("Buscando ultima versao do XMRig no GitHub...")
    req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "xmrig-manager"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        log.error("Falha ao consultar GitHub API: %s", e)
        return None


def find_zip_asset(release: dict) -> Optional[str]:
    for asset in release.get("assets", []):
        name: str = asset.get("name", "")
        if "msvc" in name.lower() and name.endswith(".zip"):
            return asset.get("browser_download_url")
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".zip") and "win" in name.lower():
            return asset.get("browser_download_url")
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".zip"):
            return asset.get("browser_download_url")
    return None


def download_file(url: str, dest: Path) -> bool:
    log.info("Baixando %s ...", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xmrig-manager"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  Progresso: {pct}% ({downloaded // 1024} KB)", end="")
        print()
        log.info("Download concluido: %s", dest)
        return True
    except (urllib.error.URLError, OSError) as e:
        log.error("Erro no download: %s", e)
        return False


def extract_zip(zip_path: Path, extract_to: Path) -> bool:
    log.info("Extraindo %s para %s ...", zip_path.name, extract_to)
    try:
        if not zipfile.is_zipfile(zip_path):
            log.error("Arquivo ZIP corrompido ou invalido.")
            return False
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                log.error("ZIP corrompido: %s", bad)
                return False
            zf.extractall(extract_to)
        log.info("Extracao concluida.")
        return True
    except (zipfile.BadZipFile, OSError) as e:
        log.error("Falha ao extrair ZIP: %s", e)
        return False


def find_exe(directory: Path) -> Optional[Path]:
    log.info("Procurando xmrig.exe em %s ...", directory)
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower() == "xmrig.exe":
                return Path(root) / f
    log.warning("xmrig.exe nao encontrado em %s", directory)
    return None


def install_xmrig() -> bool:
    separator("INSTALAR XMRig")

    if not check_internet():
        return False

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    release = get_latest_release()
    if not release:
        return False

    tag = release.get("tag_name", "desconhecido")
    log.info("Ultima versao disponivel: %s", tag)

    url = find_zip_asset(release)
    if not url:
        log.error("Nenhum arquivo ZIP encontrado nos assets do release.")
        return False

    zip_dest = WORK_DIR / "xmrig.zip"
    if not download_file(url, zip_dest):
        return False

    extract_dir = WORK_DIR / f"xmrig-{tag}"
    if not extract_zip(zip_dest, extract_dir):
        return False

    exe = find_exe(extract_dir)
    if not exe:
        log.error("xmrig.exe nao encontrado apos extracao.")
        return False

    save_state({"version": tag, "exe_path": str(exe), "install_dir": str(extract_dir)})
    log.info("XMRig %s instalado com sucesso em %s", tag, exe)
    return True


# ─── Config ───────────────────────────────────────────────────────────────────

WALLET_DEFAULT = "48qupBCJdCb4Nx2WtmyxcYWYT1vUB3dj8h2cP6m9rKafgtJqnvzEPSQ7DiL8Kx4Vh6etcBTqZ2RmieBrgjpMeFmP6QoM5uG"
WORKER_DEFAULT = "p1"
POOL_DEFAULT = "gulf.moneroocean.stream"
PORT_DEFAULT = 10128


def configure() -> Optional[dict]:
    separator("CONFIGURAR XMRig")

    state = load_state()
    if not state.get("exe_path") or not Path(state["exe_path"]).exists():
        log.error("XMRig nao instalado. Instale primeiro.")
        return None

    wallet = input(f"Endereco da carteira [ENTER = padrao]: ").strip()
    if not wallet:
        wallet = WALLET_DEFAULT

    worker = input(f"Nome do worker [ENTER = {WORKER_DEFAULT}]: ").strip()
    if not worker:
        worker = WORKER_DEFAULT

    pool = input(f"Pool [ENTER = {POOL_DEFAULT}]: ").strip()
    if not pool:
        pool = POOL_DEFAULT

    port_str = input(f"Porta [ENTER = {PORT_DEFAULT}]: ").strip()
    if not port_str:
        port_str = str(PORT_DEFAULT)
    while not port_str.isdigit():
        port_str = input("Porta deve ser numerica: ").strip()
    port = int(port_str)

    config = {
        "wallet": wallet,
        "worker": worker,
        "pool": pool,
        "port": port,
    }
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        log.info("Configuracao salva em %s", CONFIG_FILE)
    except OSError as e:
        log.error("Erro ao salvar configuracao: %s", e)
        return None

    return config


def auto_configure() -> dict:
    config = {
        "wallet": WALLET_DEFAULT,
        "worker": WORKER_DEFAULT,
        "pool": POOL_DEFAULT,
        "port": PORT_DEFAULT,
    }
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        log.info("Configuracao automatica salva.")
    except OSError as e:
        log.error("Erro ao salvar configuracao automatica: %s", e)
    return config


def load_config() -> Optional[dict]:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return None


# ─── Process Management ──────────────────────────────────────────────────────

def start_xmrig() -> bool:
    global process
    with process_lock:
        if process and process.poll() is None:
            log.warning("XMRig ja esta em execucao.")
            return False

        state = load_state()
        exe_path_str = state.get("exe_path")
        if not exe_path_str or not Path(exe_path_str).exists():
            log.error("XMRig nao instalado. Instale primeiro.")
            return False

        cfg = load_config()
        if not cfg:
            log.error("Nenhuma configuracao encontrada. Configure primeiro.")
            return False

        exe_path = Path(exe_path_str)
        args = [str(exe_path),
                "-o", f"{cfg['pool']}:{cfg['port']}",
                "-u", f"{cfg['wallet']}+{cfg['worker']}",
                "-p", "x", "--keepalive"]

        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                cwd=str(exe_path.parent),
            )
            log.info("XMRig iniciado (PID %d).", process.pid)
            save_state(dict(load_state(), pid=process.pid))
            threading.Thread(target=_monitor_process, daemon=True).start()
            threading.Thread(target=_stream_output, daemon=True).start()
            return True
        except (OSError, subprocess.SubprocessError) as e:
            log.error("Falha ao iniciar XMRig: %s", e)
            return False


def stop_xmrig() -> bool:
    global process
    with process_lock:
        if process and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                log.info("XMRig parado.")
                process = None
                return True
            except OSError as e:
                log.error("Erro ao parar XMRig: %s", e)
                return False
        log.warning("XMRig nao esta em execucao.")
        return False


def restart_xmrig() -> bool:
    log.info("Reiniciando XMRig...")
    stop_xmrig()
    time.sleep(1)
    return start_xmrig()


def _monitor_process() -> None:
    global process
    with process_lock:
        p = process
    if p is None:
        return
    try:
        p.wait()
    except OSError:
        pass
    with process_lock:
        if process is p:
            log.warning("XMRig foi encerrado inesperadamente (codigo: %d).", p.returncode)
            process = None


def _stream_output() -> None:
    global process
    with process_lock:
        p = process
    if p is None or p.stdout is None:
        return
    try:
        for line in iter(p.stdout.readline, b""):
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                log.info("[XMRig] %s", text)
    except (OSError, ValueError):
        pass


# ─── Log Viewer ──────────────────────────────────────────────────────────────

def view_logs() -> None:
    separator("LOGS")
    log_path = LOG_FILE
    if not log_path.exists():
        print("Nenhum log encontrado.")
        return

    try:
        content = log_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        tail = lines[-50:] if len(lines) > 50 else lines
        print(f"\nUltimas {len(tail)} linhas de {log_path}:\n")
        for line in tail:
            print(line)
    except (OSError, UnicodeDecodeError) as e:
        log.error("Erro ao ler logs: %s", e)
    finally:
        print()


# ─── Status ──────────────────────────────────────────────────────────────────

def show_status() -> None:
    separator("STATUS")
    global process
    state = load_state()

    installed = state.get("exe_path") and Path(state["exe_path"]).exists()
    print(f"  Instalado:          {'SIM' if installed else 'NAO'}")
    if installed:
        print(f"  Versao:             {state.get('version', '?')}")
        print(f"  Executavel:         {state.get('exe_path', '?')}")

    cfg = load_config()
    if cfg:
        print(f"  Pool:               {cfg.get('pool', '?')}:{cfg.get('port', '?')}")
        print(f"  Wallet:             {cfg.get('wallet', '?')}")
        print(f"  Worker:             {cfg.get('worker', '?')}")

    with process_lock:
        running = process is not None and process.poll() is None
    print(f"  Executando:         {'SIM' if running else 'NAO'}")
    if running and process:
        print(f"  PID:                {process.pid}")
    print()


# ─── Prerequisites ───────────────────────────────────────────────────────────

def run_prerequisites() -> bool:
    if not check_os():
        return False
    if not check_dependencies():
        return False
    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not run_prerequisites():
        sys.exit(1)

    log.info("=" * 50)
    log.info("XMRig Auto-Manager iniciado")
    log.info("=" * 50)

    state = load_state()
    installed = state.get("exe_path") and Path(state["exe_path"]).exists()

    if not installed:
        log.info("XMRig nao instalado. Instalando...")
        if not install_xmrig():
            log.error("Falha na instalacao. Abortando.")
            sys.exit(1)
    else:
        log.info("XMRig ja instalado.")

    cfg = load_config()
    if not cfg:
        log.info("Nenhuma configuracao encontrada. Configurando automaticamente...")
        cfg = auto_configure()

    if not start_xmrig():
        log.error("Falha ao iniciar XMRig. Abortando.")
        sys.exit(1)

    log.info("XMRig em execucao. Pressione CTRL+C para parar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("CTRL+C detectado. Encerrando...")
    finally:
        stop_xmrig()
        log.info("XMRig encerrado.")


if __name__ == "__main__":
    main()
