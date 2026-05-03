import os
import io
import time
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from database import Base, engine, SessionLocal
from models import Campaign, SmsMessage

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nuxway SMS Platform")

API_KEY = os.getenv("API_KEY", "change-me")
COUNTRY_CODE = os.getenv("COUNTRY_CODE", "591")

agent_status = {}

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


def normalize_phone(phone: str) -> str:
    phone = str(phone).strip()
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    if phone.endswith(".0"):
        phone = phone[:-2]

    if phone.startswith("+"):
        return phone

    if phone.startswith(COUNTRY_CODE):
        return "+" + phone

    return "+" + COUNTRY_CODE + phone


def parse_chips(chips_raw: str):
    chips = []
    for item in chips_raw.split(","):
        item = item.strip()
        if not item:
            continue

        chip = int(item)

        if chip < 1 or chip > 16:
            raise ValueError("Chip fuera de rango. Use 1 a 16.")

        chips.append(chip)

    if not chips:
        raise ValueError("Debe elegir al menos un chip.")

    return chips


def read_phones_from_excel(upload: UploadFile):
    content = upload.file.read()
    filename = upload.filename.lower()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))

    if df.empty:
        return []

    first_col = df.columns[0]
    phones = []

    for value in df[first_col].dropna().tolist():
        phones.append(normalize_phone(value))

    return phones


def get_agent_panel():
    now = time.time()

    if not agent_status:
        return """
        <div class="agent offline">
            <span class="dot"></span>
            <div>
                <b>Agente local</b><br>
                <small>Offline - ningún EXE conectado</small>
            </div>
        </div>
        """

    panels = ""

    for agent_id, data in agent_status.items():
        last_seen = data.get("last_seen", 0)
        seconds = int(now - last_seen)
        online = seconds <= 20
        css = "online" if online else "offline"
        label = "Activo" if online else "Offline"

        panels += f"""
        <div class="agent {css}">
            <span class="dot"></span>
            <div>
                <b>{agent_id}</b><br>
                <small>{label} - último contacto hace {seconds}s</small>
            </div>
        </div>
        """

    return panels


