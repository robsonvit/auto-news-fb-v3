import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# Dados do .env
APP_ID = "1283566600658374"
APP_SECRET = "bf2533e5778d3036b43a61c6f1f9c192"
PAGE_ID = "1021302557732355"
USER_TOKEN_INPUT = "XXX"

def renovar():
    print("Transformando em token de longa duracao...")
    
    url = "https://graph.facebook.com/v22.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": USER_TOKEN_INPUT
    }
    
    r = requests.get(url, params=params)
    res = r.json()
    
    if "access_token" not in res:
        print(f"Erro na troca: {res}")
        return
    
    long_user_token = res["access_token"]
    print("Token de Usuario (60 dias) gerado!")

    url_acc = f"https://graph.facebook.com/v22.0/me/accounts?access_token={long_user_token}"
    r_acc = requests.get(url_acc)
    acc_data = r_acc.json()
    
    page_token = None
    if "data" in acc_data:
        for p in acc_data["data"]:
            if p["id"] == PAGE_ID:
                page_token = p["access_token"]
                break
    
    if page_token:
        print("\n--- RESULTADOS PARA O GITHUB ---")
        print(f"\nFB_USER_TOKEN:\n{long_user_token}")
        print(f"\nFB_TOKEN:\n{page_token}")
        
        # Atualiza o .env local
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            with open(".env", "w", encoding="utf-8") as f:
                for line in lines:
                    if line.startswith("FB_USER_TOKEN="):
                        f.write(f"FB_USER_TOKEN={long_user_token}\n")
                    elif line.startswith("FB_TOKEN="):
                        f.write(f"FB_TOKEN={page_token}\n")
                    else:
                        f.write(line)
            print("\nArquivo .env local atualizado!")
    else:
        print(f"Nao encontrei a pagina {PAGE_ID} nas contas desse token.")

renovar()
