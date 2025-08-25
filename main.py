# ✅ BOT DA FORCA — VERSÃO COM REAÇÕES E INTERAÇÃO INTELIGENTE
# Desenvolvido para rodar no Render como Web Service (Flask)
# Palavras só são descobertas letra por letra. Sem tentar palavra inteira.

import os
import time
import json
import random
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request
import telebot

# ✅ CONFIGURAÇÕES
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ✅ PARÂMETROS DO JOGO
TEMPO_ENTRE_RODADAS = 300  # 5 minutos
HORARIO_RANKING_FINAL = "23:30"

# ✅ VARIÁVEIS DE CONTROLE
jogos_ativos = {}             # {chat_id: dados do jogo atual}
pontuacao_diaria = {}         # {nome: pontos}
historico_palavras = []       # palavras usadas recentemente
ultimas_mensagens = {}        # controle de mensagens por chat
baloes_para_apagar = {}  # {chat_id: [msg_id, msg_id...]}
ultimo_jogo_timestamp = {}  # {chat_id: datetime do último jogo}
INTERVALO_MIN_ENTRE_JOGOS = 300  # segundos (5 minutos). Altere se quiser

# ✅ FUNÇÕES DE SUPORTE

def carregar_palavras():
    try:
        with open("palavras.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def escolher_palavra():
    palavras = carregar_palavras()
    candidatas = list(set(tuple(p.items()) for p in palavras) - set(tuple(p.items()) for p in historico_palavras[-60:]))
    if not candidatas:
        historico_palavras.clear()
        candidatas = [tuple(p.items()) for p in palavras]
    escolha = random.choice(candidatas)
    escolha_dict = dict(escolha)
    historico_palavras.append(escolha_dict)
    return escolha_dict["palavra"].lower(), escolha_dict["dica"]

def formatar_palavra(palavra, certas):
    exibicao = ''
    for letra in palavra:
        if letra in certas:
            exibicao += f'{letra.upper()} '
        else:
            exibicao += '• '
    return exibicao.strip()

def gerar_ranking():
    if not pontuacao_diaria:
        return "📊 Ninguém pontuou hoje."
    ranking = sorted(pontuacao_diaria.items(), key=lambda x: x[1], reverse=True)
    texto = "\n\n🏆 *Ranking Parcial:*\n"
    for i, (nome, pontos) in enumerate(ranking, 1):
        texto += f"{i}. {nome}: {pontos} ponto(s)\n"
    return texto

def enviar_mensagem(chat_id, texto, markup=None):
    msg = bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=markup)
    ultimas_mensagens.setdefault(chat_id, []).append(msg.message_id)

    # Só salvar balões de atualização (não salvar se tiver botão, ou seja, se for balão final)
    if markup is None:
        baloes_para_apagar.setdefault(chat_id, []).append(msg.message_id)

def enviar_balao_atualizado(chat_id):
    jogo = jogos_ativos[chat_id]
    texto = f"🎯 *Desafio em Andamento!*\n\n"
    texto += f"🔠 Palavra:\n{formatar_palavra(jogo['palavra'], jogo['letras_certas'])}\n"
    texto += f"💡 Dica: {jogo['dica']}\n"
    texto += f"💣 Tentativas:\n"
    for nome, rest in jogo['tentativas'].items():
        texto += f"- {nome}: {rest} restantes\n"

    enviar_mensagem(chat_id, texto)

    # ✅ Apagar balões antigos após 1 segundo, sem travar o bot
    def apagar_depois():
        time.sleep(1)
        apagar_baloes_antigos(chat_id)

    threading.Thread(target=apagar_depois, daemon=True).start()

def apagar_baloes_antigos(chat_id, manter=1):
    ids = baloes_para_apagar.get(chat_id, [])
    apagar = ids[:-manter]
    for msg_id in apagar:
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
    baloes_para_apagar[chat_id] = ids[-manter:]

def finalizar_rodada(chat_id):
    jogo = jogos_ativos[chat_id]
    palavra = jogo['palavra']
    acertos = jogo['acertos']
    erros = jogo['erros']
    ranking = gerar_ranking()

    texto = f"📢 *Fim da Rodada!*\n\n✅ Palavra: *{palavra.upper()}*\n"

    if acertos:
        texto += "\n👑 Vencedores:\n"
        for nome, letras in acertos.items():
            pontos = pontuacao_diaria.get(nome, 0)
            texto += f"- {nome} (+1 ponto) — Letras: {', '.join(letras).upper()} — Total: {pontos + 0} ponto(s)\n"
    else:
        texto += "\n💔 Ninguém acertou letras.\n"

    if erros:
        texto += "\n❌ Erraram:\n"
        for nome, letras in erros.items():
            texto += f"- {nome} — Letras erradas: {', '.join(letras).upper()}\n"

    texto += ranking

    # Botão "Novo Desafio"
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔁 Novo Desafio", callback_data="novo_desafio"))

    enviar_mensagem(chat_id, texto, markup)
    del jogos_ativos[chat_id]

# ✅ INICIAR NOVO JOGO
def iniciar_rodada(chat_id):
    palavra, dica = escolher_palavra()
    dados = {
        "palavra": palavra,
        "dica": dica,
        "letras_certas": [],
        "letras_erradas": [],
        "tentativas": {},         # nome: tentativas restantes
        "acertos": {},            # nome: letras certas
        "erros": {},              # nome: letras erradas
        "inicio": datetime.now()
    }
    jogos_ativos[chat_id] = dados

    texto = f"🪢 *Jogo da Forca Iniciado!*\n\n"
    texto += f"🔠 Palavra:\n{formatar_palavra(palavra, [])}\n"
    texto += f"💡 Dica: {dica}\n"
    texto += f"🎯 Envie uma *letra* ou a *palavra inteira* para tentar!"
    ultimo_jogo_timestamp[chat_id] = datetime.now()

    enviar_mensagem(chat_id, texto)

    # ⏳ Thread que finaliza automaticamente após TEMPO_ENTRE_RODADAS
    def finalizar_depois():
        time.sleep(TEMPO_ENTRE_RODADAS)
        if chat_id in jogos_ativos:
            finalizar_rodada(chat_id)
    threading.Thread(target=finalizar_depois, daemon=True).start()

