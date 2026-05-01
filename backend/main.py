import os
import io
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from database import Base, engine, SessionLocal
from models import Campaign, SmsMessage

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TG1600 SMS Platform")

API_KEY = os.getenv("API_KEY", "change-me")
COUNTRY_CODE = os.getenv("COUNTRY_CODE", "591")


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


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = SessionLocal()

    total = db.query(SmsMessage).count()
    queued = db.query(SmsMessage).filter(SmsMessage.status == "queued").count()
    sent = db.query(SmsMessage).filter(SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.status == "failed").count()
    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).limit(20).all()
    db.close()

    rows = ""
    for c in campaigns:
        rows += f"""
        <tr>
            <td>{c.id}</td>
            <td>{c.name}</td>
            <td>{c.chips}</td>
            <td>{c.status}</td>
            <td>{c.created_at}</td>
            <td><a href="/campaigns/{c.id}">Ver</a></td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>TG1600 SMS Platform</title>
        <style>
            body {{ font-family: Arial; margin: 30px; }}
            .card {{ border:1px solid #ddd; padding:15px; margin:10px 0; border-radius:8px; }}
            table {{ border-collapse: collapse; width:100%; }}
            th, td {{ border:1px solid #ddd; padding:8px; }}
            th {{ background:#f2f2f2; }}
            a.button {{ background:#1a73e8; color:white; padding:10px 15px; text-decoration:none; border-radius:6px; }}
        </style>
    </head>
    <body>
        <h1>TG1600 SMS Platform</h1>

        <div class="card">
            <b>Total:</b> {total} |
            <b>En cola:</b> {queued} |
            <b>Enviados:</b> {sent} |
            <b>Fallidos:</b> {failed}
        </div>

        <p><a class="button" href="/campaigns/new">Nueva campaña</a></p>

        <h2>Campañas</h2>
        <table>
            <tr>
                <th>ID</th><th>Nombre</th><th>Chips</th><th>Estado</th><th>Fecha</th><th>Acción</th>
            </tr>
            {rows}
        </table>
    </body>
    </html>
    """


@app.get("/campaigns/new", response_class=HTMLResponse)
def new_campaign():
    return """
    <html>
    <head>
        <title>Nueva campaña</title>
        <style>
            body { font-family: Arial; margin: 30px; }
            input, textarea { width: 500px; padding: 8px; margin: 6px 0; }
            button { padding:10px 15px; }
        </style>
    </head>
    <body>
        <h1>Nueva campaña SMS</h1>

        <form action="/campaigns/create" method="post" enctype="multipart/form-data">
            <label>Nombre campaña</label><br>
            <input name="name" required><br>

            <label>Mensaje</label><br>
            <textarea name="message_text" rows="5" required></textarea><br>

            <label>Chips a usar. Ejemplo: 1,2,3,4</label><br>
            <input name="chips" value="1" required><br>

            <label>Excel/CSV con teléfonos en la primera columna</label><br>
            <input type="file" name="file" required><br><br>

            <button type="submit">Crear campaña</button>
        </form>

        <p><a href="/">Volver</a></p>
    </body>
    </html>
    """


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

        campaign = Campaign(
            name=name,
            message_text=message_text,
            chips=",".join(str(c) for c in chip_list),
            status="active"
        )

        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        for index, phone in enumerate(phones):
            chip = chip_list[index % len(chip_list)]

            msg = SmsMessage(
                campaign_id=campaign.id,
                phone=phone,
                text=message_text,
                chip=chip,
                status="queued"
            )

            db.add(msg)

        db.commit()

    except Exception as e:
        db.rollback()
        db.close()
        raise HTTPException(status_code=400, detail=str(e))

    db.close()
    return RedirectResponse(url=f"/campaigns/{campaign.id}", status_code=303)


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(campaign_id: int):
    db = SessionLocal()

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        db.close()
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    total = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id).count()
    queued = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "queued").count()
    sent = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id, SmsMessage.status == "failed").count()

    messages = db.query(SmsMessage).filter(SmsMessage.campaign_id == campaign_id).order_by(SmsMessage.id.desc()).limit(100).all()

    rows = ""
    for m in messages:
        rows += f"""
        <tr>
            <td>{m.id}</td>
            <td>{m.phone}</td>
            <td>{m.chip}</td>
            <td>{m.status}</td>
            <td>{m.sent_at}</td>
            <td>{m.result or ""}</td>
        </tr>
        """

    db.close()

    return f"""
    <html>
    <head>
        <title>Campaña {campaign.id}</title>
        <style>
            body {{ font-family: Arial; margin: 30px; }}
            table {{ border-collapse: collapse; width:100%; }}
            th, td {{ border:1px solid #ddd; padding:8px; font-size:13px; }}
            th {{ background:#f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>{campaign.name}</h1>
        <p><b>Chips:</b> {campaign.chips}</p>
        <p><b>Mensaje:</b> {campaign.message_text}</p>

        <p>
            Total: {total} |
            En cola: {queued} |
            Enviados: {sent} |
            Fallidos: {failed}
        </p>

        <h2>Últimos mensajes</h2>
        <table>
            <tr>
                <th>ID</th><th>Teléfono</th><th>Chip</th><th>Estado</th><th>Enviado</th><th>Resultado</th>
            </tr>
            {rows}
        </table>

        <p><a href="/">Volver</a></p>
    </body>
    </html>
    """


@app.get("/agent/poll")
def agent_poll(agent_id: str, agent_key: str):
    if agent_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid agent key")

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
    msg.result = raw[:2000]
    msg.sent_at = datetime.utcnow()

    db.commit()
    db.close()

    return {"ok": True}


@app.post("/agent/inbound")
async def agent_inbound(request: Request, agent_key: str):
    if agent_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    data = await request.json()
    return {"ok": True, "received": data}


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
        "failed": failed
    }
