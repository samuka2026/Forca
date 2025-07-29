import telebot
import json
import random
import time
import threading
from datetime import datetime, timedelta

API_TOKEN = '8482676317:AAG66DWO5QItfX4DgwBOdX5lEB0AGMIs2Kg'
bot = telebot.TeleBot(API_TOKEN)

# === CONFIGURAÇÕES ===
TEMPO_ENTRE_RODADAS = 600  # 10 minutos em segundos
HORARIO_RANKING_FINAL = "23:30"

# === VARIÁVEIS DE CONTROLE ===
usuarios_jogo = {}
pontuacao_diaria = {}
historico_palavras = []
mensagens_anteriores = []
ultima_rodada = datetime.now() - timedelta(seconds=TEMPO_ENTRE_RODADAS)

# === FUNÇÕES UTILITÁRIAS ===
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
    palavra = random.choice(candidatas)
    historico_palavras.append(palavra)
    return palavra.lower()

def formatar_palavra(palavra, certas):
    return ' '.join([letra if letra in certas else '_' for letra in palavra])

def resetar_jogo():
    global usuarios_jogo
    usuarios_jogo = {}

def enviar_mensagem(chat_id, texto):
    msg = bot.send_message(chat_id, texto)
    mensagens_anteriores.append(msg.message_id)

def apagar_mensagens(chat_id):
    for msg_id in mensagens_anteriores[:-2]:
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
    del mensagens_anteriores[:-2]

def gerar_ranking():
    if not pontuacao_diaria:
        return "📊 Ninguém pontuou hoje."
    ranking = sorted(pontuacao_diaria.items(), key=lambda x: x[1], reverse=True)
    texto = "\n\n🏆 *Ranking Parcial:*\n"
    for i, (user, pontos) in enumerate(ranking, 1):
        texto += f"{i}. {user}: {pontos} ponto(s)\n"
    return texto

def enviar_balao_resposta(chat_id, palavra, acertos, erros):
    vencedores = list(acertos.keys())
    texto = f"📢 *Fim da Rodada!*\n\n✅ Palavra: *{palavra.upper()}*\n"

    if vencedores:
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

def enviar_nova_pergunta(chat_id):
    global ultima_rodada
    apagar_mensagens(chat_id)

    palavra = escolher_palavra()
    letras_certas = []
    letras_erradas = []
    tentativas = {}
    resposta_correta = palavra
    acertos = {}
    erros = {}

    texto = f"🎯 *Novo Desafio!*\n\n🔠 Palavra: {formatar_palavra(palavra, letras_certas)}\n📢 Dica: Palavra com {len(palavra)} letras.\n\nDigite uma letra ou a palavra.\n\n💬 Novo desafio!"
    enviar_mensagem(chat_id, texto)

    def rodada():
        nonlocal letras_certas, letras_erradas
        tempo_inicio = time.time()
        fim = False

        while not fim:
            if time.time() - tempo_inicio > TEMPO_ENTRE_RODADAS:
                fim = True
                break
            time.sleep(1)

        enviar_balao_resposta(chat_id, resposta_correta, acertos, erros)
        time.sleep(30)
        enviar_nova_pergunta(chat_id)

    def processar_resposta(m):
        if m.chat.id != chat_id:
            return

        nome = m.from_user.first_name
        texto = m.text.strip().lower()
        if nome not in tentativas:
            tentativas[nome] = 2

        if tentativas[nome] <= 0:
            return

        if texto == resposta_correta:
            acertos[nome] = list(set(letras_certas))
            pontuacao_diaria[nome] = pontuacao_diaria.get(nome, 0) + 1
            tentativas[nome] = 0
        elif len(texto) == 1 and texto.isalpha():
            if texto in resposta_correta:
                letras_certas.append(texto)
                if nome not in acertos:
                    acertos[nome] = []
                acertos[nome].append(texto)
            else:
                letras_erradas.append(texto)
                tentativas[nome] -= 1
                if nome not in erros:
                    erros[nome] = []
                erros[nome].append(texto)

            palavra_atual = formatar_palavra(resposta_correta, letras_certas)
            tent = tentativas[nome]
            emoji = "✅" if texto in resposta_correta else "❌"
            resposta = f"{emoji} {nome}: '{texto}'\n{palavra_atual}\n❤️ Tentativas restantes: {tent}"
            enviar_mensagem(chat_id, resposta)

    bot.register_next_step_handler_by_chat_id(chat_id, processar_resposta)
    threading.Thread(target=rodada).start()
    ultima_rodada = datetime.now()

# === COMANDO /forca ===
@bot.message_handler(commands=['forca'])
def handle_forca(message):
    if datetime.now() - ultima_rodada < timedelta(seconds=TEMPO_ENTRE_RODADAS):
        bot.reply_to(message, f"⏳ Aguarde {TEMPO_ENTRE_RODADAS//60} minutos para novo desafio.")
        return
    enviar_nova_pergunta(message.chat.id)

# === COMANDO /start ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "👋 Envie /forca para começar o desafio da forca!")

# === RANKING DIÁRIO AUTOMÁTICO ===
def ranking_diario():
    while True:
        agora = datetime.now().strftime("%H:%M")
        if agora == HORARIO_RANKING_FINAL:
            for chat_id in GRUPOS_PERMITIDOS:
                texto = "📆 *Ranking Final do Dia*\n" + gerar_ranking()
                enviar_mensagem(chat_id, texto)
            pontuacao_diaria.clear()
        time.sleep(60)

threading.Thread(target=ranking_diario, daemon=True).start()

# ✅ Integração com Flask para Render Web Service
from flask import Flask, request

app = Flask(__name__)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

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

# ✅ Mantém o bot vivo no Render
def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)  # A cada 10 minutos

# ✅ Início da aplicação no Render
if __name__ == "__main__":
    import threading
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
