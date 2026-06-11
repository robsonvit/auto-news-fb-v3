#!/usr/bin/env python3
"""
SharesForYou → Facebook Auto-Poster Bot
Versão FINAL ABSOLUTA - Noticiário Profissional
"""

import os
import json
import time
import datetime
import logging
import hashlib
import textwrap
import requests
import random
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from requests.adapters import HTTPAdapter
import traceback
import subprocess
import glob
from dotenv import load_dotenv
import difflib

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Configurações
SFY_EMAIL    = os.environ.get("SFY_EMAIL", "")
SFY_PASSWORD = os.environ.get("SFY_PASSWORD", "")
FB_PAGE_ID   = os.environ.get("FB_PAGE_ID", "122181202022766925")
FB_TOKEN     = os.environ.get("FB_TOKEN", "")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")

POSTED_FILE  = "posted_ids.json"
SFY_SHARE    = "https://www.sharesforyou.com/dashboard/share"
SFY_LOGIN    = "https://www.sharesforyou.com/login"
FB_GRAPH     = "https://graph.facebook.com/v22.0"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}



def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    r = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=r))
    return s

# Palavras irrelevantes para normalização semântica de títulos
_STOP_WORDS = {
    "de","da","do","das","dos","a","o","as","os","e","em","no","na","nos","nas",
    "por","para","com","que","se","ao","à","um","uma","uns","umas","é","foi",
    "ser","ter","mais","mas","ou","ele","ela","eles","elas","seu","sua"
}

def normalizar_titulo(title):
    """Normaliza título removendo stop words, números e pontuação para comparação semântica."""
    t = title.lower()
    t = re.sub(r'[^\w\s]', '', t)          # Remove pontuação
    t = re.sub(r'\b\d+\b', '', t)          # Remove números isolados
    palavras = [w for w in t.split() if w not in _STOP_WORDS and len(w) > 2]
    return ' '.join(sorted(palavras))       # Ordena para capturar rearranjos de palavras

def make_article_id(title):
    """Gera ID estável baseado no título normalizado — imune a variações de pontuação/capitalização."""
    chave = normalizar_titulo(title)
    return hashlib.sha256(chave.encode('utf-8')).hexdigest()[:16]

def load_state():
    """
    Carrega o estado unificado do bot a partir do posted_ids.json.
    Retorna (set_de_ids, lista_de_titulos_recentes).
    Suporta tanto o formato legado (lista de IDs) quanto o novo formato (dict com ids + titles).
    """
    if not os.path.exists(POSTED_FILE):
        return set(), []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Formato legado: lista de strings
        if isinstance(data, list):
            log.info(f"📂 Estado legado carregado: {len(data)} IDs. Migrando para novo formato.")
            return set(data), []
        # Novo formato: dicionário
        if isinstance(data, dict):
            ids = set(data.get("ids", []))
            titles = data.get("titles", [])
            log.info(f"📂 Estado carregado: {len(ids)} IDs únicos | {len(titles)} títulos recentes.")
            return ids, titles
    except Exception as e:
        log.warning(f"⚠️ Erro ao carregar estado: {e}")
    return set(), []

def save_state(ids_set, titles_list):
    """Salva o estado unificado em formato JSON estruturado."""
    # Mantém os últimos 200 títulos para o fuzzy match (sem crescer indefinidamente)
    titles_list = titles_list[-200:]
    data = {
        "ids": sorted(list(ids_set)),
        "titles": titles_list
    }
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"💾 Estado salvo: {len(ids_set)} IDs | {len(titles_list)} títulos.")
    except Exception as e:
        log.error(f"❌ Falha ao salvar estado: {e}")

def load_recent_titles():
    """Carrega títulos recentes para o Gemini não repetir HOOKs visuais."""
    if os.path.exists("last_title.txt"):
        try:
            with open("last_title.txt", "r", encoding="utf-8") as f:
                return [linha.strip() for linha in f.readlines() if linha.strip()]
        except: return []
    return []

def save_recent_titles(titles_list):
    try:
        with open("last_title.txt", "w", encoding="utf-8") as f:
            for t in titles_list[-15:]:
                f.write(t + "\n")
    except: pass

