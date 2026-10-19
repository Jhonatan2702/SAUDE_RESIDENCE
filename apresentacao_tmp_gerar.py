"""Gera a apresentação demonstrativa do TST-GESTÃO (capturas reais + dados fictícios)."""
from __future__ import annotations

import os
import random
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp())
os.environ["TST_DATA_DIR"] = str(TMP / "dados")
sys.path.insert(0, str(RAIZ))

from tst_gestao.app import ANEXOS_DIR, create_app  # noqa: E402
from tst_gestao.db import connect  # noqa: E402

SAIDA = RAIZ / "apresentacao"
SHOTS = TMP / "shots"
SHOTS.mkdir(parents=True)
SAIDA.mkdir(exist_ok=True)
HOJE = date(2026, 10, 19)
random.seed(7)


def semear() -> None:
    nomes = ["Maria", "José", "Ana", "João", "Antônia", "Francisco", "Luiza", "Pedro", "Helena", "Carlos", "Rita", "Paulo",
             "Joana", "Marcos", "Sandra", "Roberto", "Lúcia", "Fernando", "Teresa", "Rafael"]
    sob = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Ribeiro", "Almeida", "Carvalho"]
    bairros = ["Centro", "Boa Viagem", "Casa Forte", "Madalena", "Espinheiro", "Graças", "Imbiribeira", "Torre"]
    cidades = ["Recife"] * 6 + ["Olinda", "Jaboatão", "Paulista"]
    oper = ["Unimed", "Bradesco Saúde", "SulAmérica", "Amil", "Particular"]
    diag = ["AVC", "DPOC", "Insuficiência cardíaca", "Fratura de fêmur", "Alzheimer", "Pós-operatório", "Diabetes"]
    serv = ["Home Care", "Internação domiciliar", "Monitoramento"]
    cx = ["Básico", "Intermediário", "Intensivo"]
    profs = ["Dra. Camila (Fono)", "Dr. Rodrigo (Fisio)", "Dra. Beatriz (Nutri)", "Dr. Henrique (Psico)", "Dra. Larissa (TO)"]
    with connect() as c:
        c.execute("UPDATE usuarios SET trocar_senha = 0")
        for tabela, valores in {"operadoras": oper, "diagnosticos": diag, "servicos": serv, "profissionais": profs,
                                "empresas": ["Vida Plena", "Reabilita+"]}.items():
            c.executemany("INSERT OR IGNORE INTO opcoes (lista, valor) VALUES (?, ?)", [(tabela, v) for v in valores])
        for i in range(1, 61):
            adm = HOJE - timedelta(days=random.randint(0, 330))
            nasc = date(random.randint(1935, 2005), random.randint(1, 12), random.randint(1, 28))
            alta = motivo = None
            if random.random() < 0.3:
                alta = min(HOJE, adm + timedelta(days=random.randint(5, 120)))
                motivo = random.choice(["Alta clínica", "Alta clínica", "Óbito", "Transferência", "Desistência"])
            nome = f"{random.choice(nomes)} {random.choice(sob)}"
            cod = f"P{i:03d}"
            c.execute(
                "INSERT INTO pacientes (codigo,nome,nascimento,sexo,bairro,cidade,operadora,diagnostico,complexidade,servico,"
                "data_admissao,data_alta,motivo_alta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cod, nome, nasc.isoformat(), random.choice("FM"), random.choice(bairros), random.choice(cidades), random.choice(oper),
                 random.choice(diag), random.choices(cx, [5, 3, 2])[0], random.choice(serv), adm.isoformat(),
                 alta.isoformat() if alta else None, motivo))
            c.execute("INSERT INTO movimentacao (data,codigo_paciente,evento) VALUES (?,?,'Admissão')", (adm.isoformat(), cod))
            if alta:
                c.execute("INSERT INTO movimentacao (data,codigo_paciente,evento,motivo) VALUES (?,?,?,?)",
                          (alta.isoformat(), cod, "Óbito" if motivo == "Óbito" else "Alta", motivo))
            if not alta:
                for t in random.sample(["PSICO", "NUTRI", "TO", "FONO", "FISIO"], random.randint(1, 3)):
                    for mes in ("2026-09", "2026-10"):
                        c.execute(
                            "INSERT INTO terapias (mes,codigo_paciente,terapia,modalidade,empresa,profissional,situacao,sessoes,"
                            "frequencia,valor,agendado,relatorio) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (mes, cod, t, "Domiciliar", random.choice(["Vida Plena", "Reabilita+"]), random.choice(profs),
                             random.choice(["Pendente", "Realizada", "Realizada", "Suspensa"]), random.randint(4, 16),
                             random.choice(["Semanal", "Diária", "Quinzenal"]), random.choice([180, 220, 260]),
                             random.choice(["Sim", "Não"]), random.choice(["Sim", "Não"])))
        # paciente de destaque para o prontuário
        c.execute("UPDATE pacientes SET nome='Maria das Graças Oliveira', nascimento='1948-03-12', sexo='F', bairro='Boa Viagem', "
                  "cidade='Recife', operadora='Unimed', diagnostico='AVC', complexidade='Intensivo', servico='Home Care', "
                  "data_admissao='2026-09-02', data_alta=NULL, motivo_alta=NULL WHERE codigo='P001'")
        c.execute("DELETE FROM movimentacao WHERE codigo_paciente='P001'")
        c.execute("INSERT INTO movimentacao (data,codigo_paciente,evento) VALUES ('2026-09-02','P001','Admissão')")
        c.execute("INSERT INTO movimentacao (data,codigo_paciente,evento,motivo) VALUES ('2026-09-28','P001','Internação','Pneumonia aspirativa')")
        c.execute("INSERT INTO movimentacao (data,codigo_paciente,evento,motivo) VALUES ('2026-10-03','P001','Retorno','Alta hospitalar')")
        evo = [("2026-09-02", "Anamnese", "Dr. Rodrigo (Fisio)", "Paciente admitida com sequela de AVC isquêmico, hemiparesia à direita. Orientados cuidadores quanto a mudança de decúbito."),
               ("2026-10-05", "Evolução", "Dra. Camila (Fono)", "Boa aceitação de dieta pastosa, sem sinais de broncoaspiração. Mantida terapia de deglutição 3x/semana."),
               ("2026-10-15", "Evolução", "Dra. Beatriz (Nutri)", "Peso estável. Ajustado aporte proteico; orientada hidratação fracionada.")]
        for d, t, p, tx in evo:
            c.execute("INSERT INTO evolucoes (codigo_paciente,data,tipo,profissional,texto,autor,criado_em) VALUES ('P001',?,?,?,?,?,?)",
                      (d, t, p, tx, "Administrador", d + "T10:00:00"))
        ANEXOS_DIR.mkdir(parents=True, exist_ok=True)
        for i, (cat, desc, nome) in enumerate([("Exame", "Hemograma completo", "hemograma.pdf"), ("Receita", "Prescrição médica", "receita.pdf"),
                                              ("Laudo", "Tomografia de crânio", "tomografia.pdf")]):
            arq = f"demo{i}.pdf"
            (ANEXOS_DIR / arq).write_bytes(b"%PDF-1.4 demo")
            c.execute("INSERT INTO anexos (codigo_paciente,categoria,descricao,data_documento,nome_original,arquivo,tamanho,enviado_por,criado_em) "
                      "VALUES ('P001',?,?,?,?,?,?,?,?)", (cat, desc, f"2026-10-{10 + i:02d}", nome, arq, 120000 + i * 40000, "Administrador", f"2026-10-{10 + i:02d}T09:00:00"))
        c.execute("INSERT INTO usuarios (usuario,nome,senha_hash,nivel,ativo) SELECT 'ana.gestora','Ana Gestora',senha_hash,'gestor',1 FROM usuarios WHERE usuario='admin'")
        c.execute("INSERT INTO usuarios (usuario,nome,senha_hash,nivel,ativo) SELECT 'carlos.op','Carlos Operador',senha_hash,'operador',1 FROM usuarios WHERE usuario='admin'")
        c.execute("INSERT INTO usuarios (usuario,nome,senha_hash,nivel,ativo) SELECT 'leitura','Consulta BI',senha_hash,'consulta',1 FROM usuarios WHERE usuario='admin'")
        c.execute("INSERT INTO api_chaves (nome,prefixo,hash,escopo,criado_em,ultimo_uso) VALUES ('Sistema financeiro','tst_Ab3xK9','h1','leitura','2026-10-10T09:00:00','2026-10-19T08:15:00')")
        c.execute("INSERT INTO api_chaves (nome,prefixo,hash,escopo,criado_em,ultimo_uso) VALUES ('Integração operadora','tst_Qw8Lm2','h2','escrita','2026-10-12T14:30:00','2026-10-18T17:02:00')")
        c.execute("INSERT INTO webhooks (nome,url,eventos,segredo) VALUES ('ERP hospitalar','https://erp.exemplo.com/hooks/tst','paciente.criado,movimentacao.criada','a1b2c3d4e5f6a7b8c9d0')")
        c.execute("INSERT INTO webhook_log (webhook_id,evento,ok,resultado,criado_em) VALUES (1,'paciente.criado',1,'HTTP 200','2026-10-19T09:41:00')")
        c.execute("INSERT INTO webhook_log (webhook_id,evento,ok,resultado,criado_em) VALUES (1,'movimentacao.criada',1,'HTTP 200','2026-10-19T10:12:00')")


