from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from . import bi
from . import relatorios as rel
from . import integracoes as ig
from . import banco
from .db import DATA_DIR, EVENTOS, LISTAS, NIVEIS, ErroIntegridade, connect, garantir_opcao, init_db

ANEXOS_DIR = DATA_DIR / "anexos"
MAX_UPLOAD = 20_000_000
EXT_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".odt", ".ods"}
EXT_INLINE = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def remover_arquivo(nome: str) -> None:
    try:
        (ANEXOS_DIR / nome).unlink(missing_ok=True)
    except OSError:  # arquivo em uso (Windows): o registro já foi removido, sobra apenas o arquivo órfão
        pass

SIM_NAO = ["Sim", "Não"]
WEBHOOK_EVENTO = {
    "pacientes": ("paciente.criado", "paciente.atualizado"),
    "terapias": ("terapia.criada", "terapia.atualizada"),
    "movimentacao": ("movimentacao.criada", "movimentacao.criada"),
}
FILTROS_API = {
    "pacientes": ["codigo", "cidade", "bairro", "operadora", "servico", "complexidade", "diagnostico", "sexo"],
    "terapias": ["mes", "codigo_paciente", "terapia", "situacao", "profissional", "empresa"],
    "movimentacao": ["codigo_paciente", "evento"],
}
EXTRA_ALIAS = {
    "pacientes": {"cod": "codigo", "nome_paciente": "nome", "nome_do_paciente": "nome", "data_nascimento": "nascimento"},
    "terapias": {"cod_paciente": "codigo_paciente", "codigo_do_paciente": "codigo_paciente", "profissional_responsavel": "profissional"},
    "movimentacao": {"cod_paciente": "codigo_paciente", "codigo_do_paciente": "codigo_paciente"},
}

# tipo: text | date | month | int | money | select (fonte: lista em `opcoes`, valores fixos ou pacientes)
ENTIDADES = {
    "pacientes": {
        "titulo": "Pacientes",
        "tabela": "pacientes",
        "busca": ["codigo", "nome", "bairro", "cidade", "diagnostico"],
        "ordem": "nome COLLATE NOCASE",
        "obrigatorios": ["codigo", "nome"],
        "campos": [
            {"nome": "codigo", "rotulo": "Código", "tipo": "text"},
            {"nome": "nome", "rotulo": "Nome", "tipo": "text"},
            {"nome": "nascimento", "rotulo": "Nascimento", "tipo": "date"},
            {"nome": "sexo", "rotulo": "Sexo", "tipo": "select", "valores": ["F", "M"]},
            {"nome": "bairro", "rotulo": "Bairro", "tipo": "text"},
            {"nome": "cidade", "rotulo": "Cidade", "tipo": "text"},
            {"nome": "operadora", "rotulo": "Operadora", "tipo": "select", "lista": "operadoras"},
            {"nome": "diagnostico", "rotulo": "Diagnóstico", "tipo": "select", "lista": "diagnosticos"},
            {"nome": "complexidade", "rotulo": "Complexidade", "tipo": "select", "lista": "complexidades"},
            {"nome": "servico", "rotulo": "Serviço", "tipo": "select", "lista": "servicos"},
            {"nome": "data_admissao", "rotulo": "Data de admissão", "tipo": "date"},
            {"nome": "data_alta", "rotulo": "Data da alta", "tipo": "date"},
            {"nome": "motivo_alta", "rotulo": "Motivo da alta", "tipo": "select", "lista": "motivos_alta"},
        ],
        "tabela_cols": ["codigo", "nome", "nascimento", "cidade", "operadora", "complexidade", "servico", "data_alta"],
    },
    "terapias": {
        "titulo": "Terapias",
        "tabela": "terapias",
        "busca": ["codigo_paciente", "terapia", "profissional", "empresa"],
        "ordem": "mes DESC, codigo_paciente, terapia",
        "obrigatorios": ["mes", "codigo_paciente", "terapia"],
        "filtro_mes": True,
        "campos": [
            {"nome": "mes", "rotulo": "Mês", "tipo": "month"},
            {"nome": "codigo_paciente", "rotulo": "Paciente", "tipo": "select", "lista": "@pacientes"},
            {"nome": "terapia", "rotulo": "Terapia", "tipo": "select", "lista": "terapias"},
            {"nome": "modalidade", "rotulo": "Modalidade", "tipo": "select", "lista": "modalidades"},
            {"nome": "empresa", "rotulo": "Empresa", "tipo": "select", "lista": "empresas"},
            {"nome": "profissional", "rotulo": "Profissional", "tipo": "select", "lista": "profissionais"},
            {"nome": "situacao", "rotulo": "Situação", "tipo": "select", "lista": "situacoes"},
            {"nome": "sessoes", "rotulo": "Sessões", "tipo": "int"},
            {"nome": "frequencia", "rotulo": "Frequência", "tipo": "select", "lista": "frequencias"},
            {"nome": "valor", "rotulo": "Valor (R$)", "tipo": "money"},
            {"nome": "agendado", "rotulo": "Agendado", "tipo": "select", "valores": SIM_NAO},
            {"nome": "relatorio", "rotulo": "Relatório", "tipo": "select", "valores": SIM_NAO},
            {"nome": "observacao", "rotulo": "Observação", "tipo": "text"},
        ],
        "tabela_cols": ["mes", "codigo_paciente", "terapia", "profissional", "situacao", "sessoes", "valor", "agendado", "relatorio"],
    },
    "movimentacao": {
        "titulo": "Movimentação",
        "tabela": "movimentacao",
        "busca": ["codigo_paciente", "evento", "motivo"],
        "ordem": "data DESC, id DESC",
        "obrigatorios": ["data", "codigo_paciente", "evento"],
        "campos": [
            {"nome": "data", "rotulo": "Data", "tipo": "date"},
            {"nome": "codigo_paciente", "rotulo": "Paciente", "tipo": "select", "lista": "@pacientes"},
            {"nome": "evento", "rotulo": "Evento", "tipo": "select", "valores": EVENTOS},
            {"nome": "motivo", "rotulo": "Motivo", "tipo": "text"},
        ],
        "tabela_cols": ["data", "codigo_paciente", "evento", "motivo"],
    },
}