def layout(title: str, content: str):
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{
                margin: 0;
                font-family: Arial, Helvetica, sans-serif;
                background:
                    radial-gradient(circle at top left, rgba(56,189,248,0.16), transparent 30%),
                    radial-gradient(circle at top right, rgba(245,158,11,0.12), transparent 28%),
                    linear-gradient(135deg, #070b14 0%, #0b1020 45%, #111827 100%);
                color: #f8fafc;
            }}

            header {{
                background: rgba(15,23,42,0.90);
                backdrop-filter: blur(12px);
                padding: 26px 42px;
                border-bottom: 1px solid rgba(148,163,184,0.22);
                display: flex;
                align-items: center;
                gap: 30px;
            }}

            .logo-box {{
                background: rgba(255,255,255,0.94);
                padding: 12px;
                border-radius: 22px;
                box-shadow: 0 0 40px rgba(245,158,11,0.28);
            }}

            .logo {{
                width: 108px;
                height: auto;
                display: block;
            }}

            .title {{
                font-size: 42px;
                font-weight: 900;
                letter-spacing: 5px;
                color: #f8fafc;
                text-shadow: 0 0 20px rgba(56,189,248,0.18);
            }}

            .subtitle {{
                color: #cbd5e1;
                margin-top: 8px;
                font-size: 20px;
            }}

            main {{
                padding: 34px 42px;
            }}

            .card {{
                background: rgba(17,24,39,0.88);
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 20px;
                padding: 24px;
                margin-bottom: 24px;
                box-shadow: 0 22px 55px rgba(0,0,0,0.32);
            }}

            .stats {{
                display: flex;
                gap: 16px;
                flex-wrap: wrap;
            }}

            .stat {{
                background: rgba(12,18,32,0.95);
                border: 1px solid rgba(148,163,184,0.20);
                border-radius: 16px;
                padding: 18px 22px;
                min-width: 145px;
            }}

            .stat b {{
                display: block;
                font-size: 30px;
                margin-top: 8px;
            }}

            .sent {{ color: #22c55e; }}
            .failed {{ color: #ef4444; }}
            .queued {{ color: #f59e0b; }}
            .processing {{ color: #38bdf8; }}

            .button {{
                background: linear-gradient(135deg, #f59e0b, #f97316);
                color: #111827;
                padding: 11px 18px;
                text-decoration: none;
                border-radius: 10px;
                font-weight: 800;
                border: none;
                cursor: pointer;
                box-shadow: 0 8px 18px rgba(245,158,11,0.25);
            }}

            .button-secondary {{
                background: linear-gradient(135deg, #2563eb, #38bdf8);
                color: white;
            }}

            .button-danger {{
                background: linear-gradient(135deg, #dc2626, #ef4444);
                color: white;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                background: rgba(12,18,32,0.95);
                border-radius: 12px;
                overflow: hidden;
            }}

            th, td {{
                border-bottom: 1px solid rgba(148,163,184,0.16);
                padding: 11px;
                font-size: 13px;
                vertical-align: top;
            }}

            th {{
                background: rgba(30,41,59,0.95);
                color: #ffffff;
            }}

            tr:hover {{
                background: rgba(30,41,59,0.55);
            }}

            input, textarea {{
                width: 560px;
                max-width: 95%;
                padding: 11px;
                margin: 8px 0;
                background: #0c1220;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 10px;
            }}

            pre {{
                white-space: pre-wrap;
                font-size: 11px;
                max-height: 130px;
                overflow: auto;
            }}

            .actions {{
                display: flex;
                gap: 8px;
                align-items: center;
            }}

            .agent {{
                display: inline-flex;
                gap: 10px;
                align-items: center;
                padding: 12px 16px;
                border-radius: 14px;
                margin-right: 10px;
                margin-bottom: 10px;
                background: rgba(12,18,32,0.96);
                border: 1px solid rgba(148,163,184,0.20);
            }}

            .dot {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
                display: inline-block;
            }}

            .agent.online .dot {{
                background: #22c55e;
                box-shadow: 0 0 15px #22c55e;
            }}

            .agent.offline .dot {{
                background: #ef4444;
                box-shadow: 0 0 15px #ef4444;
            }}

            .agent small {{
                color: #cbd5e1;
            }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo-box">
                <img class="logo" src="/static/logo.png" onerror="this.parentElement.style.display='none'">
            </div>
            <div>
                <div class="title">NUXWAY SMS</div>
                <div class="subtitle">TG Series Gateway Campaign Platform</div>
            </div>
        </header>
        <main>
            {content}
        </main>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = SessionLocal()

    total = db.query(SmsMessage).count()
    queued = db.query(SmsMessage).filter(SmsMessage.status == "queued").count()
    processing = db.query(SmsMessage).filter(SmsMessage.status == "processing").count()
    sent = db.query(SmsMessage).filter(SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.status == "failed").count()

    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).limit(50).all()

    rows = ""
    for c in campaigns:
        campaign_total = db.query(SmsMessage).filter(SmsMessage.campaign_id == c.id).count()
        campaign_sent = db.query(SmsMessage).filter(SmsMessage.campaign_id == c.id, SmsMessage.status == "sent").count()
        campaign_failed = db.query(SmsMessage).filter(SmsMessage.campaign_id == c.id, SmsMessage.status == "failed").count()
        campaign_queued = db.query(SmsMessage).filter(SmsMessage.campaign_id == c.id, SmsMessage.status == "queued").count()

        rows += f"""
        <tr>
            <td>{c.id}</td>
            <td>{c.name}</td>
            <td>{c.chips}</td>
            <td>{c.status}</td>
            <td>{campaign_total}</td>
            <td class="queued">{campaign_queued}</td>
            <td class="sent">{campaign_sent}</td>
            <td class="failed">{campaign_failed}</td>
            <td>{c.created_at}</td>
            <td>
                <div class="actions">
                    <a class="button button-secondary" href="/campaigns/{c.id}">Ver</a>
                    <form method="post" action="/campaigns/{c.id}/delete" onsubmit="return confirm('¿Eliminar campaña y todos sus mensajes?');">
                        <button class="button button-danger" type="submit">Eliminar</button>
                    </form>
                </div>
            </td>
        </tr>
        """

    db.close()

    content = f"""
        <div class="card">
            <h2>Estado del agente local</h2>
            {get_agent_panel()}
        </div>

        <div class="stats">
            <div class="stat">Total<b>{total}</b></div>
            <div class="stat queued">En cola<b>{queued}</b></div>
            <div class="stat processing">Procesando<b>{processing}</b></div>
            <div class="stat sent">Enviados<b>{sent}</b></div>
            <div class="stat failed">Fallidos<b>{failed}</b></div>
        </div>

        <br>

        <p><a class="button" href="/campaigns/new">Nueva campaña</a></p>

        <div class="card">
            <h2>Campañas</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Chips</th>
                    <th>Estado</th>
                    <th>Total</th>
                    <th>Cola</th>
                    <th>Enviados</th>
                    <th>Fallidos</th>
                    <th>Fecha</th>
                    <th>Acción</th>
                </tr>
                {rows}
            </table>
        </div>
    """

    return layout("Nuxway SMS", content)


@app.get("/campaigns/new", response_class=HTMLResponse)
def new_campaign():
    content = """
    <div class="card">
        <h1>Nueva campaña SMS</h1>

        <p>
            El Excel debe tener los teléfonos en la primera columna.
            En chips usa los puertos del TG, por ejemplo: <b>2,3</b>.
        </p>

        <form action="/campaigns/create" method="post" enctype="multipart/form-data">
            <label>Nombre campaña</label><br>
            <input name="name" required><br>

            <label>Mensaje</label><br>
            <textarea name="message_text" rows="5" required></textarea><br>

            <label>Chips a usar. Ejemplo: 2,3</label><br>
            <input name="chips" value="2" required><br>

            <label>Excel/CSV con teléfonos en primera columna</label><br>
            <input type="file" name="file" required><br><br>

            <button class="button" type="submit">Crear campaña</button>
        </form>

        <p><a href="/">Volver</a></p>
    </div>
    """
    return layout("Nueva campaña", content)


@app.post("/campaigns/create")
def create_campaign(
    name: str = Form(...),
    message_text: str = Form(...),
    chips: str = Form(...),
    file: UploadFile = File(...)
):
    db = SessionLocal()

    try:
        chip_list = parse_chips(chips)
        phones = read_phones_from_excel(file)

        if not phones:
            raise ValueError("El archivo no tiene teléfonos válidos.")

        campaign = Campaign(
            name=name,
            message_text=message_text,
            chips=",".join(str(c) for c in chip_list),
            status="active"
        )

        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        campaign_id = campaign.id

        for index, phone in enumerate(phones):
            chip = chip_list[index % len(chip_list)]

            msg = SmsMessage(
                campaign_id=campaign_id,
                phone=phone,
                text=message_text,
                chip=chip,
                status="queued"
            )

            db.add(msg)

        db.commit()
        db.close()

        return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)

    except Exception as e:
        db.rollback()
        db.close()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(campaign_id: int):
    db = SessionLocal()

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        db.close()
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    total = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id).count()
    queued = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "queued").count()
    processing = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "processing").count()
    sent = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "failed").count()

    messages = (
        db.query(SmsMessage)
        .filter(SmsMessage.campaign_id == campaign_id)
        .order_by(SmsMessage.id.desc())
        .limit(500)
        .all()
    )

    rows = ""
    for m in messages:
        result_short = (m.result or "").replace("<", "").replace(">", "")
        if len(result_short) > 300:
            result_short = result_short[:300] + "..."

        rows += f"""
        <tr>
            <td>{m.id}</td>
            <td>{m.phone}</td>
            <td>{m.chip}</td>
            <td class="{m.status}">{m.status}</td>
            <td>{m.created_at}</td>
            <td>{m.sent_at or ""}</td>
            <td><pre>{result_short}</pre></td>
        </tr>
        """

    db.close()

    content = f"""
    <div class="card">
        <h1>{campaign.name}</h1>
        <p><b>Chips:</b> {campaign.chips}</p>
        <p><b>Mensaje:</b> {campaign.message_text}</p>

        <div class="stats">
            <div class="stat">Total<b>{total}</b></div>
            <div class="stat queued">Cola<b>{queued}</b></div>
            <div class="stat processing">Procesando<b>{processing}</b></div>
            <div class="stat sent">Enviados<b>{sent}</b></div>
            <div class="stat failed">Fallidos<b>{failed}</b></div>
        </div>

        <br>

        <p>
            <a class="button button-secondary" href="/">Volver</a>
            <a class="button" href="/campaigns/{campaign.id}/retry-failed">Reintentar fallidos</a>
        </p>
    </div>

    <div class="card">
        <h2>Resultados</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Teléfono</th>
                <th>Chip</th>
                <th>Estado</th>
                <th>Creado</th>
                <th>Enviado</th>
                <th>Respuesta TG</th>
            </tr>
            {rows}
        </table>
    </div>
    """

    return layout(f"Campaña {campaign.id}", content)


@app.post("/campaigns/{campaign_id}/delete")
def delete_campaign(campaign_id: int):
    db = SessionLocal()

    db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id).delete()
    db.query(Campaign).filter(Campaign.id == campaign_id).delete()

    db.commit()
    db.close()

    return RedirectResponse(url="/", status_code=303)


@app.get("/campaigns/{campaign_id}/retry-failed")
def retry_failed(campaign_id: int):
    db = SessionLocal()

    failed_messages = (
        db.query(SmsMessage)
        .filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "failed")
        .all()
    )

    for m in failed_messages:
        m.status = "queued"
        m.result = None
        m.sent_at = None

    db.commit()
    db.close()

    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)


@app.get("/agent/poll")
def agent_poll(agent_id: str, agent_key: str):
    if agent_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    agent_status[agent_id] = {
        "last_seen": time.time()
    }

    db = SessionLocal()

    msg = (
        db.query(SmsMessage)
        .filter(SmsMessage.status == "queued")
        .order_by(SmsMessage.id.asc())
        .first()
    )

    if not msg:
        db.close()
        return {"job": None}

    msg.status = "processing"
    db.commit()
    db.refresh(msg)

    job = {
        "id": msg.id,
        "campaign_id": msg.campaign_id,
        "phone": msg.phone,
        "text": msg.text,
        "chip": msg.chip
    }

    db.close()
    return {"job": job}


@app.post("/agent/result")
async def agent_result(request: Request, agent_key: str):
    if agent_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    data = await request.json()

    message_id = data.get("id")
    success = data.get("success", False)
    raw = data.get("raw", "")

    db = SessionLocal()
    msg = db.query(SmsMessage).filter(SmsMessage.id == message_id).first()

    if not msg:
        db.close()
        raise HTTPException(status_code=404, detail="Message not found")

    msg.status = "sent" if success else "failed"
    msg.result = raw[:3000]
    msg.sent_at = datetime.utcnow()

    db.commit()
    db.close()

    return {"ok": True}


@app.get("/health")
def health():
    db = SessionLocal()

    total = db.query(SmsMessage).count()
    queued = db.query(SmsMessage).filter(SmsMessage.status == "queued").count()
    processing = db.query(SmsMessage).filter(SmsMessage.status == "processing").count()
    sent = db.query(SmsMessage).filter(SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.status == "failed").count()

    db.close()

    return {
        "status": "ok",
        "total": total,
        "queued": queued,
        "processing": processing,
        "sent": sent,
        "failed": failed,
        "agents": agent_status
    }
