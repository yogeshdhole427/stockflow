# StockFlow — Backend Case Study Solution

This repository contains a minimal, runnable solution for the Backend Engineering Intern case study.

## Contents
- `schema.sql` — SQL DDL for the inventory system
- `app.py` — Flask + SQLAlchemy API with:
  - `POST /api/products` — robust product creation (atomic, validated)
  - `GET  /api/companies/<id>/alerts/low-stock` — low-stock alerts per warehouse
- `.env.example` — sample environment configuration
- `requirements.txt` — Python dependencies

## Quick Start (SQLite)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///stockflow.db
python app.py
```

## Quick Start (PostgreSQL)
```bash
# Set DATABASE_URL to your Postgres connection string
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/stockflow
psql "$DATABASE_URL" -f schema.sql
python app.py
```

## Endpoints

### 1) Create Product
`POST /api/products`
```json
{
  "name": "USB Keyboard",
  "sku": "KB-001",
  "price": 799.00,
  "warehouse_id": 1,
  "initial_quantity": 25
}
```
**Responses**
- `201 Created` — returns product + inventory
- `409 Conflict` — duplicate SKU
- `415` / `400` — invalid payload

### 2) Low-Stock Alerts
`GET /api/companies/{company_id}/alerts/low-stock?days=30`

Returns items that had sales in the last N days and whose current stock is below threshold (per-warehouse override if present, else product default).

## Notes
- SKU is unique globally.
- Inventories keyed by (product, warehouse).
- All writes are atomic and validated.