def create_app() -> Flask:
    init_db()
    app = Flask(__name__)
    key_file = DATA_DIR / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    app.secret_key = key_file.read_text()
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True, MAX_CONTENT_LENGTH=MAX_UPLOAD + 1_000_000)

    # ---------- segurança / sessão ----------
    def usuario_atual():
        uid = session.get("uid")
        if not uid:
            return None
        with connect() as conn:
            u = conn.execute("SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (uid,)).fetchone()
        return u

    def exige(nivel: str):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                u = usuario_atual()
                if not u or NIVEIS[u["nivel"]] < NIVEIS[nivel]:
                    abort(403)
                return fn(*a, **kw)

            return wrapper

        return deco

    @app.before_request
    def protecao():
        if request.path.startswith("/api/v1/"):
            return None  # API externa: autenticada por chave, sem sessão/CSRF
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method in ("POST", "PUT", "DELETE"):
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not token or not secrets.compare_digest(token, session["csrf"]):
                abort(400, "Token inválido. Recarregue a página.")
        if request.endpoint in ("login", "static") or request.endpoint is None:
            return None
        u = usuario_atual()
        if not u:
            if request.path.startswith("/api/"):
                return jsonify(erro="Sessão expirada."), 401
            return redirect(url_for("login"))
        if u["trocar_senha"] and request.endpoint not in ("perfil", "logout", "api_senha"):
            return redirect(url_for("perfil"))
        return None

    @app.context_processor
    def contexto():
        u = usuario_atual()
        return {"usuario": u, "csrf_token": session.get("csrf", ""), "nivel": NIVEIS.get(u["nivel"], 0) if u else 0}

    @app.errorhandler(403)
    def proibido(_):
        if request.path.startswith("/api/"):
            return jsonify(erro="Sem permissão para esta ação."), 403
        return render_template("erro.html", mensagem="Você não tem permissão para acessar esta área."), 403

    @app.errorhandler(400)
    def requisicao_invalida(e):
        return jsonify(erro=getattr(e, "description", "Requisição inválida.")), 400

    # ---------- autenticação ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        erro = None
        if request.method == "POST":
            with connect() as conn:
                u = conn.execute(
                    "SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?) AND ativo = 1", (request.form.get("usuario", "").strip(),)
                ).fetchone()
            if u and check_password_hash(u["senha_hash"], request.form.get("senha", "")):
                session.clear()
                session["uid"] = u["id"]
                session["csrf"] = secrets.token_hex(16)
                return redirect(url_for("index"))
            erro = "Usuário ou senha inválidos."
        return render_template("login.html", erro=erro)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/perfil")
    def perfil():
        return render_template("perfil.html", ativa="perfil")

    @app.post("/api/senha")
    def api_senha():
        d = request.get_json(silent=True) or {}
        u = usuario_atual()
        nova = d.get("nova", "")
        if not check_password_hash(u["senha_hash"], d.get("atual", "")):
            return jsonify(erro="Senha atual incorreta."), 400
        if len(nova) < 6 or nova == "admin":
            return jsonify(erro="A nova senha deve ter ao menos 6 caracteres e não pode ser 'admin'."), 400
        with connect() as conn:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?", (generate_password_hash(nova), u["id"])
            )
        return jsonify(ok=True)

    # ---------- páginas ----------
    @app.route("/")
    def index():
        return render_template("dashboard.html", ativa="dashboard", hoje=date.today().isoformat())

    @app.route("/relatorios")
    def relatorios():
        return render_template("relatorios.html", ativa="relatorios", grupos=rel.agrupados())

    @app.route("/relatorios/<slug>")
    def relatorio(slug):
        if slug not in rel.REL:
            abort(404)
        dados = rel.gerar(slug, request.args)
        if request.args.get("formato") == "csv":
            nome = f"tst-{slug}-{dados['gerado_em']:%Y%m%d}.csv"
            return Response(rel.para_csv(dados), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{nome}"'})
        return render_template("relatorio.html", ativa="relatorios", d=dados, periodos=rel.PERIODOS, situacoes=rel.SITUACOES)

    @app.route("/cadastro/<ent>")
    def cadastro(ent):
        if ent not in ENTIDADES:
            abort(404)
        return render_template("crud.html", ativa=ent, ent=ent, titulo=ENTIDADES[ent]["titulo"])

    # ---------- prontuário ----------
    @app.route("/paciente/<path:codigo>")
    def prontuario(codigo):
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM pacientes WHERE codigo = ?", (codigo,)).fetchone():
                abort(404)
        return render_template("prontuario.html", ativa="pacientes", codigo=codigo, hoje=date.today().isoformat())

    @app.errorhandler(404)
    def nao_encontrado(_):
        if request.path.startswith("/api/"):
            return jsonify(erro="Registro não encontrado."), 404
        return render_template("erro.html", mensagem="Página ou registro não encontrado."), 404

    @app.errorhandler(413)
    def grande_demais(_):
        return jsonify(erro=f"Arquivo acima do limite de {MAX_UPLOAD // 1_000_000} MB."), 413

    @app.get("/api/prontuario/<path:codigo>")
    def api_prontuario(codigo):
        with connect() as conn:
            pac = conn.execute("SELECT * FROM pacientes WHERE codigo = ?", (codigo,)).fetchone()
            if not pac:
                abort(404)
            q = lambda sql: [dict(r) for r in conn.execute(sql, (codigo,))]
            return jsonify(
                paciente=dict(pac),
                evolucoes=q("SELECT * FROM evolucoes WHERE codigo_paciente = ? ORDER BY data DESC, id DESC"),
                movimentacao=q("SELECT * FROM movimentacao WHERE codigo_paciente = ? ORDER BY data DESC, id DESC"),
                terapias=q("SELECT * FROM terapias WHERE codigo_paciente = ? ORDER BY mes DESC, terapia"),
                anexos=q(
                    "SELECT id, categoria, descricao, data_documento, nome_original, tamanho, enviado_por, criado_em "
                    "FROM anexos WHERE codigo_paciente = ? ORDER BY COALESCE(data_documento, substr(criado_em, 1, 10)) DESC, id DESC"
                ),
                opcoes={
                    "tipos": [r[0] for r in conn.execute("SELECT valor FROM opcoes WHERE lista = 'tipos_evolucao' ORDER BY valor COLLATE NOCASE")],
                    "categorias": [r[0] for r in conn.execute("SELECT valor FROM opcoes WHERE lista = 'categorias_anexo' ORDER BY valor COLLATE NOCASE")],
                    "profissionais": [r[0] for r in conn.execute("SELECT valor FROM opcoes WHERE lista = 'profissionais' ORDER BY valor COLLATE NOCASE")],
                },
            )

    @app.post("/api/prontuario/<path:codigo>/evolucoes")
    @exige("operador")
    def evolucao_criar(codigo):
        d = request.get_json(silent=True) or {}
        texto, tipo = (d.get("texto") or "").strip(), (d.get("tipo") or "").strip()
        data = (d.get("data") or date.today().isoformat()).strip()
        try:
            date.fromisoformat(data)
        except ValueError:
            return jsonify(erro="Data inválida."), 400
        if not texto or not tipo:
            return jsonify(erro="Informe o tipo e o texto do registro."), 400
        if len(texto) > 20000:
            return jsonify(erro="Texto muito longo (máx. 20.000 caracteres)."), 400
        with connect() as conn:
            paciente_existe(conn, codigo)
            conn.execute(
                "INSERT INTO evolucoes (codigo_paciente, data, tipo, profissional, texto, autor, criado_em) VALUES (?,?,?,?,?,?,?)",
                (codigo, data, tipo, (d.get("profissional") or "").strip() or None, texto, usuario_atual()["nome"],
                 datetime.now().isoformat(timespec="seconds")),
            )
        return jsonify(ok=True)

    @app.delete("/api/evolucoes/<int:eid>")
    @exige("gestor")
    def evolucao_excluir(eid):
        with connect() as conn:
            conn.execute("DELETE FROM evolucoes WHERE id = ?", (eid,))
        return jsonify(ok=True)

    @app.post("/api/prontuario/<path:codigo>/anexos")
    @exige("operador")
    def anexo_criar(codigo):
        arq = request.files.get("file")
        categoria = (request.form.get("categoria") or "").strip()
        if not arq or not arq.filename or not categoria:
            return jsonify(erro="Selecione o arquivo e a categoria."), 400
        nome = Path(arq.filename.replace("\\", "/")).name[:150]
        ext = Path(nome).suffix.lower()
        if ext not in EXT_PERMITIDAS:
            return jsonify(erro="Tipo de arquivo não permitido. Aceitos: " + ", ".join(sorted(EXT_PERMITIDAS))), 400
        data_doc = (request.form.get("data_documento") or "").strip() or None
        if data_doc:
            try:
                date.fromisoformat(data_doc)
            except ValueError:
                return jsonify(erro="Data do documento inválida."), 400
        with connect() as conn:
            paciente_existe(conn, codigo)
        ANEXOS_DIR.mkdir(parents=True, exist_ok=True)
        guardado = uuid.uuid4().hex + ext
        destino = ANEXOS_DIR / guardado
        arq.save(destino)
        tamanho = destino.stat().st_size
        if tamanho == 0 or tamanho > MAX_UPLOAD:
            remover_arquivo(guardado)
            return jsonify(erro="Arquivo vazio ou acima do limite de 20 MB."), 400
        try:
            with connect() as conn:
                conn.execute(
                    "INSERT INTO anexos (codigo_paciente, categoria, descricao, data_documento, nome_original, arquivo, tamanho, enviado_por, criado_em) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (codigo, categoria, (request.form.get("descricao") or "").strip()[:300] or None, data_doc, nome, guardado,
                     tamanho, usuario_atual()["nome"], datetime.now().isoformat(timespec="seconds")),
                )
        except Exception:
            remover_arquivo(guardado)
            raise
        return jsonify(ok=True)

    @app.get("/anexos/<int:aid>")
    def anexo_baixar(aid):
        with connect() as conn:
            a = conn.execute("SELECT * FROM anexos WHERE id = ?", (aid,)).fetchone()
        if not a or not (ANEXOS_DIR / a["arquivo"]).is_file():
            abort(404)
        inline = Path(a["arquivo"]).suffix.lower() in EXT_INLINE and request.args.get("baixar") != "1"
        resp = send_from_directory(ANEXOS_DIR, a["arquivo"], download_name=a["nome_original"], as_attachment=not inline)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.delete("/api/anexos/<int:aid>")
    @exige("gestor")
    def anexo_excluir(aid):
        with connect() as conn:
            a = conn.execute("SELECT arquivo FROM anexos WHERE id = ?", (aid,)).fetchone()
            conn.execute("DELETE FROM anexos WHERE id = ?", (aid,))
        if a:
            remover_arquivo(a["arquivo"])
        return jsonify(ok=True)

    @app.route("/listas")
    @exige("gestor")
    def listas():
        return render_template("listas.html", ativa="listas", listas=LISTAS)

    @app.route("/usuarios")
    @exige("admin")
    def usuarios():
        return render_template("usuarios.html", ativa="usuarios", niveis=list(NIVEIS))

    # ---------- API: BI ----------
    @app.get("/api/bi")
    def api_bi():
        a = request.args
        return jsonify(bi.dashboard(a.get("ref"), a.get("periodo", "mes"), a.get("ini"), a.get("fim")))

    # ---------- API: opções ----------
    def todas_opcoes(conn) -> dict:
        out = {k: [] for k in LISTAS}
        for r in conn.execute("SELECT lista, valor FROM opcoes ORDER BY valor COLLATE NOCASE"):
            out.setdefault(r["lista"], []).append(r["valor"])
        out["@pacientes"] = [
            {"valor": r["codigo"], "rotulo": f'{r["codigo"]} - {r["nome"]}'}
            for r in conn.execute("SELECT codigo, nome FROM pacientes ORDER BY nome COLLATE NOCASE")
        ]
        return out

    @app.get("/api/opcoes")
    def api_opcoes():
        with connect() as conn:
            return jsonify(todas_opcoes(conn))

    @app.post("/api/opcoes/<lista>")
    @exige("gestor")
    def api_opcao_add(lista):
        valor = ((request.get_json(silent=True) or {}).get("valor") or "").strip()
        if lista not in LISTAS or not valor:
            return jsonify(erro="Informe um valor válido."), 400
        with connect() as conn:
            garantir_opcao(conn, lista, valor)
        return jsonify(ok=True)

    @app.delete("/api/opcoes/<lista>")
    @exige("gestor")
    def api_opcao_del(lista):
        valor = (request.get_json(silent=True) or {}).get("valor")
        if lista not in LISTAS:
            abort(404)
        with connect() as conn:
            conn.execute("DELETE FROM opcoes WHERE lista = ? AND valor = ?", (lista, valor))
        return jsonify(ok=True)

    # ---------- API: cadastros ----------
    @app.get("/api/meta/<ent>")
    def api_meta(ent):
        if ent not in ENTIDADES:
            abort(404)
        e = ENTIDADES[ent]
        return jsonify(
            titulo=e["titulo"], campos=e["campos"], colunas=e["tabela_cols"], filtro_mes=e.get("filtro_mes", False)
        )

    def limpar(ent: str, dados: dict) -> dict:
        e = ENTIDADES[ent]
        out = {}
        for c in e["campos"]:
            v = dados.get(c["nome"])
            v = v.strip() if isinstance(v, str) else v
            if v in ("", None):
                v = None
            elif c["tipo"] == "int":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    abort(400, f'{c["rotulo"]}: número inteiro inválido.')
            elif c["tipo"] == "money":
                try:
                    v = float(str(v).replace(",", "."))
                except ValueError:
                    abort(400, f'{c["rotulo"]}: valor inválido.')
            elif c["tipo"] == "date":
                try:
                    date.fromisoformat(v)
                except ValueError:
                    abort(400, f'{c["rotulo"]}: data inválida.')
            elif c["tipo"] in ("text", "select") and (lim := banco.limite(e["tabela"], c["nome"])) and len(v) > lim:
                abort(400, f'{c["rotulo"]}: máximo de {lim} caracteres.')
            elif c["tipo"] == "month" and not (len(v) == 7 and v[4] == "-" and v[:4].isdigit() and v[5:].isdigit()):
                abort(400, f'{c["rotulo"]}: mês inválido.')
            out[c["nome"]] = v
        for obrig in e["obrigatorios"]:
            if out.get(obrig) is None:
                rotulo = next(c["rotulo"] for c in e["campos"] if c["nome"] == obrig)
                abort(400, f"Preencha o campo obrigatório: {rotulo}.")
        return out

    def paciente_existe(conn, codigo) -> None:
        if not conn.execute("SELECT 1 FROM pacientes WHERE codigo = ?", (codigo,)).fetchone():
            abort(400, "Paciente não encontrado.")

    def sincronizar_paciente(conn, d: dict) -> None:
        if d.get("data_admissao") and not conn.execute(
            "SELECT 1 FROM movimentacao WHERE codigo_paciente = ? AND evento = 'Admissão' AND data = ?",
            (d["codigo"], d["data_admissao"]),
        ).fetchone():
            conn.execute(
                "INSERT INTO movimentacao (data, codigo_paciente, evento) VALUES (?, ?, 'Admissão')",
                (d["data_admissao"], d["codigo"]),
            )
        if d.get("data_alta"):
            evento = "Óbito" if (d.get("motivo_alta") or "").lower().startswith("óbito") else "Alta"
            if not conn.execute(
                "SELECT 1 FROM movimentacao WHERE codigo_paciente = ? AND evento IN ('Alta', 'Óbito') AND data = ?",
                (d["codigo"], d["data_alta"]),
            ).fetchone():
                conn.execute(
                    "INSERT INTO movimentacao (data, codigo_paciente, evento, motivo) VALUES (?, ?, ?, ?)",
                    (d["data_alta"], d["codigo"], evento, d.get("motivo_alta")),
                )

    def aplicar_movimento(conn, d: dict) -> None:
        cod, ev, data, motivo = d["codigo_paciente"], d["evento"], d["data"], d.get("motivo")
        if ev == "Admissão":
            conn.execute(
                "UPDATE pacientes SET data_admissao = ?, data_alta = NULL, motivo_alta = NULL WHERE codigo = ?", (data, cod)
            )
        elif ev in ("Alta", "Óbito"):
            conn.execute(
                "UPDATE pacientes SET data_alta = ?, motivo_alta = ? WHERE codigo = ?",
                (data, motivo or ("Óbito" if ev == "Óbito" else None), cod),
            )
        elif ev == "Retorno":
            conn.execute("UPDATE pacientes SET data_alta = NULL, motivo_alta = NULL WHERE codigo = ?", (cod,))

    def gravar(conn, ent: str, dados: dict, registro_id: int | None = None) -> int:
        """Valida vínculos, grava e sincroniza paciente/movimentação (sem notificar)."""
        e = ENTIDADES[ent]
        if ent == "movimentacao" and dados["evento"] not in EVENTOS:
            abort(400, "Evento inválido.")
        cols = list(dados)
        antigo = None
        if ent == "pacientes":
            if registro_id:
                antigo = conn.execute("SELECT codigo FROM pacientes WHERE id = ?", (registro_id,)).fetchone()
        else:
            paciente_existe(conn, dados["codigo_paciente"])
        if registro_id is None:
            cur = conn.execute(
                f'INSERT INTO {e["tabela"]} ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})',
                [dados[c] for c in cols],
            )
            registro_id = cur.lastrowid
        else:
            if not conn.execute(f'SELECT 1 FROM {e["tabela"]} WHERE id = ?', (registro_id,)).fetchone():
                abort(404)
            conn.execute(
                f'UPDATE {e["tabela"]} SET {",".join(c + "=?" for c in cols)} WHERE id = ?',
                [dados[c] for c in cols] + [registro_id],
            )
            if ent == "pacientes" and antigo and antigo["codigo"] != dados["codigo"]:
                for t in ("terapias", "movimentacao", "evolucoes", "anexos"):
                    conn.execute(
                        f"UPDATE {t} SET codigo_paciente = ? WHERE codigo_paciente = ?",
                        (dados["codigo"], antigo["codigo"]),
                    )
        if ent == "pacientes":
            sincronizar_paciente(conn, dados)
        elif ent == "movimentacao":
            aplicar_movimento(conn, dados)
        return registro_id

    def salvar(ent: str, registro_id: int | None):
        dados = limpar(ent, request.get_json(silent=True) or {})
        try:
            with connect() as conn:
                novo_id = gravar(conn, ent, dados, registro_id)
        except ErroIntegridade:
            msg = "Já existe um paciente com este código." if ent == "pacientes" else "Já existe registro para este paciente, terapia, profissional e mês."
            return jsonify(erro=msg), 409
        ig.notificar(WEBHOOK_EVENTO[ent][registro_id is not None], {**dados, "id": novo_id})
        return jsonify(ok=True, id=novo_id)

    @app.get("/api/<ent>")
    def api_listar(ent):
        if ent not in ENTIDADES:
            abort(404)
        e = ENTIDADES[ent]
        where, params = [], []
        q = request.args.get("q", "").strip()
        if q:
            where.append("(" + " OR ".join(f"LOWER({c}) LIKE LOWER(?)" for c in e["busca"]) + ")")
            params += [f"%{q}%"] * len(e["busca"])
        if e.get("filtro_mes") and request.args.get("mes"):
            where.append("mes = ?")
            params.append(request.args["mes"])
        sql = f'SELECT * FROM {e["tabela"]}' + (" WHERE " + " AND ".join(where) if where else "") + f' ORDER BY {e["ordem"]} LIMIT 2000'
        with connect() as conn:
            return jsonify([dict(r) for r in conn.execute(sql, params)])

    @app.post("/api/<ent>")
    @exige("operador")
    def api_criar(ent):
        if ent not in ENTIDADES:
            abort(404)
        return salvar(ent, None)

    @app.put("/api/<ent>/<int:rid>")
    @exige("operador")
    def api_editar(ent, rid):
        if ent not in ENTIDADES:
            abort(404)
        return salvar(ent, rid)

    @app.delete("/api/<ent>/<int:rid>")
    @exige("gestor")
    def api_excluir(ent, rid):
        if ent not in ENTIDADES:
            abort(404)
        with connect() as conn:
            if ent == "pacientes":
                p = conn.execute("SELECT codigo FROM pacientes WHERE id = ?", (rid,)).fetchone()
                if p:
                    for a in conn.execute("SELECT arquivo FROM anexos WHERE codigo_paciente = ?", (p["codigo"],)):
                        remover_arquivo(a["arquivo"])
                    for t in ("terapias", "movimentacao", "evolucoes", "anexos"):
                        conn.execute(f"DELETE FROM {t} WHERE codigo_paciente = ?", (p["codigo"],))
            conn.execute(f'DELETE FROM {ENTIDADES[ent]["tabela"]} WHERE id = ?', (rid,))
        return jsonify(ok=True)

    # ---------- API: usuários ----------
    @app.get("/api/usuarios")
    @exige("admin")
    def api_usuarios():
        with connect() as conn:
            rows = conn.execute("SELECT id, usuario, nome, nivel, ativo FROM usuarios ORDER BY nome COLLATE NOCASE")
            return jsonify([dict(r) for r in rows])

    @app.route("/api/usuarios", methods=["POST"])
    @app.route("/api/usuarios/<int:uid>", methods=["PUT"])
    @exige("admin")
    def api_usuario_salvar(uid=None):
        d = request.get_json(silent=True) or {}
        usuario, nome, nivel = (d.get("usuario") or "").strip(), (d.get("nome") or "").strip(), d.get("nivel")
        senha, ativo = d.get("senha") or "", 1 if d.get("ativo", 1) in (1, True, "1") else 0
        if not usuario or not nome or nivel not in NIVEIS:
            return jsonify(erro="Informe usuário, nome e nível de acesso."), 400
        if (uid is None or senha) and len(senha) < 6:
            return jsonify(erro="A senha deve ter ao menos 6 caracteres."), 400
        try:
            with connect() as conn:
                if uid is None:
                    conn.execute(
                        "INSERT INTO usuarios (usuario, nome, senha_hash, nivel, ativo, trocar_senha) VALUES (?,?,?,?,?,1)",
                        (usuario, nome, generate_password_hash(senha), nivel, ativo),
                    )
                else:
                    atual = conn.execute("SELECT nivel FROM usuarios WHERE id = ?", (uid,)).fetchone()
                    if not atual:
                        abort(404)
                    if uid == session["uid"] and (nivel != "admin" or not ativo):
                        return jsonify(erro="Você não pode rebaixar ou desativar a própria conta."), 400
                    conn.execute(
                        "UPDATE usuarios SET usuario=?, nome=?, nivel=?, ativo=? WHERE id=?", (usuario, nome, nivel, ativo, uid)
                    )
                    if senha:
                        conn.execute(
                            "UPDATE usuarios SET senha_hash=?, trocar_senha=1 WHERE id=?", (generate_password_hash(senha), uid)
                        )
                    if not conn.execute("SELECT 1 FROM usuarios WHERE nivel='admin' AND ativo=1").fetchone():
                        conn.rollback()
                        return jsonify(erro="Deve existir ao menos um administrador ativo."), 400
        except ErroIntegridade:
            return jsonify(erro="Este nome de usuário já existe."), 409
        return jsonify(ok=True)

    @app.delete("/api/usuarios/<int:uid>")
    @exige("admin")
    def api_usuario_excluir(uid):
        if uid == session["uid"]:
            return jsonify(erro="Você não pode excluir a própria conta."), 400
        with connect() as conn:
            conn.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
        return jsonify(ok=True)

    # ---------- integrações ----------
    def preparar(ent: str, bruto: dict) -> dict:
        """Mapeia cabeçalhos/chaves para campos do cadastro e normaliza os valores."""
        campos = {c["nome"]: c for c in ENTIDADES[ent]["campos"]}
        alias = {}
        for nome, c in campos.items():
            alias[nome] = nome
            alias[ig.norm(c["rotulo"])] = nome
        alias.update(EXTRA_ALIAS[ent])
        out = {}
        for chave, v in bruto.items():
            nome = alias.get(ig.norm(chave))
            if not nome or v is None or (isinstance(v, str) and not v.strip()):
                continue
            tipo = campos[nome]["tipo"]
            if tipo == "date":
                v = ig.valor_data(v)
            elif tipo == "month":
                v = ig.valor_mes(v)
            elif tipo in ("text", "select"):
                v = ig.valor_texto(v)
            out[nome] = v
        return out

    def upsert(conn, ent: str, dados_in: dict):
        e = ENTIDADES[ent]
        chaves = {"pacientes": ["codigo"], "terapias": ["mes", "codigo_paciente", "terapia"], "movimentacao": ["data", "codigo_paciente", "evento"]}[ent]
        if any(dados_in.get(k) in (None, "") for k in chaves):
            limpar(ent, dados_in)  # aborta com a mensagem de campo obrigatório
        filtro = " AND ".join(f"{k} = ?" for k in chaves)
        valores = [str(dados_in[k]) for k in chaves]
        if ent == "terapias":  # o mesmo paciente pode ter mais de um profissional na mesma terapia/mês
            filtro += " AND COALESCE(profissional, '') = ?"
            valores.append(str(dados_in.get("profissional") or ""))
        existente = conn.execute(f'SELECT * FROM {e["tabela"]} WHERE {filtro}', valores).fetchone()
        if ent == "movimentacao":
            if existente:
                return "ignorado", existente["id"], None
            dados = limpar(ent, dados_in)
            rid = gravar(conn, ent, dados)
            acao = "criado"
        else:
            base = {c["nome"]: existente[c["nome"]] for c in e["campos"]} if existente else {}
            dados = limpar(ent, {**base, **dados_in})
            rid = gravar(conn, ent, dados, existente["id"] if existente else None)
            acao = "atualizado" if existente else "criado"
        for c in e["campos"]:
            lista = c.get("lista")
            if lista and not lista.startswith("@") and dados.get(c["nome"]):
                garantir_opcao(conn, lista, dados[c["nome"]])
        return acao, rid, dados

    def processar(ent: str, linhas: list[dict]) -> dict:
        res = {"total": len(linhas), "criados": 0, "atualizados": 0, "ignorados": 0, "erros": []}
        eventos = []
        with connect() as conn:
            for i, bruto in enumerate(linhas, start=1):
                try:
                    if not isinstance(bruto, dict):
                        abort(400, "Registro deve ser um objeto.")
                    acao, rid, dados = upsert(conn, ent, preparar(ent, bruto))
                except HTTPException as exc:
                    res["erros"].append({"linha": i, "erro": exc.description})
                    continue
                except ErroIntegridade:
                    res["erros"].append({"linha": i, "erro": "Conflito de unicidade."})
                    continue
                res[{"criado": "criados", "atualizado": "atualizados", "ignorado": "ignorados"}[acao]] += 1
                if dados is not None:
                    eventos.append((WEBHOOK_EVENTO[ent][acao == "atualizado"], {**dados, "id": rid}))
        for ev, payload in eventos:
            ig.notificar(ev, payload)
        return res

    def chave_api(escopo: str):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                auth = request.headers.get("Authorization", "")
                token = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("X-API-Key", "")
                if not token:
                    return jsonify(erro="Chave de API ausente. Use o cabeçalho Authorization: Bearer <chave>."), 401
                with connect() as conn:
                    k = conn.execute("SELECT * FROM api_chaves WHERE hash = ? AND ativo = 1", (ig.hash_chave(token),)).fetchone()
                    if not k:
                        return jsonify(erro="Chave de API inválida ou revogada."), 401
                    if escopo == "escrita" and k["escopo"] != "escrita":
                        return jsonify(erro="Esta chave possui somente permissão de leitura."), 403
                    conn.execute("UPDATE api_chaves SET ultimo_uso = ? WHERE id = ?", (datetime.now().isoformat(timespec="seconds"), k["id"]))
                return fn(*a, **kw)

            return wrapper

        return deco

    def resposta_lote(res: dict):
        if res["erros"] and not (res["criados"] or res["atualizados"] or res["ignorados"]):
            return jsonify(res), 422
        return jsonify(res), 207 if res["erros"] else 200

    @app.get("/api/v1/indicadores")
    @chave_api("leitura")
    def v1_indicadores():
        return jsonify(bi.dashboard(request.args.get("ref"), request.args.get("periodo", "mes")))

    @app.get("/api/v1/<ent>")
    @chave_api("leitura")
    def v1_listar(ent):
        if ent not in ENTIDADES:
            return jsonify(erro="Recurso não encontrado."), 404
        e = ENTIDADES[ent]
        where, params = [], []
        for f in FILTROS_API[ent]:
            if request.args.get(f):
                where.append(f"{f} = ?")
                params.append(request.args[f])
        if ent == "pacientes" and request.args.get("ativo") in ("true", "false"):
            where.append("(data_alta IS NULL OR data_alta = '')" if request.args["ativo"] == "true" else "(data_alta IS NOT NULL AND data_alta <> '')")
        if ent == "movimentacao":
            if request.args.get("de"):
                where.append("data >= ?")
                params.append(request.args["de"])
            if request.args.get("ate"):
                where.append("data <= ?")
                params.append(request.args["ate"])
        if request.args.get("q"):
            where.append("(" + " OR ".join(f"LOWER({c}) LIKE LOWER(?)" for c in e["busca"]) + ")")
            params += [f'%{request.args["q"]}%'] * len(e["busca"])
        try:
            limite = max(1, min(int(request.args.get("limit", 100)), 1000))
            deslocamento = max(0, int(request.args.get("offset", 0)))
        except ValueError:
            return jsonify(erro="limit/offset inválidos."), 400
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        with connect() as conn:
            total = conn.execute(f'SELECT COUNT(*) FROM {e["tabela"]}{cond}', params).fetchone()[0]
            rows = conn.execute(f'SELECT * FROM {e["tabela"]}{cond} ORDER BY {e["ordem"]} LIMIT ? OFFSET ?', params + [limite, deslocamento])
            dados = [dict(r) for r in rows]
        return jsonify(total=total, limit=limite, offset=deslocamento, dados=dados)

    @app.post("/api/v1/<ent>")
    @chave_api("escrita")
    def v1_gravar(ent):
        if ent not in ENTIDADES:
            return jsonify(erro="Recurso não encontrado."), 404
        corpo = request.get_json(silent=True)
        linhas = corpo if isinstance(corpo, list) else [corpo] if isinstance(corpo, dict) else None
        if linhas is None or not linhas:
            return jsonify(erro="Envie um objeto JSON ou uma lista de objetos."), 400
        if len(linhas) > 1000:
            return jsonify(erro="Máximo de 1000 registros por requisição."), 400
        return resposta_lote(processar(ent, linhas))

    def importar_arquivo(ent: str):
        arq = request.files.get("file")
        if ent not in ENTIDADES or not arq:
            return jsonify(erro="Informe o recurso e o arquivo (campo 'file')."), 400
        try:
            linhas = ig.ler_planilha(arq.filename, arq.read())
        except ValueError as exc:
            return jsonify(erro=str(exc)), 400
        except Exception:
            return jsonify(erro="Não foi possível ler o arquivo. Verifique se é um .xlsx ou .csv válido."), 400
        return resposta_lote(processar(ent, linhas))

    @app.post("/api/v1/importar/<ent>")
    @chave_api("escrita")
    def v1_importar(ent):
        return importar_arquivo(ent)

    @app.post("/api/importar/<ent>")
    @exige("gestor")
    def api_importar(ent):
        return importar_arquivo(ent)

    @app.route("/integracoes")
    @exige("admin")
    def integracoes():
        return render_template("integracoes.html", ativa="integracoes", eventos=ig.EVENTOS_WEBHOOK, entidades={k: v["titulo"] for k, v in ENTIDADES.items()})

    @app.get("/api/integracoes/chaves")
    @exige("admin")
    def chaves_listar():
        with connect() as conn:
            rows = conn.execute("SELECT id, nome, prefixo, escopo, ativo, criado_em, ultimo_uso FROM api_chaves ORDER BY id DESC")
            return jsonify([dict(r) for r in rows])

    @app.post("/api/integracoes/chaves")
    @exige("admin")
    def chaves_criar():
        d = request.get_json(silent=True) or {}
        nome, escopo = (d.get("nome") or "").strip(), d.get("escopo")
        if not nome or escopo not in ("leitura", "escrita"):
            return jsonify(erro="Informe o nome e o escopo (leitura ou escrita)."), 400
        token, prefixo, h = ig.nova_chave()
        with connect() as conn:
            conn.execute(
                "INSERT INTO api_chaves (nome, prefixo, hash, escopo, criado_em) VALUES (?,?,?,?,?)",
                (nome, prefixo, h, escopo, datetime.now().isoformat(timespec="seconds")),
            )
        return jsonify(ok=True, chave=token)

    @app.route("/api/integracoes/chaves/<int:cid>", methods=["PUT", "DELETE"])
    @exige("admin")
    def chaves_alterar(cid):
        with connect() as conn:
            if request.method == "DELETE":
                conn.execute("DELETE FROM api_chaves WHERE id = ?", (cid,))
            else:
                ativo = 1 if (request.get_json(silent=True) or {}).get("ativo") else 0
                conn.execute("UPDATE api_chaves SET ativo = ? WHERE id = ?", (ativo, cid))
        return jsonify(ok=True)

    @app.get("/api/integracoes/webhooks")
    @exige("admin")
    def webhooks_listar():
        with connect() as conn:
            hooks = [dict(r) for r in conn.execute("SELECT * FROM webhooks ORDER BY id DESC")]
            log = [dict(r) for r in conn.execute(
                "SELECT l.*, w.nome FROM webhook_log l LEFT JOIN webhooks w ON w.id = l.webhook_id ORDER BY l.id DESC LIMIT 30")]
        return jsonify(webhooks=hooks, log=log)

    @app.route("/api/integracoes/webhooks", methods=["POST"])
    @app.route("/api/integracoes/webhooks/<int:wid>", methods=["PUT"])
    @exige("admin")
    def webhooks_salvar(wid=None):
        d = request.get_json(silent=True) or {}
        nome, url = (d.get("nome") or "").strip(), (d.get("url") or "").strip()
        eventos = [x for x in (d.get("eventos") or []) if x == "*" or x in ig.EVENTOS_WEBHOOK] or ["*"]
        if not nome or not url.lower().startswith(("http://", "https://")):
            return jsonify(erro="Informe um nome e uma URL http(s) válida."), 400
        ativo = 1 if d.get("ativo", True) else 0
        with connect() as conn:
            if wid is None:
                conn.execute(
                    "INSERT INTO webhooks (nome, url, eventos, segredo, ativo) VALUES (?,?,?,?,?)",
                    (nome, url, ",".join(eventos), secrets.token_hex(20), ativo),
                )
            else:
                conn.execute("UPDATE webhooks SET nome=?, url=?, eventos=?, ativo=? WHERE id=?", (nome, url, ",".join(eventos), ativo, wid))
        return jsonify(ok=True)

    @app.delete("/api/integracoes/webhooks/<int:wid>")
    @exige("admin")
    def webhooks_excluir(wid):
        with connect() as conn:
            conn.execute("DELETE FROM webhooks WHERE id = ?", (wid,))
            conn.execute("DELETE FROM webhook_log WHERE webhook_id = ?", (wid,))
        return jsonify(ok=True)

    @app.post("/api/integracoes/webhooks/<int:wid>/teste")
    @exige("admin")
    def webhooks_testar(wid):
        with connect() as conn:
            h = conn.execute("SELECT * FROM webhooks WHERE id = ?", (wid,)).fetchone()
        if not h:
            abort(404)
        ok, resultado = ig.testar(h)
        return jsonify(ok=ok, resultado=resultado)

    # ---------- banco de dados (SQLite / SQL Server / Oracle) ----------
    def _msg(exc: Exception) -> str:
        args = getattr(exc, "args", ())
        return str(args[1] if len(args) > 1 and isinstance(args[1], str) else exc)

    def _cfg_do_corpo():
        d = request.get_json(silent=True) or {}
        return d, banco.normalizar_cfg(d.get("cfg") or {}, banco.ler_config())

    def _ativar(cfg: dict) -> bool:
        """Passa a usar `cfg` (cria estrutura/listas se faltarem). Retorna True se a sessão atual foi invalidada."""
        anterior = banco.ler_config()
        banco.gravar_config(cfg)
        try:
            init_db()
        except Exception:
            banco.gravar_config(anterior)
            raise
        with connect() as conn:
            ainda = conn.execute("SELECT 1 FROM usuarios WHERE id = ? AND ativo = 1", (session.get("uid"),)).fetchone()
        if not ainda:
            session.clear()
        return not ainda

    @app.route("/banco")
    @exige("admin")
    def pagina_banco():
        return render_template("banco.html", ativa="banco", motores=banco.MOTORES)

    @app.get("/api/banco")
    @exige("admin")
    def api_banco_estado():
        cfg = banco.ler_config()
        try:
            with connect() as conn:
                info = {"versao": banco.versao(conn), "tabelas": banco.contagens(conn)}
        except Exception as exc:
            info = {"erro": _msg(exc)}
        try:
            import pyodbc  # noqa: F401
            tem_pyodbc = True
        except ImportError:
            tem_pyodbc = False
        try:
            import oracledb  # noqa: F401
            tem_oracle = True
        except ImportError:
            tem_oracle = False
        return jsonify(cfg=banco.cfg_publica(cfg), atual=info, drivers=banco.drivers_sqlserver(),
                       bibliotecas={"sqlserver": tem_pyodbc, "oracle": tem_oracle},
                       arquivo_padrao=str(banco.DB_PATH))

    @app.post("/api/banco/testar")
    @exige("admin")
    def api_banco_testar():
        try:
            d, cfg = _cfg_do_corpo()
            return jsonify(ok=True, **banco.testar(cfg, criar_banco=bool(d.get("criar_banco"))))
        except Exception as exc:
            return jsonify(erro=_msg(exc)), 400

    @app.post("/api/banco/migrar")
    @exige("admin")
    def api_banco_migrar():
        try:
            d, cfg = _cfg_do_corpo()
            if d.get("criar_banco") and cfg["motor"] == "sqlserver":
                banco.criar_banco_sqlserver(cfg)
            res = banco.migrar(banco.ler_config(), cfg, apagar_destino=bool(d.get("apagar_destino")))
            relogin = _ativar(cfg) if d.get("ativar") else False
            return jsonify(ok=True, ativado=bool(d.get("ativar")), relogin=relogin, **res)
        except Exception as exc:
            return jsonify(erro=_msg(exc)), 400

    @app.post("/api/banco/ativar")
    @exige("admin")
    def api_banco_ativar():
        try:
            d, cfg = _cfg_do_corpo()
            if d.get("criar_banco") and cfg["motor"] == "sqlserver":
                banco.criar_banco_sqlserver(cfg)
            banco.testar(cfg)
            return jsonify(ok=True, relogin=_ativar(cfg))
        except Exception as exc:
            return jsonify(erro=_msg(exc)), 400

    return app
