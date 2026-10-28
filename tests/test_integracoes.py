import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["TST_DATA_DIR"] = tempfile.mkdtemp()

from openpyxl import Workbook  # noqa: E402

from tst_gestao.app import create_app  # noqa: E402
from tst_gestao import integracoes as ig  # noqa: E402


def admin():
    c = create_app().test_client()
    c.get("/login")
    with c.session_transaction() as s:
        t = s["csrf"]
    for senha in ("segredo1", "admin"):  # o banco temporário é compartilhado entre os módulos de teste
        c.post("/login", data={"usuario": "admin", "senha": senha, "csrf_token": t})
        with c.session_transaction() as s:
            if s.get("uid"):
                break
            t = s["csrf"]
    with c.session_transaction() as s:
        c.environ_base["HTTP_X_CSRF_TOKEN"] = s["csrf"]
    c.post("/api/senha", json={"atual": senha, "nova": "segredo1"})
    return c


def test_api_entrada_saida_e_webhook():
    recebidos = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            corpo = self.rfile.read(int(self.headers["Content-Length"]))
            recebidos.append((self.headers, corpo))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    a = admin()
    leitura = a.post("/api/integracoes/chaves", json={"nome": "r", "escopo": "leitura"}).get_json()["chave"]
    escrita = a.post("/api/integracoes/chaves", json={"nome": "w", "escopo": "escrita"}).get_json()["chave"]
    a.post("/api/integracoes/webhooks", json={"nome": "h", "url": f"http://127.0.0.1:{srv.server_port}/", "eventos": ["paciente.criado"]})
    segredo = a.get("/api/integracoes/webhooks").get_json()["webhooks"][0]["segredo"]

    api = create_app().test_client()  # sem sessão nem CSRF
    H_R, H_W = {"Authorization": f"Bearer {leitura}"}, {"Authorization": f"Bearer {escrita}"}
    assert api.get("/api/v1/pacientes").status_code == 401
    assert api.get("/api/v1/pacientes", headers={"Authorization": "Bearer x"}).status_code == 401
    assert api.post("/api/v1/pacientes", json={}, headers=H_R).status_code == 403

    r = api.post("/api/v1/pacientes", headers=H_W, json=[
        {"codigo": "A1", "nome": "Ana", "nascimento": "10/05/1950", "Data de admissão": "01/10/2026", "complexidade": "Intensivo"},
        {"codigo": "A1", "cidade": "Recife"},
        {"nome": "Sem código"},
    ])
    d = r.get_json()
    assert r.status_code == 207 and (d["criados"], d["atualizados"], len(d["erros"])) == (1, 1, 1)
    p = api.get("/api/v1/pacientes?ativo=true", headers=H_R).get_json()
    assert p["total"] == 1 and p["dados"][0]["nome"] == "Ana" and p["dados"][0]["cidade"] == "Recife"
    assert p["dados"][0]["nascimento"] == "1950-05-10"

    mov = {"data": "2026-10-19", "codigo_paciente": "A1", "evento": "Alta", "motivo": "Alta clínica"}
    assert api.post("/api/v1/movimentacao", json=mov, headers=H_W).get_json()["criados"] == 1
    assert api.post("/api/v1/movimentacao", json=mov, headers=H_W).get_json()["ignorados"] == 1
    assert api.get("/api/v1/indicadores?ref=2026-10-19", headers=H_R).get_json()["altas"]["dia"] == 1
    assert "Alta clínica" in a.get("/api/opcoes").get_json()["motivos_alta"]
    assert a.get("/integracoes").status_code == 200

    for _ in range(50):
        if recebidos:
            break
        time.sleep(0.1)
    hdr, corpo = recebidos[0]
    assert hdr["X-TST-Event"] == "paciente.criado"
    assert hdr["X-TST-Signature"] == "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    assert json.loads(corpo)["dados"]["codigo"] == "A1"
    srv.shutdown()


def test_importar_planilha_xlsx_e_csv():
    a = admin()
    wb = Workbook()
    ws = wb.active
    ws.append(["Código", "Nome", "Data de nascimento", "Bairro"])
    ws.append([101, "Beto", "03/02/1980", "Centro"])
    ws.append([102, "", None, None])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = a.post("/api/importar/pacientes", data={"file": (buf, "p.xlsx")}, content_type="multipart/form-data")
    d = r.get_json()
    assert (d["criados"], len(d["erros"])) == (1, 1)

    csv = "mes;codigo paciente;terapia;situação;valor\n10/2026;101;FONO;Pendente;150,5\n".encode("utf-8")
    r = a.post("/api/importar/terapias", data={"file": (io.BytesIO(csv), "t.csv")}, content_type="multipart/form-data")
    assert r.get_json()["criados"] == 1, r.get_json()
    t = a.get("/api/terapias").get_json()[0]
    assert t["codigo_paciente"] == "101" and t["valor"] == 150.5 and t["mes"] == "2026-10"
    bad = a.post("/api/importar/pacientes", data={"file": (io.BytesIO(b"x"), "x.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 400


def test_sincronizar_dadosbi_importa_pacientes_e_visitas_sem_duplicar(monkeypatch):
    create_app()
    payload = {
        "sucesso": True,
        "dados": [{
            "id": "DADOSBI-TESTE-1",
            "nmpaciente": "Paciente de teste BI",
            "nmoperadora": "Operadora teste",
            "nmservico": "Monitoramento",
            "status": "EM ATENDIMENTO",
            "dataadmissao": "22/08/2024",
            "dataalta": None,
            "condicaoalta": None,
            "visitas": [{
                "id": "DADOSBI-VISITA-TESTE-1",
                "nmprofessional": "Profissional de teste",
                "nmespecialidade": "Fisioterapia",
                "datavisita": "15/10/2024",
            }],
        }],
    }

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limite):
            return json.dumps(payload).encode()

    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda *_a, **_kw: Resposta())

    primeiro = ig.sincronizar_dadosbi()
    payload["dados"][0]["visitas"][0]["nmespecialidade"] = "Fisioterapia atualizada"
    segundo = ig.sincronizar_dadosbi()
    assert (primeiro["pacientes_criados"], primeiro["visitas_importadas"]) == (1, 1)
    assert (segundo["pacientes_atualizados"], segundo["visitas_importadas"]) == (1, 0)
    with ig.connect() as conn:
        paciente = conn.execute("SELECT * FROM pacientes WHERE codigo = ?", ("DADOSBI-TESTE-1",)).fetchone()
        visitas = conn.execute(
            "SELECT e.* FROM evolucoes e JOIN dadosbi_visitas v ON v.evolucao_id = e.id WHERE v.origem_id = ?",
            ("DADOSBI-VISITA-TESTE-1",),
        ).fetchall()
    assert paciente["data_admissao"] == "2024-08-22" and paciente["data_alta"] is None
    assert len(visitas) == 1 and visitas[0]["tipo"] == "Visita"
    assert "Fisioterapia atualizada" in visitas[0]["texto"]
