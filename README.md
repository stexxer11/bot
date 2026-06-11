# Rifa WhatsApp + Twilio + Groq + Railway

## Variables en Railway

Agrega estas variables en Railway > Variables:

```env
GROQ_API_KEY=tu_key_de_groq
GROQ_MODEL=llama-3.3-70b-versatile
PUBLIC_URL=https://tu-app.up.railway.app
PRECIO=1.50
DB_PATH=rifa.db
```

Cuando Railway genere tu dominio publico, copia ese dominio en `PUBLIC_URL`.

## Webhook de Twilio WhatsApp

En Twilio, configura:

```txt
https://tu-app.up.railway.app/whatsapp
```

Metodo: `POST`

## Probar local

```bash
pip install -r requirements.txt
python app.py
```

Abre:

```txt
http://localhost:5000
```

## Rutas

- `/` panel de rifa
- `/rifa.png` imagen actual
- `/whatsapp` webhook Twilio
- `/health` prueba de vida