def baixar_fonte(emoji=False):
    # Priorizar fonte local para compatibilidade com Nuvem (Linux)
    local_impact = os.path.join("fonts", "impact.ttf")
    if os.path.exists(local_impact): return local_impact

    if emoji:
        for f in ["C:\\Windows\\Fonts\\seguiemj.ttf"]:
            if os.path.exists(f): return f
            
    # Fallbacks de sistema
    for f in ["C:\\Windows\\Fonts\\impact.ttf", "fonts/NotoSans-Bold.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"]:
        if os.path.exists(f): return f
    return None

def limpar_emojis(texto):
    # Preserva caracteres acentuados e pontuação, removendo apenas o que não é texto 'humano'
    return re.sub(r'[^\w\s.,!?;:\"\'\(\)\-\u00C0-\u00FF]+', '', texto).strip()

# Mapeamento de emojis de reação do Facebook
FB_REACTIONS = {
    "LIKE": "1f44d",
    "LOVE": "2764-fe0f",
    "CARE": "1f917",
    "HAHA": "1f606",
    "WOW": "1f62e",
    "SAD": "1f622",
    "ANGRY": "1f621"
}

def gerar_gancho(title):
    default_res = {
        "hook": "BOMBA!!", "tag": "NOTÍCIA URGENTE",
        "color": (255, 0, 0, 200), "emoji": "1f6a8",
        "hashtags": "#noticias #urgente",
        "category": "URGENTE",
        "reactions": [("1f631", "Finalmente!"), ("1f44d", "Boa notícia"), ("1f621", "Duvido muito")],
        "misterio": "VEJA O QUE ACONTECEU AGORA"
    }
    
    if not GEMINI_KEY:
        return default_res

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        f"Analise a notícia: \"{title}\".\n"
        f"Retorne APENAS um JSON válido com a seguinte estrutura:\n"
        "{\n"
        "  \"hook\": \"Título curtíssimo (máx 3 palavras) em CAIXA ALTA sobre a notícia para ir na imagem. CAMUFLE palavras sensíveis (M0RT3, S@NGU3)\",\n"
        "  \"tag\": \"Categoria curta (ex: URGENTE, POLÍTICA, FOFOCA, CRIME)\",\n"
        "  \"emoji\": \"código hexadecimal do emoji sem U+, ex: 1f6a8\",\n"
        "  \"hashtags\": \"#hashtag1 #hashtag2 #hashtag3\",\n"
        "  \"misterio\": \"Frase incompleta que gere curiosidade (ex: O que foi descoberto vai te chocar...)\"\n"
        "}\n"
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                resp_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                dados = json.loads(resp_text)
                
                for k in ["hook", "tag", "emoji", "hashtags", "misterio"]:
                    if k in dados:
                        default_res[k] = dados[k]
                        
                default_res["emoji"] = default_res["emoji"].replace("U+", "").lower().strip()
                log.info(f"🧠 Gemini gerou o título com sucesso: {default_res['hook']}")
                return default_res
            elif r.status_code == 429:
                log.warning(f"⚠️ Rate limit do Gemini (429). Tentativa {attempt+1}/3. Aguardando...")
                time.sleep(10)
            else:
                log.warning(f"⚠️ Erro do Gemini (Status {r.status_code}): {r.text}")
                break
        except Exception as e:
            log.warning(f"⚠️ Exceção na IA do Gemini (Tentativa {attempt+1}/3): {e}")
            time.sleep(5)
            
    log.warning("❌ Falha em todas as tentativas do Gemini. Usando título genérico.")
    return default_res

