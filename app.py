import os
import re
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, send_file, render_template_string
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

DB = os.getenv("DB_PATH", "rifa.db")
PRECIO = float(os.getenv("PRECIO", "1.50"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

app = Flask(__name__)
client_groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def preguntar_groq(mensaje):
    if not client_groq:
        return "La IA no está configurada todavía. Escribe *menu* para ver la rifa."

    try:
        respuesta = client_groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
              {
    "role": "system",
    "content": """
Eres SOFIA, la asistente oficial de ventas de SÚPER RIFA.

Tu misión principal es ayudar al cliente, responder preguntas y motivarlo de forma natural a participar en la rifa.

PERSONALIDAD:
- Muy amable.
- Cercana y profesional.
- Hablas español neutro.
- Nunca eres fría ni robótica.
- Siempre saludas con energía positiva.
- Generas confianza.

INFORMACIÓN DE LA RIFA:
- Nombre: SÚPER RIFA.
- Precio por boleto: $1.50.
- Premio principal: una cacerola de 20cm.
- Los números disponibles solo pueden verse mediante el sistema escribiendo MENU o VER RIFA.

REGLAS IMPORTANTES:
- Nunca inventes números disponibles.
- Nunca inventes compras realizadas.
- Nunca confirmes pagos.
- Nunca reserves números por tu cuenta.
- Para comprar siempre dirige al usuario al proceso oficial.

COMPORTAMIENTO:
- Saluda cálidamente.
- Responde preguntas sobre la rifa.
- Motiva a participar sin presionar.
- Si pregunta cómo comprar, indícale que escriba MENU.
- Si pregunta por números disponibles, indícale que escriba VER RIFA.
- Si conversa de otros temas, responde brevemente y vuelve a la rifa.

ESTILO:
- Usa emojis moderadamente.
- Máximo 4 líneas por respuesta.
- Sé persuasiva sin presionar.
- Haz sentir al cliente bien atendido.
- Mantén la conversación natural y humana.
"""
},
                {"role": "user", "content": mensaje}
            ],
            temperature=0.4,
            max_tokens=250
        )
        return respuesta.choices[0].message.content.strip()
    except Exception:
        return "Ahora mismo la IA no pudo responder. Escribe *menu* para ver la rifa."


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS numeros (
        numero TEXT PRIMARY KEY,
        estado TEXT DEFAULT 'libre',
        cliente TEXT DEFAULT '',
        telefono TEXT DEFAULT '',
        fecha TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sesiones (
        telefono TEXT PRIMARY KEY,
        paso TEXT DEFAULT 'inicio',
        cantidad INTEGER DEFAULT 0,
        seleccion TEXT DEFAULT ''
    )
    """)

    for i in range(100):
        n = f"{i:02d}"
        cur.execute("INSERT OR IGNORE INTO numeros(numero, estado) VALUES(?, 'libre')", (n,))

    con.commit()
    con.close()


def get_numeros():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT numero, estado FROM numeros ORDER BY numero")
    data = cur.fetchall()
    con.close()
    return data


def disponibles():
    return [n for n, e in get_numeros() if e == "libre"]


def vendidos():
    return [n for n, e in get_numeros() if e == "vendido"]


def get_sesion(telefono):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT paso, cantidad, seleccion FROM sesiones WHERE telefono=?", (telefono,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO sesiones(telefono, paso, cantidad, seleccion) VALUES(?, 'inicio', 0, '')",
            (telefono,)
        )
        con.commit()
        row = ("inicio", 0, "")

    con.close()
    return {"paso": row[0], "cantidad": row[1], "seleccion": row[2]}


def set_sesion(telefono, paso, cantidad=0, seleccion=""):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sesiones(telefono, paso, cantidad, seleccion)
        VALUES(?, ?, ?, ?)
    """, (telefono, paso, cantidad, seleccion))
    con.commit()
    con.close()


def marcar_vendidos(numeros, telefono):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for n in numeros:
        cur.execute("""
            UPDATE numeros
            SET estado='vendido', telefono=?, fecha=?
            WHERE numero=? AND estado='libre'
        """, (telefono, fecha, n))

    con.commit()
    con.close()


def extraer_numeros(texto):
    encontrados = re.findall(r"\b\d{1,2}\b", texto)
    return [f"{int(n):02d}" for n in encontrados if 0 <= int(n) <= 99]


