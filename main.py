# ✅ BOT DA FORCA - VERSÃO AJUSTADA PARA RENDER WEB SERVICE COM FLASK

import telebot
import json
import random
import time
import threading
import os
from datetime import datetime, timedelta
from flask import Flask, request

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
bot = telebot.TeleBot(API_TOKEN)

# === CONFIGURAÇÕES ===
TEMPO_ENTRE_RODADAS = 600  # 10 minutos
HORARIO_RANKING_FINAL = "23:30"
GRUPOS_PERMITIDOS = []  # Vazio significa sem restrição

# === VARIÁVEIS DE CONTROLE ===
usuarios_jogo = {}
pontuacao_diaria = {}
historico_palavras = []
mensagens_anteriores = {}
ultima_rodada = {}
rodada_ativa = {}
rodada_dados = {}

# === FUNÇÕES ===
def carregar_palavras():
    try:
        with open("palavras.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def escolher_palavra():
    palavras = carregar_palavras()
    candidatas = list(set(palavras) - set(historico_palavras[-60:]))
    if not candidatas:
        historico_palavras.clear()
        candidatas = palavras
    if not candidatas:
        return "erro"
    palavra = random.choice(candidatas)
    historico_palavras.append(palavra)
    return palavra.lower()

def formatar_palavra(palavra, certas):
    return ' '.join([letra if letra in certas else '_' for letra in palavra])

def enviar_mensagem(chat_id, texto):
    msg = bot.send_message(chat_id, texto, parse_mode="Markdown")
    mensagens_anteriores.setdefault(chat_id, []).append(msg.message_id)

def apagar_mensagens(chat_id):
    msgs = mensagens_anteriores.get(chat_id, [])
    for msg_id in msgs[:-2]:
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
    mensagens_anteriores[chat_id] = msgs[-2:]

def gerar_ranking():
    if not pontuacao_diaria:
        return "\ud83d\udcca Ninguém pontuou hoje."
    ranking = sorted(pontuacao_diaria.items(), key=lambda x: x[1], reverse=True)
    texto = "\n\n\ud83c\udfc6 *Ranking Parcial:*\n"
    for i, (user, pontos) in enumerate(ranking, 1):
        texto += f"{i}. {user}: {pontos} ponto(s)\n"
    return texto

def enviar_balao_resposta(chat_id, palavra, acertos, erros):
    texto = f"\ud83d\udce2 *Fim da Rodada!*\n\n\u2705 Palavra: *{palavra.upper()}*\n"
    if acertos:
        texto += "\n\ud83d\udc51 Vencedores:\n"
        for nome, letras in acertos.items():
            pontos = pontuacao_diaria.get(nome, 0)
            texto += f"- {nome} (+1 ponto) — Letras: {', '.join(letras)} — Total: {pontos} ponto(s)\n"
    else:
        texto += "\n\ud83d\ude1e Ninguém acertou.\n"

    if erros:
        texto += "\n\u274c Tentativas Erradas:\n"
        for nome, letras in erros.items():
            texto += f"- {nome} — Letras erradas: {', '.join(letras)}\n"

    texto += gerar_ranking()
    enviar_mensagem(chat_id, texto)

def enviar_nova_pergunta(chat_id):
    apagar_mensagens(chat_id)
    palavra = escolher_palavra()
    if palavra == "erro":
        bot.send_message(chat_id, "Erro ao carregar palavras.")
        return

    letras_certas, letras_erradas = [], []
    tentativas, acertos, erros = {}, {}, {}
    rodada_ativa[chat_id] = True
    ultima_rodada[chat_id] = datetime.now()
    rodada_dados[chat_id] = {
        "palavra": palavra,
        "letras_certas": letras_certas,
        "letras_erradas": letras_erradas,
        "tentativas": tentativas,
        "acertos": acertos,
        "erros": erros
    }

    texto = f"\ud83c\udfaf *Novo Desafio!*\n\n\ud83d\udd20 Palavra: {formatar_palavra(palavra, letras_certas)}\n\ud83d\udce2 Dica: Palavra com {len(palavra)} letras.\n\nDigite uma letra ou a palavra."
    enviar_mensagem(chat_id, texto)

def processar_resposta(m):
    chat_id = m.chat.id
    if not rodada_ativa.get(chat_id):
        return
    dados = rodada_dados[chat_id]
    nome = m.from_user.first_name
    texto = m.text.strip().lower()

    if nome not in dados["tentativas"]:
        dados["tentativas"][nome] = 2
    if dados["tentativas"][nome] <= 0:
        return

    if texto == dados["palavra"]:
        dados["acertos"][nome] = list(set(dados["letras_certas"]))
        pontuacao_diaria[nome] = pontuacao_diaria.get(nome, 0) + 1
        dados["tentativas"][nome] = 0
    elif len(texto) == 1 and texto.isalpha():
        if texto in dados["palavra"]:
            dados["letras_certas"].append(texto)
            dados["acertos"].setdefault(nome, []).append(texto)
        else:
            dados["letras_erradas"].append(texto)
            dados["tentativas"][nome] -= 1
            dados["erros"].setdefault(nome, []).append(texto)

        palavra_atual = formatar_palavra(dados["palavra"], dados["letras_certas"])
        tent = dados["tentativas"][nome]
        emoji = "\u2705" if texto in dados["palavra"] else "\u274c"
        enviar_mensagem(chat_id, f"{emoji} {nome}: '{texto}'\n{palavra_atual}\n\u2764\ufe0f Tentativas restantes: {tent}")

# === COMANDO /forca ===
@bot.message_handler(commands=['forca'])
def handle_forca(message):
    chat_id = message.chat.id
    if GRUPOS_PERMITIDOS and chat_id not in GRUPOS_PERMITIDOS:
        return
    if datetime.now() - ultima_rodada.get(chat_id, datetime.min) < timedelta(seconds=TEMPO_ENTRE_RODADAS):
        bot.reply_to(message, f"\u23f3 Aguarde {TEMPO_ENTRE_RODADAS//60} minutos para novo desafio.")
        return
    enviar_nova_pergunta(chat_id)

# === COMANDO /start ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "\ud83d\udc4b Envie /forca para começar o desafio da forca!")

# === TODAS AS MENSAGENS ===
@bot.message_handler(func=lambda m: True)
def todas_respostas(m):
    processar_resposta(m)

# === RANKING DIÁRIO ===
def ranking_diario():
    while True:
        agora = datetime.now().strftime("%H:%M")
        if agora == HORARIO_RANKING_FINAL:
            for chat_id in rodada_ativa:
                enviar_mensagem(chat_id, "\ud83d\udcc6 *Ranking Final do Dia*\n" + gerar_ranking())
            pontuacao_diaria.clear()
        time.sleep(60)

threading.Thread(target=ranking_diario, daemon=True).start()

# === FLASK WEBHOOK PARA RENDER ===
app = Flask(__name__)

@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route("/")
def home():
    url = f"{RENDER_URL}/{API_TOKEN}"
    if bot.get_webhook_info().url != url:
        bot.remove_webhook()
        bot.set_webhook(url=url)
    return "Bot da Forca online!", 200

def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

if __name__ == "__main__":
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
