import os
import io
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = SessionLocal()

    total = db.query(SmsMessage).count()
    queued = db.query(SmsMessage).filter(SmsMessage.status == "queued").count()
    processing = db.query(SmsMessage).filter(SmsMessage.status == "processing").count()
    sent = db.query(SmsMessage).filter(SmsMessage.status == "sent").count()
    failed = db.query(SmsMessage).filter(SmsMessage.status == "failed").count()

    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).limit(30).all()

    rows = ""
    for c in campaigns:
        campaign_total = db.query(SmsMessage).filter(SmsMessage.campaign_id == c.id).count()
        campaign_sent = db.query(SmsMessage).filter(
            SmsMessage.campaign_id == c.id,
            SmsMessage.status == "sent"
        ).count()
        campaign_failed = db.query(SmsMessage).filter(
            SmsMessage.campaign_id == c.id,
            SmsMessage.status == "failed"
        ).count()
        campaign_queued = db.query(SmsMessage).filter(
            SmsMessage.campaign_id == c.id,
            SmsMessage.status == "queued"
        ).count()

        rows += f"""
        <tr>
            <td>{c.id}</td>
            <td>{c.name}</td>
            <td>{c.chips}</td>
            <td>{c.status}</td>
            <td>{campaign_total}</td>
            <td>{campaign_queued}</td>
            <td>{campaign_sent}</td>
            <td>{campaign_failed}</td>
            <td>{c.created_at}</td>
            <td><a href="/campaigns/{c.id}">Ver resultados</a></td>
        </tr>
        """

    db.close()

    return f"""
    <html>
    <head>
        <title>TG1600 SMS Platform</title>
        <style>
            body {{ font-family: Arial; margin: 30px; }}
            .card {{ border:1px solid #ddd; padding:15px; margin:10px 0; border-radius:8px; }}
            table {{ border-collapse: collapse; width:100%; }}
            th, td {{ border:1px solid #ddd; padding:8px; font-size:13px; }}
            th {{ background:#f2f2f2; }}
            a.button {{ background:#1a73e8; color:white; padding:10px 15px; text-decoration:none; border-radius:6px; }}
            .sent {{ color: green; font-weight: bold; }}
            .failed {{ color: red; font-weight: bold; }}
            .queued {{ color: orange; font-weight: bold; }}
            .processing {{ color: blue; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>TG1600 SMS Platform</h1>

        <div class="card">
            <b>Total:</b> {total} |
            <b>En cola:</b> {queued} |
            <b>Procesando:</b> {processing} |
            <b class="sent">Enviados:</b> {sent} |
            <b class="failed">Fallidos:</b> {failed}
        </div>

        <p><a class="button" href="/campaigns/new">Nueva campaña</a></p>

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
            .note { background:#fff8d6; padding:12px; border:1px solid #e8d36c; width:520px; }
        </style>
    </head>
    <body>
        <h1>Nueva campaña SMS</h1>

        <div class="note">
            <b>Importante:</b><br>
            El Excel debe tener los teléfonos en la primera columna.<br>
            En "Chips a usar", escribe ranuras separadas por coma. Ejemplo: 2,3
        </div>

        <br>

        <form action="/campaigns/create" method="post" enctype="multipart/form-data">
            <label>Nombre campaña</label><br>
            <input name="name" required><br>

            <label>Mensaje</label><br>
            <textarea name="message_text" rows="5" required></textarea><br>

            <label>Chips a usar. Ejemplo: 2,3</label><br>
            <input name="chips" value="2" required><br>

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
        .limit(300)
        .all()
    )

    rows = ""
    for m in messages:
        status_class = m.status
        result_short = (m.result or "").replace("<", "").replace(">", "")
        if len(result_short) > 300:
            result_short = result_short[:300] + "..."

        rows += f"""
        <tr>
            <td>{m.id}</td>
            <td>{m.phone}</td>
            <td>{m.chip}</td>
            <td class="{status_class}">{m.status}</td>
            <td>{m.created_at}</td>
            <td>{m.sent_at or ""}</td>
            <td><pre>{result_short}</pre></td>
        </tr>
        """

    db.close()

    return f"""
    <html>
    <head>
        <title>Campaña {campaign.id}</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body {{ font-family: Arial; margin: 30px; }}
            table {{ border-collapse: collapse; width:100%; }}
            th, td {{ border:1px solid #ddd; padding:8px; font-size:13px; vertical-align: top; }}
            th {{ background:#f2f2f2; }}
            pre {{ white-space: pre-wrap; font-size:11px; max-height:120px; overflow:auto; }}
            .sent {{ color: green; font-weight: bold; }}
            .failed {{ color: red; font-weight: bold; }}
            .queued {{ color: orange; font-weight: bold; }}
            .processing {{ color: blue; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>{campaign.name}</h1>

        <p><b>Chips:</b> {campaign.chips}</p>
        <p><b>Mensaje:</b> {campaign.message_text}</p>

        <h2>Resultados</h2>
        <p>
            Total: {total} |
            En cola: {queued} |
            Procesando: {processing} |
            <span class="sent">Enviados: {sent}</span> |
            <span class="failed">Fallidos: {failed}</span>
        </p>

        <p>
            <a href="/">Volver</a> |
            <a href="/campaigns/{campaign.id}/retry-failed">Reintentar fallidos</a>
        </p>

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
    </body>
    </html>
    """


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
