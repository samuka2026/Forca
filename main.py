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
TEMPO_ENTRE_RODADAS = 600  # 10 minutos
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
    """
    Mostra a palavra com quadrados pretos.
    Letras acertadas substituem o quadrado.
    Hífens e espaços já aparecem.
    """
    exibicao = ''
    for letra in palavra:
        if letra == ' ':
            exibicao += '   '  # mantém espaço entre palavras
        elif letra == '-':
            exibicao += '- '   # já mostra hífen
        elif letra.lower() in certas:
            exibicao += f'{letra.upper()} '  # letra acertada
        else:
            exibicao += '⬛ '  # quadrado preto para letras não acertadas
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
    texto = f"🎯 *DESAFIO EM ANDAMENTO!*\n\n"
    texto += f"🔠 *PALAVRA:*\n{formatar_palavra(jogo['palavra'], jogo['letras_certas'])}\n\n"
    texto += f"💡 *DICA:* {jogo['dica'].upper()}\n\n"
    texto += "💣 *TENTATIVAS RESTANTES:*\n"
    for nome, rest in jogo['tentativas'].items():
        texto += f"👤 {nome}: {rest} tentativa(s)\n"

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

    # cancela o timer se ainda existir
    if jogo.get("timer"):
        jogo["timer"].cancel()

    palavra = jogo["palavra"]
    dica = jogo["dica"]

    texto = f"🏁 *Fim da Rodada!*\n\n"
    texto += f"✅ Palavra correta: *{palavra}*\n"
    texto += f"💡 Dica: {dica}\n\n"

    if jogo["acertos"]:
        texto += "🏆 Pontuação:\n"
        for nome, pontos in jogo["acertos"].items():
            texto += f"⭐ {nome}: {pontos} ponto(s)\n"
    else:
        texto += "⚠️ Ninguém acertou nesta rodada.\n"

    botoes = {
        "inline_keyboard": [
            [{"text": "🔁 Novo Desafio", "callback_data": "novo_desafio"}]
        ]
    }

    enviar_mensagem(chat_id, texto, botoes)

    # remove o jogo da memória
    del jogos_ativos[chat_id]

def iniciar_rodada(chat_id):
    palavra, dica = escolher_palavra()
    dados = {
        "palavra": palavra,
        "dica": dica,
        "letras_certas": [],
        "letras_erradas": [],
        "tentativas": {},
        "acertos": {},
        "erros": {},
        "inicio": datetime.now(),
        "timer": None  # 🔴 espaço para salvar o Timer
    }

    # se já existe jogo ativo, cancela o timer antigo
    if chat_id in jogos_ativos and jogos_ativos[chat_id].get("timer"):
        jogos_ativos[chat_id]["timer"].cancel()

    jogos_ativos[chat_id] = dados

    texto = f"🪢 *Jogo da Forca Iniciado!*\n\n"
    texto += f"🔠 Palavra:\n{formatar_palavra(palavra, [])}\n"
    texto += f"💡 Dica: {dica}\n"
    texto += f"🎯 Envie uma *letra* ou a *palavra inteira* para tentar!"
    ultimo_jogo_timestamp[chat_id] = datetime.now()
    enviar_mensagem(chat_id, texto)

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

@bot.message_handler(func=lambda m: True, content_types=["text"])
def letras_handler(message):
    chat_id = message.chat.id
    texto = message.text.strip()
    
    # 🔹 Se não houver jogo ativo, ignora
    if chat_id not in jogos_ativos:
        return

    jogo = jogos_ativos[chat_id]
    jogador = message.from_user.first_name

    # 🔹 Inicializa tentativas do jogador se não existir
    if jogador not in jogo["tentativas"]:
        jogo["tentativas"][jogador] = 6  # define número de tentativas

    # 🔹 Encerramento manual
    if texto.lower() == "//forca":
        finalizar_rodada(chat_id)
        enviar_mensagem(chat_id, "⏹️ O jogo foi encerrado manualmente pelo administrador.")
        return

    # 🔹 Tentativa de palavra inteira (/ ou !)
    if texto.startswith("/") or texto.startswith("!"):
        tentativa_palavra = texto[1:].lower()
        if tentativa_palavra == jogo["palavra"]:
            enviar_mensagem(chat_id, f"🎉 {jogador} acertou a palavra inteira!")
            jogo["acertos"][jogador] = jogo["acertos"].get(jogador, 0) + 3
            pontuacao_diaria[jogador] = pontuacao_diaria.get(jogador, 0) + 3
            finalizar_rodada(chat_id)
        else:
            enviar_mensagem(chat_id, f"❌ {jogador} tentou a palavra '{tentativa_palavra}' e errou.")
            jogo["tentativas"][jogador] -= 1
        enviar_balao_atualizado(chat_id)
        return

    # 🔹 Tentativa de letra
    if len(texto) == 1 and texto.isalpha():
        letra = texto.lower()

        if letra in jogo["palavra"]:
            if letra not in jogo["letras_certas"]:
                jogo["letras_certas"].append(letra)
                enviar_mensagem(chat_id, f"✅ A letra '{letra.upper()}' está na palavra!")
                jogo["acertos"][jogador] = jogo["acertos"].get(jogador, 0) + 1
                pontuacao_diaria[jogador] = pontuacao_diaria.get(jogador, 0) + 1
            else:
                enviar_mensagem(chat_id, f"⚠️ A letra '{letra.upper()}' já foi escolhida.")
        else:
            if letra not in jogo["letras_erradas"]:
                jogo["letras_erradas"].append(letra)
                enviar_mensagem(chat_id, f"❌ A letra '{letra.upper()}' não está na palavra.")
                jogo["tentativas"][jogador] -= 1

        enviar_balao_atualizado(chat_id)

        # 🔹 Checa se todas as letras foram descobertas
        if all(l in jogo["letras_certas"] for l in jogo["palavra"] if l.isalpha()):
            enviar_mensagem(chat_id, f"🎉 Todas as letras foram descobertas! {jogador} concluiu a palavra!")
            finalizar_rodada(chat_id)
        return

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