def capturar() -> list[tuple[str, str]]:
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server

    srv = make_server("127.0.0.1", 8815, create_app(), threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8815"
    feitos = []

    def shot(page, nome):
        page.wait_for_timeout(900)
        page.screenshot(path=str(SHOTS / f"{nome}.png"))
        feitos.append(nome)

    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge")
        page = nav.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base + "/login")
        shot(page, "login")
        page.fill("input[name=usuario]", "admin")
        page.fill("input[name=senha]", "admin")
        page.click("button[type=submit]")
        page.wait_for_url(base + "/")
        page.wait_for_timeout(1500)
        shot(page, "dashboard1")
        page.mouse.wheel(0, 370)
        shot(page, "dashboard2")
        page.mouse.wheel(0, 1000)
        shot(page, "dashboard3")
        page.goto(base + "/cadastro/pacientes")
        page.wait_for_selector("#tbl tbody tr")
        shot(page, "pacientes")
        page.click("#novo")
        shot(page, "novo_paciente")
        page.goto(base + "/paciente/P001")
        page.wait_for_selector(".tl-item")
        shot(page, "prontuario")
        page.click("[data-tab=anexos]")
        shot(page, "anexos")
        page.goto(base + "/cadastro/terapias")
        page.wait_for_selector("#tbl tbody tr")
        shot(page, "terapias")
        page.goto(base + "/cadastro/movimentacao")
        page.wait_for_selector("#tbl tbody tr")
        shot(page, "movimentacao")
        page.goto(base + "/listas")
        page.select_option("#lista", "motivos_alta")
        shot(page, "listas")
        page.goto(base + "/usuarios")
        page.wait_for_selector("#tb tr")
        shot(page, "usuarios")
        page.goto(base + "/integracoes")
        page.wait_for_selector("#tb-chaves tr")
        shot(page, "integracoes1")
        page.mouse.wheel(0, 720)
        shot(page, "integracoes2")
        nav.close()
    srv.shutdown()
    return feitos


