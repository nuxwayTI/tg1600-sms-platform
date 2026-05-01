# TG1600 SMS Platform

Plataforma web para campañas SMS usando Render + PostgreSQL + agente local + TG1600.

## Arquitectura

Render Web App -> PostgreSQL -> Agent EXE -> TG1600 -> SIM 1 a SIM 16

## Render

Crear PostgreSQL y Web Service.

Variables:

API_KEY
DATABASE_URL
COUNTRY_CODE

## Web Service

Root Directory:

backend

Build Command:

pip install -r requirements.txt

Start Command:

uvicorn main:app --host 0.0.0.0 --port $PORT

## Agent

Ejecutar en la red local del TG1600.

Compilar EXE:

cd agent
pip install -r requirements.txt
python -m PyInstaller --onefile --windowed gui_agent.py
