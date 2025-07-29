# ✅ BOT DA FORCA - RODANDO EM RENDER COM FLASK E WEBHOOK
# Funções: Jogo da Forca, ranking diário às 23h30, rodadas automáticas, sem repetir palavras por 3 dias

import telebot
import json
import random
import time
import threading
import os
from datetime import datetime, timedelta
from flask import Flask, request

# ✅ Configurações do bot e ambiente
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ✅ Parâmetros da lógica do jogo
TEMPO_ENTRE_RODADAS = 10  # 10 minutos = 600 segundos
HORARIO_RANKING_FINAL = "23:30"
GRUPOS_PERMITIDOS = []  # Deixe vazio para permitir em todos os grupos

# ✅ Variáveis globais de controle
usuarios_jogo = {}
pontuacao_diaria = {}
historico_palavras = []
mensagens_anteriores = {}
ultima_rodada = {}
rodada_ativa = {}
rodada_dados = {}

# ✅ Função para carregar palavras do arquivo .json
def carregar_palavras():
    try:
        with open("palavras.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

# ✅ Escolhe uma nova palavra, evitando repetições recentes
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

# ✅ Formata a palavra com _ e letras reveladas
def formatar_palavra(palavra, certas):
    return ' '.join([letra if letra in certas else '_' for letra in palavra])

# ✅ Envia mensagem e armazena o ID para limpar depois
def enviar_mensagem(chat_id, texto):
    msg = bot.send_message(chat_id, texto, parse_mode="Markdown")
    mensagens_anteriores.setdefault(chat_id, []).append(msg.message_id)

# ✅ Apaga mensagens antigas, mantendo apenas os 2 últimos balões
def apagar_mensagens(chat_id):
    msgs = mensagens_anteriores.get(chat_id, [])
    for msg_id in msgs[:-2]:
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
    mensagens_anteriores[chat_id] = msgs[-2:]

# ✅ Gera o ranking parcial ou final
def gerar_ranking():
    if not pontuacao_diaria:
        return "📊 Ninguém pontuou hoje."
    ranking = sorted(pontuacao_diaria.items(), key=lambda x: x[1], reverse=True)
    texto = "\n\n🏆 *Ranking Parcial:*\n"
    for i, (user, pontos) in enumerate(ranking, 1):
        texto += f"{i}. {user}: {pontos} ponto(s)\n"
    return texto

# ✅ Envia balão com resumo da rodada e ranking
def enviar_balao_resposta(chat_id, palavra, acertos, erros):
    texto = f"📢 *Fim da Rodada!*\n\n✅ Palavra: *{palavra.upper()}*\n"
    if acertos:
        texto += "\n👑 Vencedores:\n"
        for nome, letras in acertos.items():
            pontos = pontuacao_diaria.get(nome, 0)
            texto += f"- {nome} (+1 ponto) — Letras: {', '.join(letras)} — Total: {pontos} ponto(s)\n"
    else:
        texto += "\n😢 Ninguém acertou.\n"

    if erros:
        texto += "\n❌ Tentativas Erradas:\n"
        for nome, letras in erros.items():
            texto += f"- {nome} — Letras erradas: {', '.join(letras)}\n"

    texto += gerar_ranking()
    enviar_mensagem(chat_id, texto)

# ✅ Inicia nova pergunta e configura dados da rodada
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

    texto = f"🎯 *Novo Desafio!*\n\n🔠 Palavra: {formatar_palavra(palavra, letras_certas)}\n📢 Dica: Palavra com {len(palavra)} letras.\n\nDigite uma letra ou a palavra."
    enviar_mensagem(chat_id, texto)

# ✅ Executa a rodada com temporizador e repete após 30s
def iniciar_rodada(chat_id):
    def rodada():
        time.sleep(TEMPO_ENTRE_RODADAS)
        dados = rodada_dados.get(chat_id, {})
        if not dados:
            return
        palavra = dados.get("palavra")
        acertos = dados.get("acertos", {})
        erros = dados.get("erros", {})
        enviar_balao_resposta(chat_id, palavra, acertos, erros)
        rodada_ativa[chat_id] = False
        time.sleep(30)
        enviar_nova_pergunta(chat_id)
        iniciar_rodada(chat_id)
    threading.Thread(target=rodada).start()

# ✅ Processa todas as mensagens do grupo
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
        emoji = "✅" if texto in dados["palavra"] else "❌"
        enviar_mensagem(chat_id, f"{emoji} {nome}: '{texto}'\n{palavra_atual}\n❤️ Tentativas restantes: {tent}")

# ✅ Comando /forca
@bot.message_handler(commands=['forca'])
def handle_forca(message):
    chat_id = message.chat.id
    if GRUPOS_PERMITIDOS and chat_id not in GRUPOS_PERMITIDOS:
        return
    if datetime.now() - ultima_rodada.get(chat_id, datetime.min) < timedelta(seconds=TEMPO_ENTRE_RODADAS):
        bot.reply_to(message, f"⏳ Aguarde {TEMPO_ENTRE_RODADAS//60} minutos para novo desafio.")
        return
    enviar_nova_pergunta(chat_id)
    iniciar_rodada(chat_id)

# ✅ Comando /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "👋 Envie /forca para começar o desafio da forca!")

# ✅ Captura todas as mensagens para tratar como resposta
@bot.message_handler(func=lambda m: True)
def todas_respostas(m):
    processar_resposta(m)

# ✅ Ranking diário às 23:30
def ranking_diario():
    while True:
        agora = datetime.now().strftime("%H:%M")
        if agora == HORARIO_RANKING_FINAL:
            for chat_id in rodada_ativa:
                enviar_mensagem(chat_id, "📆 *Ranking Final do Dia*\n" + gerar_ranking())
            pontuacao_diaria.clear()
        time.sleep(60)

threading.Thread(target=ranking_diario, daemon=True).start()

# ✅ ROTA FLASK PARA WEBHOOK (Render)
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

# ✅ Mantém o bot acordado no Render (ping a cada 10 minutos)
def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

# ✅ Inicializa o servidor Flask (Render Web Service)
if __name__ == "__main__":
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
