import os
import requests
from dotenv import load_dotenv

def check_gemini_key():
    load_dotenv(override=True)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("❌ Nenhuma GEMINI_API_KEY encontrada no .env")
        return
    
    print(f"--- Testando chave: {key[:10]}... ---")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    payload = {"contents":[{"parts":[{"text":"oi"}]}]}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("INFO: A chave AINDA ESTA ATIVA e funcionando!")
            print("AVISO: Se voce ja deletou no AI Studio, pode levar alguns minutos para desativar.")
        else:
            print(f"STOP: Chave desativada ou invalida (Status: {r.status_code})")
            print(f"Mensagem: {r.text}")
    except Exception as e:
        print(f"ERRO: Erro ao testar chave: {e}")


if __name__ == "__main__":
    check_gemini_key()