def gerar_video_ffmpeg(img_path, audio_path, output_path, duration=20):
    """
    Cria um vídeo com movimento real (efeito Ken Burns / zoom suave) a partir de uma
    imagem e um áudio — evitando detecção como 'imagem estática' pelo Facebook.
    Resolução saída: 1080x1920 (9:16), bitrate alto, sem tune stillimage.
    """
    log.info(f"🎞️ Gerando vídeo DINÂMICO de {duration}s com Ken Burns...")
    try:
        fps = 30
        total_frames = duration * fps

        # Efeito Ken Burns: zoom gradual de 1.0 → 1.08 ao longo de todos os frames
        # A imagem de entrada já está em 2160x3840 — resolução ideal para o zoom sem artefatos
        # zoompan trabalha no tamanho original da imagem e escala a saída para 1080x1920
        zoom_filter = (
            f"zoompan=z='min(zoom+0.0003,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps}"
        )

        # Fade de áudio: 0.5s no início e 1s no final
        audio_filter = f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(duration-1,0)}:d=1"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-framerate", str(fps),
            "-i", img_path,
            "-stream_loop", "-1",
            "-i", audio_path,
            "-vf", zoom_filter,
            "-af", audio_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-profile:v", "high",
            "-level", "4.0",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-t", str(duration),
            output_path
        ]
        result = subprocess.run(cmd, check=True, capture_output=True)
        log.info(f"✅ Vídeo dinâmico gerado: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ Erro no FFmpeg (código {e.returncode}): {e.stderr.decode('utf-8', errors='replace')[-500:]}")
        return False
    except Exception as e:
        log.error(f"❌ Erro inesperado no FFmpeg: {e}")
        return False

def publicar_reel(page_id, token, video_path, message):
    """
    Publica um Reel no Facebook usando o processo de 3 etapas (Start, Upload, Finish).
    """
    log.info("🚀 Iniciando upload de Reel...")
    
    # 1. Start Upload Session
    try:
        url_init = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
        res_init = requests.post(url_init, params={
            "upload_phase": "start",
            "access_token": token
        }, timeout=30).json()
        
        video_id = res_init.get("video_id")
        if not video_id:
            log.error(f"Erro ao iniciar sessão Reel: {res_init}")
            return None
            
        # 2. Upload the Video
        file_size = os.path.getsize(video_path)
        url_upload = f"https://rupload.facebook.com/video-upload/v22.0/{video_id}"
        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream"
        }
        with open(video_path, "rb") as f:
            res_up = requests.post(url_upload, headers=headers, data=f, timeout=120)
            
        if res_up.status_code != 200:
            log.error(f"Erro no upload binário: {res_up.text}")
            return None
            
        # 3. Finish and Publish
        url_finish = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
        payload = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": message,
            "access_token": token
        }
        res_finish = requests.post(url_finish, data=payload, timeout=30).json()
        
        if res_finish.get("success"):
            log.info(f"✅ REEL PUBLICADO! ID: {video_id}")
            return video_id
        else:
            log.error(f"Erro ao finalizar Reel: {res_finish}")
            return None
            
    except Exception as e:
        log.error(f"Erro no processo de publicação de Reel: {e}")
        return None

def publicar_imagem(page_id, token, img_path, message):
    """
    Publica uma foto na página do Facebook.
    """
    log.info("📸 Iniciando postagem da imagem...")
    try:
        url = f"https://graph.facebook.com/v22.0/{page_id}/photos"
        payload = {
            "message": message,
            "access_token": token
        }
        with open(img_path, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=60).json()
            
        if res.get("id"):
            log.info(f"✅ IMAGEM PUBLICADA! ID: {res.get('id')}")
            return res.get("id")
        else:
            log.error(f"Erro ao publicar imagem: {res}")
            return None
    except Exception as e:
        log.error(f"Erro no processo de publicação de imagem: {e}")
        return None