# ✅ RECEBE COMANDO /forca
@bot.message_handler(commands=["forca"])
def forca_handler(message):
    chat_id = message.chat.id

    agora = datetime.now()
    ultimo_jogo = ultimo_jogo_timestamp.get(chat_id)

    # Se já tem jogo em andamento, bloqueia
    if chat_id in jogos_ativos:
        bot.reply_to(message, "⚠️ Um jogo já está em andamento. Aguarde terminar.")
        return

    # Se tentou iniciar antes do tempo limite
    if ultimo_jogo and (agora - ultimo_jogo).total_seconds() < INTERVALO_MIN_ENTRE_JOGOS:
        minutos_restantes = int((INTERVALO_MIN_ENTRE_JOGOS - (agora - ultimo_jogo).total_seconds()) / 60)
        bot.reply_to(message, f"⏱️ Aguarde {minutos_restantes} minuto(s) para novo desafio ou finalize a rodada atual.")
        return

    iniciar_rodada(chat_id)

# ✅ TRATA LETRAS DIGITADAS
@bot.message_handler(func=lambda m: True)
def letras_handler(message):
    chat_id = message.chat.id
    if chat_id not in jogos_ativos:
        return

    texto = message.text.strip().lower()
    if not texto.isalpha():  # só aceita letras
        return

    nome = message.from_user.first_name
    jogo = jogos_ativos[chat_id]

    # Se o jogador ainda não tem tentativas, inicia com 3
    if nome not in jogo["tentativas"]:
        jogo["tentativas"][nome] = 3

    if jogo["tentativas"][nome] <= 0:
        bot.send_message(chat_id, f"❌ {nome}, você esgotou suas tentativas!")
        enviar_balao_atualizado(chat_id)
        return

    # ✅ Tentativa de PALAVRA inteira
    if len(texto) > 1:
        if texto == jogo["palavra"]:
            # Jogador acertou a palavra completa
            jogo["letras_certas"] = list(set(jogo["palavra"]))  # revela todas as letras
            jogo["acertos"].setdefault(nome, []).append(f"PALAVRA ({texto.upper()})")
            pontuacao_diaria[nome] = pontuacao_diaria.get(nome, 0) + 5  # vale mais pontos
            bot.send_message(chat_id, f"🏆 {nome} acertou a *PALAVRA INTEIRA*! +5 pontos 🎉")
            finalizar_rodada(chat_id)  # encerra rodada imediatamente
            return
        else:
            jogo["tentativas"][nome] -= 1
            jogo["erros"].setdefault(nome, []).append(f"PALAVRA ({texto.upper()})")
            bot.send_message(chat_id, f"💀 {nome} errou a palavra *{texto.upper()}*!")
            enviar_balao_atualizado(chat_id)
            if all(t <= 0 for t in jogo["tentativas"].values()):
                finalizar_rodada(chat_id)
            return

    # ✅ Tentativa de LETRA única
    letra = texto[0]

    # Já usada?
    if letra in jogo["letras_certas"] or letra in jogo["letras_erradas"]:
        bot.send_message(chat_id, f"⚠️ A letra *{letra.upper()}* já foi enviada.")
        return

    if letra in jogo["palavra"]:
        jogo["letras_certas"].append(letra)
        jogo["acertos"].setdefault(nome, []).append(letra)
        pontuacao_diaria[nome] = pontuacao_diaria.get(nome, 0) + 1
        bot.send_message(chat_id, f"✅ {nome} acertou a letra *{letra.upper()}*!")
    else:
        jogo["letras_erradas"].append(letra)
        jogo["tentativas"][nome] -= 1
        jogo["erros"].setdefault(nome, []).append(letra)
        bot.send_message(chat_id, f"❌ {nome} errou a letra *{letra.upper()}*!")

    enviar_balao_atualizado(chat_id)

    if all(t <= 0 for t in jogo["tentativas"].values()):
        finalizar_rodada(chat_id)

# ✅ BOTÃO DE NOVO DESAFIO
@bot.callback_query_handler(func=lambda call: call.data == "novo_desafio")
def callback_novo(call):
    chat_id = call.message.chat.id
    if chat_id in jogos_ativos:
        bot.answer_callback_query(call.id, "Jogo em andamento.")
        return
    iniciar_rodada(chat_id)
    bot.answer_callback_query(call.id, "Novo desafio iniciado!")

# ✅ COMANDO /start
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.reply_to(message, "👋 Envie /forca para começar o jogo da forca!")

# ✅ RANKING DIÁRIO ÀS 23H30
def ranking_diario():
    while True:
        agora = datetime.now().strftime("%H:%M")
        if agora == HORARIO_RANKING_FINAL:
            for chat_id in jogos_ativos.keys():
                texto = "📆 *Ranking Final do Dia*\n" + gerar_ranking()
                enviar_mensagem(chat_id, texto)
            pontuacao_diaria.clear()
        time.sleep(60)

threading.Thread(target=ranking_diario, daemon=True).start()

# ✅ WEBHOOK FLASK (para Render Web Service)
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
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

# ✅ INÍCIO
if __name__ == "__main__":
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