def montar() -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu, Inches, Pt

    NAVY, AZUL, CLARO = RGBColor(0x0B, 0x12, 0x20), RGBColor(0x1E, 0xA7, 0xF0), RGBColor(0xDB, 0xE7, 0xF3)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    vazio = prs.slide_layouts[6]
    logo = str(RAIZ / "logotst.png")

    def fundo(s, cor):
        f = s.background.fill
        f.solid()
        f.fore_color.rgb = cor

    def texto(s, x, y, w, h, txt, tam, cor, negrito=False):
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        r = tf.paragraphs[0].add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = txt, Pt(tam), negrito, cor, "Segoe UI"
        return tf

    def slide_capa(titulo, sub, rodape=""):
        s = prs.slides.add_slide(vazio)
        fundo(s, NAVY)
        s.shapes.add_picture(str(SHOTS / "bg.jpg"), 0, 0, prs.slide_width, prs.slide_height) if (SHOTS / "bg.jpg").exists() else None
        s.shapes.add_picture(logo, Inches(5.67), Inches(0.9), height=Inches(2.2))
        texto(s, 0.5, 3.4, 12.3, 1.0, titulo, 48, RGBColor(255, 255, 255), True).paragraphs[0].alignment = 2
        t2 = texto(s, 1.5, 4.5, 10.3, 1.2, sub, 20, CLARO)
        t2.paragraphs[0].alignment = 2
        if rodape:
            texto(s, 0.5, 6.7, 12.3, 0.5, rodape, 13, NAVY).paragraphs[0].alignment = 2
        return s

    def slide_tela(num, titulo, pontos, img):
        s = prs.slides.add_slide(vazio)
        fundo(s, RGBColor(0xF2, 0xF5, 0xF9))
        barra = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.95))
        barra.fill.solid()
        barra.fill.fore_color.rgb = NAVY
        barra.line.fill.background()
        s.shapes.add_picture(logo, Inches(0.35), Inches(0.12), height=Inches(0.72))
        texto(s, 1.2, 0.17, 9, 0.7, titulo, 26, RGBColor(255, 255, 255), True)
        texto(s, 11.6, 0.27, 1.5, 0.5, f"{num:02d}", 20, AZUL, True).paragraphs[0].alignment = 3
        # captura (16:9) à direita, pontos à esquerda
        largura = Inches(8.4)
        altura = int(largura * 900 / 1440)
        pic = s.shapes.add_picture(str(SHOTS / f"{img}.png"), Inches(4.65), Inches(1.45), largura, altura)
        pic.line.color.rgb, pic.line.width = RGBColor(0xCB, 0xD5, 0xE1), Pt(1)
        tf = texto(s, 0.45, 1.45, 4.0, 5.6, "", 14, NAVY)
        for i, p in enumerate(pontos):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            par.space_after = Pt(10)
            r = par.add_run()
            r.text, r.font.size, r.font.name, r.font.color.rgb = "▸ " + p, Pt(15), "Segoe UI", NAVY
        return s

    # bg da capa
    import shutil
    shutil.copy(RAIZ / "background.jpg", SHOTS / "bg.jpg")
    slide_capa("TST-GESTÃO", "Gestão de pacientes, terapias e indicadores assistenciais em uma única plataforma local, segura e profissional.",
               "Apresentação demonstrativa · dados fictícios")
    prs.slides[0].shapes
    slides = [
        ("Acesso seguro por login", ["Tela de login corporativa com a identidade TST", "Senhas protegidas por hash; troca obrigatória no 1º acesso",
                                     "Proteção contra requisições forjadas (CSRF)", "Atalho na Área de Trabalho e ícone na bandeja do Windows — sem terminal"], "login"),
        ("Painel BI — visão executiva", ["Pacientes ativos, admissões, altas e óbitos por dia, mês e ano",
                                         "Taxa de mortalidade mensal e anual", "Data de referência ajustável para qualquer período"], "dashboard1"),
        ("Pendências e motivos de alta", ["Pendências por terapia no mês: Psico, Nutri, TO, Fono e Fisio",
                                          "Principais motivos de alta (dia, mês ou ano)", "Complexidade com percentual (Básico / Intermediário / Intensivo)",
                                          "Pacientes por faixa etária e idade média"], "dashboard2"),
        ("Perfil da carteira de pacientes", ["Pacientes por bairro, cidade e diagnóstico", "Pacientes por serviço e por operadora de saúde",
                                             "Cruzamento serviço × operadora"], "dashboard3"),
        ("Cadastro de pacientes", ["Busca instantânea por código, nome, bairro, cidade ou diagnóstico", "Acesso direto ao prontuário em cada linha",
                                   "Permissões: consulta, operador, gestor e admin"], "pacientes"),
        ("Formulário com listas suspensas", ["Operadora, diagnóstico, complexidade e serviço padronizados", "Validação de datas e campos obrigatórios",
                                             "Admissão e alta geram a movimentação automaticamente"], "novo_paciente"),
        ("Prontuário e linha do tempo", ["Ficha completa do paciente com idade e situação", "Evoluções, movimentações, terapias e anexos em ordem cronológica",
                                         "Filtros por tipo de registro", "Cada registro guarda autor e data/hora"], "prontuario"),
        ("Documentos, exames e receitas", ["Anexe PDF, imagens, Word e Excel (até 20 MB)", "Categorias: Documento, Exame, Receita, Laudo, Relatório, Outros",
                                           "Abrir/baixar apenas com login; arquivos validados por tipo"], "anexos"),
        ("Terapias por paciente × mês", ["Modalidade, empresa, profissional, situação e frequência", "Sessões, valor, agendado e relatório",
                                         "Filtro por mês e busca rápida"], "terapias"),
        ("Movimentação de pacientes", ["Admissão, alta, óbito, internação e retorno", "Base dos indicadores de altas, admissões e mortalidade",
                                       "Registrar o evento atualiza o paciente"], "movimentacao"),
        ("Listas suspensas configuráveis", ["Operadoras, empresas, profissionais, diagnósticos, motivos de alta, serviços e mais",
                                            "Gestores adicionam ou removem opções sem suporte técnico"], "listas"),
        ("Usuários e níveis de acesso", ["Consulta · Operador · Gestor · Admin", "Ativação/desativação e redefinição de senha",
                                         "Proteção contra remover o último administrador"], "usuarios"),
        ("Integrações por API — chaves e webhooks", ["Chaves de API com escopo de leitura ou escrita", "Webhooks assinados (HMAC-SHA256) com histórico de entregas",
                                                      "Acesso restrito à máquina local (127.0.0.1)"], "integracoes1"),
        ("Importação de planilhas e documentação", ["Importe Excel/CSV de pacientes, terapias e movimentações", "Relatório de linhas criadas, atualizadas e com erro",
                                                    "Exemplos prontos de uso da API na própria tela"], "integracoes2"),
    ]
    for i, (t, pts, img) in enumerate(slides, start=1):
        slide_tela(i, t, pts, img)

    s = slide_capa("Obrigado!", "TST-GESTÃO · Sistema local com SQLite, painel BI, prontuário e integrações por API.",
                   "Abra pelo atalho TST-GESTÃO · Primeiro acesso: admin / admin")
    destino = SAIDA / "TST-GESTAO_Apresentacao.pptx"
    prs.save(destino)
    return destino


if __name__ == "__main__":
    from tst_gestao.db import init_db

    init_db()
    semear()
    capturar()
    print(montar())
