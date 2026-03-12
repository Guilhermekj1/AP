import os
import requests

SERVER_URL = "https://unreclining-melinda-intercarpellary.ngrok-free.dev"

PASTA = "."

for nome_arquivo in os.listdir(PASTA):

    caminho = os.path.join(PASTA, nome_arquivo)

    if os.path.isfile(caminho):

        try:
            with open(caminho, "rb") as f:

                files = {"file": (nome_arquivo, f)}

                r = requests.post(SERVER_URL, files=files)

                print("Enviado:", nome_arquivo, "| Resposta:", r.text)

        except Exception as e:
            print("Erro ao enviar", nome_arquivo, e)