def extraer_cantidad(texto):
    texto = texto.lower()
    numeros = re.findall(r"\b\d{1,2}\b", texto)
    if numeros:
        return int(numeros[0])

    palabras = {
        "uno": 1, "una": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10
    }

    for palabra, valor in palabras.items():
        if palabra in texto:
            return valor

    return 0


def generar_imagen():
    W, H = 900, 1500
    img = Image.new("RGB", (W, H), "#f7eeee")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arialbd.ttf", 92)
        font_sub = ImageFont.truetype("ariali.ttf", 44)
        font_price = ImageFont.truetype("ariali.ttf", 36)
        font_num = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_price = ImageFont.load_default()
        font_num = ImageFont.load_default()

    draw.text((W // 2, 170), "SÚPER", anchor="mm", fill="#333333", font=font_title)
    draw.text((W // 2, 270), "RIFA", anchor="mm", fill="#333333", font=font_title)
    draw.text((W // 2, 385), "¡Gánate una cacerola de 20cm!", anchor="mm", fill="#222222", font=font_sub)
    draw.text((W // 2, 455), f"Número: ${PRECIO:.2f}", anchor="mm", fill="#222222", font=font_price)

    nums = dict(get_numeros())
    grid_x = 140
    grid_y = 570
    cell = 62

    for fila in range(10):
        for col in range(10):
            n = f"{fila * 10 + col:02d}"
            x1 = grid_x + col * cell
            y1 = grid_y + fila * cell
            x2 = x1 + cell
            y2 = y1 + cell

            draw.rectangle((x1, y1, x2, y2), outline="#d7cfcf", width=2)
            draw.text((x1 + cell / 2, y1 + cell / 2), n, anchor="mm", fill="#111111", font=font_num)

            if nums.get(n) == "vendido":
                draw.line((x1 + 10, y1 + 10, x2 - 10, y2 - 10), fill="#c00000", width=5)
                draw.line((x2 - 10, y1 + 10, x1 + 10, y2 - 10), fill="#c00000", width=5)

    path = "rifa_actual.png"
    img.save(path)
    return path


def media_url(path):
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/{path.lstrip('/')}"
    return f"/{path.lstrip('/')}"


def mensaje_menu(libres):
    return (
        "🎟️ *SÚPER RIFA*\n\n"
        f"Cada boleto cuesta *${PRECIO:.2f}*.\n"
        f"Hay *{len(libres)}* números disponibles.\n\n"
        "Elige una opción:\n\n"
        "1️⃣ Comprar 1 boleto\n"
        "2️⃣ Comprar 2 boletos\n"
        "3️⃣ Comprar 3 boletos\n"
        "4️⃣ Ingresar otra cantidad\n\n"
        "También puedes escribir:\n"
        "• *ver rifa*\n"
        "• *comprar más*\n"
        "• *cancelar*"
    )


@app.route("/health")
def health():
    return {"ok": True, "service": "rifa-whatsapp-groq"}


@app.route("/rifa.png")
def rifa_png():
    path = generar_imagen()
    return send_file(path, mimetype="image/png")


@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.values.get("Body", "").strip()
    telefono = request.values.get("From", "")
    sesion = get_sesion(telefono)
    texto_l = msg.lower().strip()

    resp = MessagingResponse()
    m = resp.message()
    libres = disponibles()

    if texto_l in ["menu", "hola", "buenas", "inicio", "empezar"]:
        set_sesion(telefono, "inicio", 0, "")
        m.body(mensaje_menu(libres))
        m.media(media_url("rifa.png"))
        return str(resp)

    if "ver rifa" in texto_l or "rifa actual" in texto_l:
        m.body(f"Esta es la rifa actual. Hay {len(libres)} números disponibles.")
        m.media(media_url("rifa.png"))
        return str(resp)

    if "comprar mas" in texto_l or "comprar más" in texto_l or "otra compra" in texto_l:
        set_sesion(telefono, "inicio", 0, "")
        m.body("Perfecto, vamos a comprar más boletos.\n\n" + mensaje_menu(libres))
        m.media(media_url("rifa.png"))
        return str(resp)

    if "cancel" in texto_l or "anular" in texto_l:
        set_sesion(telefono, "inicio", 0, "")
        m.body("Listo, cancelé la selección temporal.\n\n" + mensaje_menu(libres))
        return str(resp)

    if "confirm" in texto_l or "acepto" in texto_l or texto_l in ["si", "sí", "ok", "dale"]:
        seleccion = sesion["seleccion"].split(",") if sesion["seleccion"] else []

        if not seleccion:
            m.body("No tienes números pendientes por confirmar.\n\n" + mensaje_menu(libres))
            m.media(media_url("rifa.png"))
            return str(resp)

        ocupados = [n for n in seleccion if n not in libres]
        if ocupados:
            validos = [n for n in seleccion if n in libres]
            set_sesion(telefono, "esperando_numeros", sesion["cantidad"], ",".join(validos))
            m.body(
                f"Lo siento, estos números ya no están disponibles: {', '.join(ocupados)}.\n\n"
                f"Tu selección válida actual: {', '.join(validos) if validos else 'ninguna'}\n"
                "Elige otros números disponibles."
            )
            m.media(media_url("rifa.png"))
            return str(resp)

        marcar_vendidos(seleccion, telefono)
        set_sesion(telefono, "inicio", 0, "")
        total = len(seleccion) * PRECIO
        m.body(
            f"✅ Listo. Tus números quedaron registrados:\n"
            f"{', '.join(seleccion)}\n\n"
            f"Total: ${total:.2f}\n\n"
            "Te envío la rifa actualizada.\n\n"
            "Si quieres comprar de nuevo, escribe *comprar más*."
        )
        m.media(media_url("rifa.png"))
        return str(resp)

    if sesion["paso"] == "inicio":
        if texto_l in ["1", "1 boleto", "uno", "un boleto"]:
            cantidad = 1
        elif texto_l in ["2", "2 boletos", "dos"]:
            cantidad = 2
        elif texto_l in ["3", "3 boletos", "tres"]:
            cantidad = 3
        elif texto_l in ["4", "otra", "otra cantidad", "ingresar otra cantidad"]:
            set_sesion(telefono, "esperando_otra_cantidad", 0, "")
            m.body("¿Cuántos boletos deseas comprar? Escribe solo el número. Ejemplo: 5")
            return str(resp)
        else:
            if "boleto" in texto_l or "boletos" in texto_l:
                cantidad = extraer_cantidad(msg)
            else:
                cantidad = 0

        if cantidad > 0:
            if cantidad > len(libres):
                m.body(f"Solo quedan {len(libres)} números disponibles. Ingresa una cantidad menor.")
                return str(resp)

            set_sesion(telefono, "esperando_numeros", cantidad, "")
            m.body(
                f"Perfecto. Elegiste comprar *{cantidad}* boleto(s).\n"
                f"Cada boleto cuesta ${PRECIO:.2f}.\n"
                f"Total estimado: ${cantidad * PRECIO:.2f}\n\n"
                f"Ahora envía {cantidad} número(s) disponibles del 00 al 99.\n\n"
                "Ejemplo: 05, 18, 44\n\n"
                f"Números disponibles:\n{', '.join(libres)}"
            )
            m.media(media_url("rifa.png"))
            return str(resp)

    if sesion["paso"] == "esperando_otra_cantidad":
        cantidad = extraer_cantidad(msg)
        if cantidad <= 0:
            m.body("No entendí la cantidad. Escribe solo un número. Ejemplo: 5")
            return str(resp)

        if cantidad > len(libres):
            m.body(f"Solo quedan {len(libres)} números disponibles. Ingresa una cantidad menor.")
            return str(resp)

        set_sesion(telefono, "esperando_numeros", cantidad, "")
        m.body(
            f"Perfecto. Elegiste comprar *{cantidad}* boleto(s).\n"
            f"Total estimado: ${cantidad * PRECIO:.2f}\n\n"
            f"Ahora envía {cantidad} número(s) disponibles del 00 al 99.\n\n"
            "Ejemplo: 05, 18, 44\n\n"
            f"Números disponibles:\n{', '.join(libres)}"
        )
        m.media(media_url("rifa.png"))
        return str(resp)

    nums = extraer_numeros(msg)
    if nums:
        nuevos_numeros = nums
        cantidad = sesion["cantidad"]
        if cantidad <= 0:
            cantidad = len(nuevos_numeros)

        anteriores = []
        if sesion["seleccion"]:
            anteriores = [n for n in sesion["seleccion"].split(",") if n]

        numeros = anteriores + nuevos_numeros
        repetidos = sorted(set([n for n in numeros if numeros.count(n) > 1]))
        if repetidos:
            m.body(
                f"Repetiste estos números: {', '.join(repetidos)}.\n"
                f"Selección actual: {', '.join(anteriores) if anteriores else 'ninguna'}\n\n"
                "Envíalos de nuevo sin repetir."
            )
            return str(resp)

        numeros = list(dict.fromkeys(numeros))
        no_disponibles = [n for n in numeros if n not in libres]
        if no_disponibles:
            validos = [n for n in numeros if n in libres]
            set_sesion(telefono, "esperando_numeros", cantidad, ",".join(validos))
            m.body(
                f"Estos números no están disponibles: {', '.join(no_disponibles)}.\n\n"
                f"Selección válida actual: {', '.join(validos) if validos else 'ninguna'}\n\n"
                f"Disponibles:\n{', '.join(libres)}"
            )
            m.media(media_url("rifa.png"))
            return str(resp)

        if len(numeros) < cantidad:
            faltan = cantidad - len(numeros)
            set_sesion(telefono, "esperando_numeros", cantidad, ",".join(numeros))
            m.body(f"Selección actual: {', '.join(numeros)}\n\nTe falta elegir {faltan} número(s) más.")
            return str(resp)

        if len(numeros) > cantidad:
            sobran = len(numeros) - cantidad
            m.body(
                f"Elegiste {sobran} número(s) de más.\n"
                f"Debes elegir exactamente {cantidad}.\n\n"
                f"Selección actual: {', '.join(numeros)}"
            )
            return str(resp)

        seleccion = ",".join(numeros)
        set_sesion(telefono, "confirmar", cantidad, seleccion)
        total = cantidad * PRECIO
        m.body(
            "🧾 *Confirmar selección*\n\n"
            f"Números: {', '.join(numeros)}\n"
            f"Cantidad: {cantidad}\n"
            f"Total: ${total:.2f}\n\n"
            "Responde *CONFIRMAR* para apartarlos.\n"
            "Si te equivocaste, escribe *cancelar* o *comprar más*."
        )
        return str(resp)

    respuesta_ia = preguntar_groq(msg)
    m.body(respuesta_ia + "\n\nPara ver la rifa o comprar boletos, escribe *menu*.")
    return str(resp)


@app.route("/")
def admin():
    nums = get_numeros()
    html = """
    <html>
    <head>
        <title>Panel Rifa</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; background: #111; color: white; padding: 24px; }
            .grid { display: grid; grid-template-columns: repeat(10, minmax(42px, 70px)); gap: 8px; }
            .num { height: 55px; border-radius: 10px; border: none; font-size: 20px; cursor: pointer; }
            .libre { background: #f4f4f4; color: #111; }
            .vendido { background: #c00000; color: white; text-decoration: line-through; }
            img { width: 360px; max-width: 100%; border-radius: 16px; }
            .wrap { display: flex; align-items: flex-start; gap: 30px; flex-wrap: wrap; }
            a { color: #00e0ff; }
            .box { background: #1d1d1d; padding: 16px; border-radius: 16px; }
        </style>
    </head>
    <body>
        <h1>Panel de Rifa</h1>
        <p>Boleto: ${{precio}}</p>
        <p>Webhook Twilio: <b>/whatsapp</b></p>
        <p><a href="/rifa.png" target="_blank">Ver imagen actual</a></p>
        <div class="wrap">
            <div class="box">
                <div class="grid">
                    {% for n, e in nums %}
                        <form method="post" action="/toggle">
                            <input type="hidden" name="numero" value="{{n}}">
                            <button class="num {{e}}">{{n}}</button>
                        </form>
                    {% endfor %}
                </div>
            </div>
            <div class="box"><img src="/rifa.png"></div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, nums=nums, precio=f"{PRECIO:.2f}")


@app.route("/toggle", methods=["POST"])
def toggle():
    n = request.form.get("numero")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT estado FROM numeros WHERE numero=?", (n,))
    row = cur.fetchone()
    if not row:
        con.close()
        return admin()

    nuevo = "libre" if row[0] == "vendido" else "vendido"
    cur.execute("UPDATE numeros SET estado=? WHERE numero=?", (nuevo, n))
    con.commit()
    con.close()
    generar_imagen()
    return admin()


init_db()

if __name__ == "__main__":
    generar_imagen()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
