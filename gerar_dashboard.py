#!/usr/bin/env python3
"""Regenera o dashboard Nestlé: busca tickets da org NESTLE STORES no Zendesk,
substitui o array `const TICKETS = [...]` no HTML atual e salva em ~/Downloads/index.html"""
import sys, re, json, time, os, base64, datetime as dt
import requests

class zd:  # cliente mínimo (credenciais via variáveis de ambiente, nunca no código)
    BASE_URL = "https://vmtecnologiasupport.zendesk.com/api/v2"
    @staticmethod
    def _headers():
        cred = f"{os.environ['ZENDESK_EMAIL']}/token:{os.environ['ZENDESK_TOKEN']}"
        return {"Authorization": "Basic " + base64.b64encode(cred.encode()).decode()}

ORG_ID = 31292232206235            # NESTLE STORES
CAT_FIELD = 42489784314907         # Categoria - Nestlé tagger
CATS = {"alterar_receita_nestle":"ALTERAR RECEITA","enviar_telemetria_nestle":"ENVIAR TELEMETRIA",
        "enviar_venda_nestle":"ENVIAR VENDA","instalação_nestle":"INSTALAÇÃO",
        "instalação_não_realizada":"INSTALAÇÃO NÃO REALIZADA","não_conecta_nestle":"NÃO CONECTA",
        "off_2m_nestle":"OFF 2M","sistema_de_pagamento_nestle":"SISTEMA DE PAGAMENTO"}
BRT = dt.timezone(dt.timedelta(hours=-3))

def fetch():
    params = {"include": "metric_sets,users", "page[size]": 100}
    url, tickets, users, metrics = f"{zd.BASE_URL}/organizations/{ORG_ID}/tickets.json", [], {}, {}
    while url:
        r = requests.get(url, headers=zd._headers(), params=params, timeout=90)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 30))); continue
        r.raise_for_status(); d = r.json()
        tickets += d["tickets"]
        users.update({u["id"]: u["name"] for u in d.get("users", [])})
        metrics.update({m["ticket_id"]: m for m in d.get("metric_sets", [])})
        url, params = (d["links"]["next"] if d["meta"]["has_more"] else None), None
        time.sleep(0.1)
    return tickets, users, metrics

def montar(tickets, users, metrics):
    rows = {}
    for t in tickets:
        cf = {f["id"]: f["value"] for f in t["custom_fields"]}
        cat = CATS.get(cf.get(CAT_FIELD), "Sem categoria")
        sat = (t.get("satisfaction_rating") or {}).get("score") or "unoffered"
        sat = {"good":"Good","bad":"Bad","offered":"Offered","unoffered":"Unoffered"}.get(sat.lower(), "Unoffered")
        m = metrics.get(t["id"], {})
        ia = m.get("initially_assigned_at")   # "espera_h" no dashboard é em MINUTOS: 1ª atribuição - criação do ticket
        espera = round((dt.datetime.fromisoformat(ia.replace("Z","+00:00")) - dt.datetime.fromisoformat(t["created_at"].replace("Z","+00:00"))).total_seconds()/60, 4) if ia else None
        fr = (m.get("full_resolution_time_in_minutes") or {}).get("calendar")
        d = dt.datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")).astimezone(BRT).strftime("%Y-%m-%d")
        rows[t["id"]] = {"id": t["id"], "data": d,
            "solicitante": users.get(t["requester_id"], "—"), "categoria": cat,
            "atribuido": users.get(t["assignee_id"], "—"), "satisfacao": sat,
            "espera_h": espera, "resolucao_min": fr or 0}
    return sorted(rows.values(), key=lambda r: (r["data"], r["id"]), reverse=True)

JANELA_DIAS = 120  # recalcula os últimos 120 dias; mais antigos vêm do histórico já publicado
RAW = "https://raw.githubusercontent.com/luizvmtecnologia-dot/nayax-scripts/main/index.html"

def main(base_html, saida):
    s = open(base_html, encoding="utf-8").read() if base_html != "RAW" else requests.get(RAW, timeout=60).text
    antigo = json.loads(re.search(r"const TICKETS = (\[.*?\]);", s, re.S).group(1))
    corte = (dt.datetime.now(BRT) - dt.timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%d")
    tickets, users, metrics = fetch()
    novos = [r for r in montar(tickets, users, metrics) if r["data"] >= corte]
    rows = [r for r in antigo if r["data"] < corte] + novos
    rows.sort(key=lambda r: (r["data"], r["id"]), reverse=True)
    novo = "const TICKETS = " + json.dumps(rows, ensure_ascii=False) + ";"
    s2, n = re.subn(r"const TICKETS = \[.*?\];", lambda m: novo, s, count=1, flags=re.S)
    assert n == 1, "array TICKETS não encontrado"
    ts = dt.datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    s2 = re.sub(r'(id="footRefreshed"[^>]*>)[^<]*', lambda m: m.group(1) + ts, s2, count=1)
    open(saida, "w", encoding="utf-8").write(s2)
    print("tickets:", len(rows), "| período:", rows[-1]["data"], "→", rows[0]["data"], "| salvo em", saida)
    return rows

if __name__ == "__main__":
    # uso: python gerar_dashboard.py RAW index.html   (RAW = baixa o index.html atual do GitHub como base)
    main(sys.argv[1] if len(sys.argv) > 1 else "RAW", sys.argv[2] if len(sys.argv) > 2 else "index.html")