def adicionar_texto_premium(img_bytes, dados_esteticos):
    MAIN_COLOR = dados_esteticos["color"]
    texto = dados_esteticos["hook"]
    tag_texto = dados_esteticos["tag"]
    emoji_hex = dados_esteticos["emoji"]

    img_orig = Image.open(BytesIO(img_bytes)).convert("RGB")
    w_orig, h_orig = img_orig.size
    font_path = baixar_fonte()

    def build_ui(target_ratio):
        sf = 2
        base_w = 1080
        base_h = int(1080 / target_ratio)
        bw, bh = base_w * sf, base_h * sf

        # 1. Crop quadrado da imagem original
        img_ratio = w_orig / h_orig
        if img_ratio > target_ratio:
            new_w = h_orig * target_ratio
            new_h = h_orig
        else:
            new_w = w_orig
            new_h = w_orig / target_ratio

        left = (w_orig - new_w) / 2
        top = (h_orig - new_h) / 2
        img_cropped = img_orig.crop((left, top, left + new_w, top + new_h))
        
        # 2. Redimensionamento e Melhoria da imagem base
        img_core = img_cropped.resize((int(bw), int(bh)), Image.Resampling.LANCZOS)
        img_core = ImageEnhance.Color(img_core).enhance(1.3)
        img_core = ImageEnhance.Contrast(img_core).enhance(1.1)
        img_core = ImageEnhance.Sharpness(img_core).enhance(1.4)

        # 3. Gradiente de base (escurecer parte inferior para leitura do título)
        overlay = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_h = int(bh * 0.50)
        for y in range(int(bh) - grad_h, int(bh)):
            alpha = int(240 * ((y - (bh - grad_h)) / grad_h))
            draw_ov.line([(0, y), (int(bw), y)], fill=(0, 0, 0, max(0, min(255, alpha))))
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=5 * sf))
        img_core = Image.alpha_composite(img_core.convert("RGBA"), overlay)
        
        draw_core = ImageDraw.Draw(img_core)

        # 4. Selo de Categoria (Topo)
        badge_h = int(bw * 0.05)
        f_badge = ImageFont.truetype(font_path, int(badge_h * 0.75)) if font_path else ImageFont.load_default()
        bbox_b = draw_core.textbbox((0, 0), tag_texto, font=f_badge)
        badge_w = (bbox_b[2] - bbox_b[0]) + (40 * sf)
        bx1, by1 = 30 * sf, 40 * sf
        bx2, by2 = bx1 + badge_w, by1 + badge_h
        draw_core.rectangle([bx1, by1, bx2, by2], fill=MAIN_COLOR)
        draw_core.text(((bx1 + bx2) // 2, (by1 + by2) // 2), tag_texto, font=f_badge, fill=(255, 255, 255), anchor="mm")

        # 5. Título (HOOK) — posicionado na parte inferior
        texto_puro = limpar_emojis(texto)
        f_size = int(bw * 0.10)
        font = ImageFont.truetype(font_path, f_size) if font_path else ImageFont.load_default()

        l = texto_puro.strip()
        bb = draw_core.textbbox((0, 0), l, font=font)
        lw, lh = bb[2] - bb[0], bb[3] - bb[1]

        if lw > (bw - 100 * sf):
            f_size = int(f_size * (bw - 100 * sf) / lw)
            font = ImageFont.truetype(font_path, f_size) if font_path else ImageFont.load_default()
            bb = draw_core.textbbox((0, 0), l, font=font)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]

        tx = (bw - lw) // 2
        padding = 35 * sf
        ty = int(bh * 0.85) - lh # Posicionado no terço inferior

        # Fundo do Título (Box)
        tx1, ty1 = tx - padding, ty - padding
        tx2, ty2 = tx + lw + padding, ty + lh + padding
        temp_box = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
        ImageDraw.Draw(temp_box).rectangle([tx1, ty1, tx2, ty2], fill=MAIN_COLOR)
        img_core = Image.alpha_composite(img_core, temp_box)

        # SOMBRA DO TÍTULO
        cx, cy = (tx1 + tx2) // 2, (ty1 + ty2) // 2
        shadow_layer = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer)
        s_draw.text((cx + 4 * sf, cy + 4 * sf), l, font=font, fill=(0, 0, 0, 200), anchor="mm")
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=3 * sf))
        img_core = Image.alpha_composite(img_core, shadow_layer)

        # Texto do Título
        draw_core = ImageDraw.Draw(img_core)
        draw_core.text((cx, cy), l, font=font, fill=(255, 255, 255), anchor="mm")

        # 6. Ícone Principal (acima do título)
        try:
            emoji_url = f"https://raw.githubusercontent.com/iamcal/emoji-data/master/img-apple-160/{emoji_hex}.png"
            r_emoji = requests.get(emoji_url, timeout=10)
            if r_emoji.status_code == 200:
                e_img = Image.open(BytesIO(r_emoji.content)).convert("RGBA")
                e_size = int(f_size * 1.5)
                e_img = e_img.resize((e_size, e_size), Image.Resampling.LANCZOS)
                ix, iy = (bw - e_size) // 2, ty1 - e_size - (2 * sf)
                
                # Sombra do Ícone Principal
                e_shadow = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
                ImageDraw.Draw(e_shadow).ellipse(
                    [ix + 6*sf, iy + 6*sf, ix + e_size + 6*sf, iy + e_size + 6*sf],
                    fill=(0, 0, 0, 150)
                )
                e_shadow = e_shadow.filter(ImageFilter.GaussianBlur(radius=6*sf))
                img_core = Image.alpha_composite(img_core, e_shadow)
                
                img_core.paste(e_img, (int(ix), int(iy)), e_img)
        except: pass

        # 7. Chamada para Ação (Call to Action - Legenda)
        cta_y = ty2 + int(60 * sf)
        f_cta_size = int(badge_h * 0.65)
        f_cta = ImageFont.truetype(font_path, f_cta_size) if font_path else ImageFont.load_default()
        
        cta_text = "VEJA MAIS NA LEGENDA"
        emoji_hex_cta = "1f447" # 👇
        
        draw_core = ImageDraw.Draw(img_core)
        lbb = draw_core.textbbox((0, 0), cta_text, font=f_cta)
        lw_text = lbb[2] - lbb[0]
        
        r_emoji_size = int(f_cta_size * 1.3)
        espacinho = int(15 * sf)
        
        total_w = r_emoji_size + espacinho + lw_text + espacinho + r_emoji_size
        rx = (bw - total_w) // 2
        
        try:
            r_url = f"https://raw.githubusercontent.com/iamcal/emoji-data/master/img-apple-160/{emoji_hex_cta}.png"
            r_resp = requests.get(r_url, timeout=10)
            
            if r_resp.status_code == 200:
                ri = Image.open(BytesIO(r_resp.content)).convert("RGBA")
                ri = ri.resize((r_emoji_size, r_emoji_size), Image.Resampling.LANCZOS)
                
                # Emoji Esquerdo
                img_core.paste(ri, (int(rx), int(cta_y - (r_emoji_size // 4))), ri)
                
                # Texto Central
                tx_pos = rx + r_emoji_size + espacinho
                ty_pos = cta_y + (r_emoji_size // 4)
                draw_core.text((tx_pos + 2*sf, ty_pos + 2*sf), cta_text, font=f_cta, fill=(0, 0, 0, 180), anchor="lm")
                draw_core.text((tx_pos, ty_pos), cta_text, font=f_cta, fill=(255, 255, 255), anchor="lm")
                
                # Emoji Direito
                rx_right = tx_pos + lw_text + espacinho
                img_core.paste(ri, (int(rx_right), int(cta_y - (r_emoji_size // 4))), ri)
            else:
                # Fallback sem imagem
                draw_core.text((bw // 2 + 2*sf, cta_y + 2*sf), f"👇 {cta_text} 👇", font=f_cta, fill=(0, 0, 0, 180), anchor="mt")
                draw_core.text((bw // 2, cta_y), f"👇 {cta_text} 👇", font=f_cta, fill=(255, 255, 255), anchor="mt")
        except:
            draw_core.text((bw // 2 + 2*sf, cta_y + 2*sf), f"👇 {cta_text} 👇", font=f_cta, fill=(0, 0, 0, 180), anchor="mt")
            draw_core.text((bw // 2, cta_y), f"👇 {cta_text} 👇", font=f_cta, fill=(255, 255, 255), anchor="mt")

        return img_core

    # A) IMAGEM REEL (Centro 1:1 + Blur 9:16)
    img_core_1_1 = build_ui(1.0)
    sf = 2
    tw_sf, th_sf = 2160, 3840
    bg_size = th_sf
    background = img_core_1_1.resize((bg_size, bg_size), Image.Resampling.LANCZOS)
    left = (bg_size - tw_sf) // 2
    background = background.crop((left, 0, left + tw_sf, th_sf))
    background = background.filter(ImageFilter.GaussianBlur(radius=20 * sf))
    background = ImageEnhance.Brightness(background).enhance(0.55)
    canvas_916 = background
    img_core_scaled = img_core_1_1.resize((tw_sf, tw_sf), Image.Resampling.LANCZOS)
    y_offset = (th_sf - tw_sf) // 2
    canvas_916.paste(img_core_scaled.convert("RGBA"), (0, y_offset), img_core_scaled.convert("RGBA"))
    out_reel = BytesIO()
    canvas_916.convert("RGB").save(out_reel, format="JPEG", quality=98)

    # B) IMAGEM POST (4:5 puro)
    img_core_4_5 = build_ui(0.8) # 4:5 é width/height = 4/5 = 0.8
    out_post = BytesIO()
    img_core_4_5.convert("RGB").save(out_post, format="JPEG", quality=98)

    return out_reel.getvalue(), out_post.getvalue()

def _selecionar_link_correto(links_info: list) -> str:
    """
    Seleciona o link correto do card SFY.
    Prioridade:
      1. Ícone 'T' (ti-bold, ti-typography, ti-article, ti-letter-t) — link rastreado
      2. Link com padrão SFY (/share/, /post/, /artigo/)
      3. Primeiro link que não seja 'olho', 'facebook' ou 'copiar'
      4. Qualquer primeiro link disponível
    """
    # Prioridade 1: ícone T
    for li in links_info:
        icone = li.get("iconeClasse", "")
        if any(cls in icone for cls in ["ti-bold", "ti-typography", "ti-article",
                                         "ti-letter-t", "ti-text", "ti-file-text", "ti-news"]):
            return li.get("href", "")
    # Prioridade 2: padrão SFY
    for li in links_info:
        href = li.get("href", "")
        if any(p in href for p in ["/share/", "/post/", "/artigo/", "sharesforyou.com"]):
            return href
    # Prioridade 3: não-olho
    for li in links_info:
        icone = li.get("iconeClasse", "")
        if not any(skip in icone for skip in ["ti-eye", "ti-brand-facebook", "ti-share", "ti-copy"]):
            return li.get("href", "")
    # Fallback
    return links_info[0].get("href", "") if links_info else ""


def salvar_links_noticias(noticias: list):
    """
    Exporta os links extraídos para links_noticias.json.
    O Clicador de Links consome este arquivo para saber quais links clicar.
    """
    hoje = datetime.date.today().isoformat()
    try:
        existente = {"links": []}
        if os.path.exists("links_noticias.json"):
            with open("links_noticias.json", "r", encoding="utf-8") as f:
                existente = json.load(f)

        links_existentes = {item["link"] for item in existente.get("links", [])}
        novos = 0
        for n in noticias:
            if n["link"] not in links_existentes:
                existente["links"].append({
                    "titulo": n["title"],
                    "link":   n["link"],
                    "data":   hoje,
                })
                novos += 1

        existente["ultima_atualizacao"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with open("links_noticias.json", "w", encoding="utf-8") as f:
            json.dump(existente, f, indent=2, ensure_ascii=False)
        log.info(f"📤 links_noticias.json atualizado — {novos} links novos exportados para o Clicador.")
    except Exception as e:
        log.warning(f"⚠️ Não foi possível salvar links_noticias.json: {e}")


def get_noticias():
    import datetime
    from playwright.sync_api import sync_playwright
    res = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            log.info("Acessando SFY...")
            page.goto(SFY_LOGIN)
            page.fill("input[name='email']", SFY_EMAIL)
            page.fill("input[name='password']", SFY_PASSWORD)
            page.click("button[type='submit']")
            page.wait_for_url("**/dashboard**", timeout=40000)
            page.goto(SFY_SHARE)
            page.wait_for_timeout(7000)

            log.info("Selecionando bloco Sharesforyou...")
            try:
                page.click("button.change-order-by:has-text('Sharesforyou')", timeout=15000)
                page.wait_for_timeout(10000)
            except Exception as e:
                log.warning(f"Não foi possível clicar no botão Sharesforyou: {e}")

            cards = page.locator(".card").all()
            log.info(f"Encontrados {len(cards)} cards no bloco Sharesforyou.")

            for card in cards:
                try:
                    title = card.locator("h5, p.fs-4").first.inner_text().strip()
                    img = card.locator("img").first.get_attribute("src")

                    # === SELETOR CORRETO: inspeciona todos os links do card ===
                    links_info = card.evaluate("""el => {
                        return Array.from(el.querySelectorAll('a[href]'))
                            .filter(a => {
                                const href = a.getAttribute('href') || '';
                                return href.length > 1 && !href.startsWith('#')
                                    && !href.includes('javascript:') && !a.querySelector('img');
                            })
                            .map(a => ({
                                href: a.getAttribute('href'),
                                iconeClasse: (a.querySelector('i') || {}).className || ''
                            }));
                    }""")

                    if not title or not links_info:
                        continue

                    link = _selecionar_link_correto(links_info)
                    if not link:
                        continue

                    if link.startswith("/"):  link = "https://www.sharesforyou.com" + link
                    if img and img.startswith("/"): img = "https://www.sharesforyou.com" + img

                    log.info(f"  ✅ Link extraído: {link[:80]}")
                    res.append({"id": make_article_id(title), "title": title,
                                "link": link, "img": img})
                except Exception as ce:
                    log.debug(f"Erro no card: {ce}")
                    continue
        except Exception as e:
            log.error(f"Erro Playwright: {e}")
        finally:
            browser.close()

    # Exporta os links para o Clicador de Links consumir
    if res:
        salvar_links_noticias(res)

    return res

def main():
    log.info("Bot Profissional Notícias Iniciado.")
    
    # Ler tokens diretamente das variáveis de ambiente (padrão do GitHub Actions)
    load_dotenv(override=True)
    FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
    FB_TOKEN   = os.environ.get("FB_TOKEN", "").strip()
    
    if not FB_TOKEN or not FB_PAGE_ID:
        log.error("❌ FB_TOKEN ou FB_PAGE_ID não configurados. Encerrando.")
        return
    
    log.info(f"🔑 PAGE_ID: {FB_PAGE_ID}")
    log.info(f"🔑 TOKEN: {FB_TOKEN[:20]}...")

    posted_ids, posted_titles = load_state()
    news = get_noticias()
    if not news:
        log.warning("Nenhuma notícia encontrada.")
        return
    
    log.info(f"📰 {len(news)} notícias encontradas. Verificando duplicatas...")
    n_puladas = 0
    
    for n in news:
        # --- CAMADA 1: Hash exato pelo ID (título normalizado) ---
        if n["id"] in posted_ids:
            log.info(f"⏭️ [ID] Pulando: {n['title'][:60]}")
            n_puladas += 1
            continue
        
        # --- CAMADA 2: Fuzzy match semântico contra os últimos 200 títulos ---
        titulo_norm = normalizar_titulo(n["title"])
        similaridade_encontrada = False
        melhor_match = 0.0
        
        for titulo_hist in posted_titles:
            ratio = difflib.SequenceMatcher(None, titulo_norm, titulo_hist).ratio()
            if ratio > melhor_match:
                melhor_match = ratio
            # Threshold de 0.80 — equilibrado: pega reescritas, permite notícias diferentes
            if ratio >= 0.80:
                similaridade_encontrada = True
                log.info(f"⏭️ [Fuzzy {ratio*100:.1f}%] Pulando: {n['title'][:60]}")
                break
        
        if not similaridade_encontrada and melhor_match > 0:
            log.info(f"  ✅ Mais parecida encontrada: {melhor_match*100:.1f}% — permitida.")
        
        if similaridade_encontrada:
            n_puladas += 1
            continue
        
        log.info(f"🆕 Notícia inédita encontrada: {n['title'][:60]}")
        
        try:
            # Baixar imagem apenas agora que sabemos que vamos postar
            img_data = None
            if n.get("img"):
                log.info(f"📥 Baixando imagem: {n['img'][:50]}...")
                try:
                    r_img = requests.get(n["img"], headers=HEADERS, timeout=15)
                    if r_img.status_code == 200:
                        img_data = r_img.content
                        log.info(f"✅ Imagem baixada ({len(img_data)//1024}KB)")
                except Exception as e_img:
                    log.warning(f"⚠️ Erro no download simples: {e_img}")

            if not img_data:
                log.warning(f"⚠️ Sem imagem válida para: {n['title'][:50]}, pulando.")
                continue
            
            estetica = gerar_gancho(n["title"])
            img_reel_b, img_post_b = adicionar_texto_premium(img_data, estetica)
            
            # Salvar imagem temporária para o FFmpeg (Reel)
            temp_reel_img = "temp_reel_base.jpg"
            with open(temp_reel_img, "wb") as f:
                f.write(img_reel_b)

            # Salvar imagem temporária para o Post de Foto
            temp_post_img = "temp_post.jpg"
            with open(temp_post_img, "wb") as f:
                f.write(img_post_b)
            
            # Selecionar áudio aleatório
            audio_files = glob.glob("AUDIOS NEWS/*.mp3")
            if not audio_files:
                log.error("❌ Nenhum arquivo MP3 encontrado na pasta AUDIOS NEWS!")
                continue
            
            audio_sel = random.choice(audio_files)
            temp_video = "temp_reel.mp4"
            # Facebook exige entre 15 e 90s; usamos 20-45s para garantir qualidade
            duracao_random = random.randint(20, 45)
            
            if not gerar_video_ffmpeg(temp_reel_img, audio_sel, temp_video, duration=duracao_random):
                continue
            
            hashtags = estetica.get("hashtags", "#noticias #brasil").lower()
            misterio = estetica.get("misterio", "VEJA O QUE ACONTECEU AGORA")
            
            # Formatação solicitada: 
            # 😱 TAG: MISTERIO... 😱
            # .
            # #hashtags
            # .
            # .
            # .
            # 🔗VEJA MAIS NO LINK: URL
            
            padding_bottom = "\n.\n.\n.\n"
            msg = f"😱 {estetica['tag'].upper()}: {misterio}... 😱\n.\n{hashtags}{padding_bottom}🔗VEJA MAIS NO LINK: {n['link']}"
            
            video_id = publicar_reel(FB_PAGE_ID, FB_TOKEN, temp_video, msg)
            
            if video_id:
                log.info(f"🔗 LINK REEL: https://www.facebook.com/reels/{video_id}/")
                
                # --- NOVO: Postar a imagem logo após o Reel ---
                img_post_id = publicar_imagem(FB_PAGE_ID, FB_TOKEN, temp_post_img, msg)
                if img_post_id:
                    # O ID retornado geralmente é PostID ou PhotoID. Apenas reportamos sucesso.
                    log.info(f"📸 Sucesso! A imagem também foi postada.")
                
                # Registra o ID e o título normalizado para deduplicação futura
                posted_ids.add(n["id"])
                posted_titles.append(normalizar_titulo(n["title"]))
                save_state(posted_ids, posted_titles)
                
                # Limpeza
                for f in [temp_img, temp_video]:
                    if os.path.exists(f): os.remove(f)
                break
            else:
                log.error("Falha ao publicar Reel.")
                
                # Tentar identificar se o erro foi de TOKEN expirado (OAuthException 190)
                # O erro costuma vir no log do publicar_reel ou no traceback.
                # Se for token, não adianta tentar as próximas notícias agora.
                if os.path.exists(temp_img): os.remove(temp_img)
                if os.path.exists(temp_video): os.remove(temp_video)
                
                # Verificação simplificada de erro de token no log (simulada aqui pelo fluxo)
                # Em um cenário real, poderíamos checar a resposta da API Meta no publicar_reel
                # Como o erro ocorreu 190/463 nos logs do usuário, vamos forçar parada se falhar.
                log.warning("🛑 Interrompendo execução por falha na publicação (verifique o TOKEN).")
                break
        except Exception as e: 
            log.error(f"Erro no loop principal: {e}")
            log.error(traceback.format_exc())

if __name__ == "__main__": main()
