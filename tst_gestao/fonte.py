"""Leitura do espelho da URL e regras comuns a todos os painéis.

Conceitos usados em todo o sistema:
- **Atendimento**: um episódio enviado pela URL (id da admissão). A mesma pessoa pode ter vários.
- **Paciente**: pessoa distinta, identificada pelo nome normalizado (a URL não envia CPF/código).
- **Ativo na data**: atendimento admitido até a data e sem alta até ela (sem data de alta, vale o status da URL).
- **Terapia**: especialidade das visitas (Fisio, Fono, TO, Nutri, Psico).
"""
from __future__ import annotations

import json
from collections import Counter
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from datetime import date, timedelta

from .db import connect

JANELA_TERAPIA = 90   # dias que definem "paciente em terapia" e a complexidade
JANELA_ATRASO = 15    # dias sem visita de uma terapia em andamento = pendente
JANELA_COBERTURA = 180  # profissional "cobre" um bairro se visitou alguém lá nesses dias (mesmo sem visita no período)
FAIXAS_IDADE = [("0-17", 0, 17), ("18-39", 18, 39), ("40-59", 40, 59), ("60-79", 60, 79), ("80+", 80, 130)]
TERAPIAS = ["FISIO", "FONO", "TO", "NUTRI", "PSICO"]
NOMES_TERAPIA = {"FISIO": "Fisioterapia", "FONO": "Fonoaudiologia", "TO": "Terapia ocupacional",
                 "NUTRI": "Nutrição", "PSICO": "Psicologia"}
# Complexidade pela quantidade de terapias diferentes nos últimos JANELA_TERAPIA dias
NIVEIS = [("Básico", 1, 2), ("Intermediário", 3, 3), ("Intensivo", 4, 99)]


def sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def chave_paciente(nome: str) -> str:
    return " ".join(sem_acento(nome).casefold().split())


# ---------------------------------------------------------------- bairros de Fortaleza
def _bairros_oficiais() -> set[str]:
    """Os 121 bairros oficiais, lidos da mesma base cartográfica usada no mapa."""
    try:
        geo = json.loads((Path(__file__).parent / "static" / "fortaleza-bairros.geojson").read_text(encoding="utf-8"))
        return {" ".join(sem_acento(f["properties"]["bairro"]).upper().split()) for f in geo["features"]}
    except (OSError, ValueError, KeyError):
        return set()


BAIRROS_OFICIAIS = _bairros_oficiais()
# grafias que a URL envia → nome oficial (erros de digitação, abreviações e nomes antigos)
ALIAS_BAIRRO = {
    "ALAGADICO": "SAO GERARDO", "ALAGADICO NOVO": "JOSE DE ALENCAR", "JOSE ALENCAR": "JOSE DE ALENCAR",
    "BAIRRO DE FATIMA": "FATIMA", "NOSSA SENHORA DE FATIMA": "FATIMA",
    "BAIRRO DE LOURDES": "DE LOURDES", "DE LURDES": "DE LOURDES", "LOURDES": "DE LOURDES",
    "BELLA VISTA": "BELA VISTA", "CASTELAO": "BOA VISTA-CASTELAO", "BOA VISTA- CASTELAO": "BOA VISTA-CASTELAO",
    "CIDADE DOS FUCIONARIOS": "CIDADE DOS FUNCIONARIOS", "CONJUNTO CEARA": "CONJUNTO CEARA I", "CONJ. CEARA": "CONJUNTO CEARA I",
    "DIONISIO TORRRES": "DIONISIO TORRES", "EDSON QUIROZ": "EDSON QUEIROZ",
    "LUCIANO CAVALCANTE": "ENGENHEIRO LUCIANO CAVALCANTE", "LUCIANO CAVALCANTI": "ENGENHEIRO LUCIANO CAVALCANTE",
    "ENG LUCIANO CAVALCANTE": "ENGENHEIRO LUCIANO CAVALCANTE", "JACAREGANGA": "JACARECANGA", "JARDIM CEARENSCE": "JARDIM CEARENSE",
    "JOQUEI": "JOQUEI CLUBE", "JOSE WALTER": "PREFEITO JOSE WALTER", "MANOEL DIAS BRANCO": "MANUEL DIAS BRANCO",
    "MANUEL SATIRO": "MANOEL SATIRO", "MODUBIM": "MONDUBIM", "MODUMBIM": "MONDUBIM", "PLANALTO AIRTON SENA": "PLANALTO AYRTON SENNA",
    "PRAIA DO FUTURO": "PRAIA DO FUTURO I", "PRAIA DO FUTURO 1": "PRAIA DO FUTURO I", "PRAIA DO FUTURO 2": "PRAIA DO FUTURO II",
    "PRES. KENNEDY": "PRESIDENTE KENNEDY", "PRESIDENTE KENEDDY": "PRESIDENTE KENNEDY", "PRESIDENTE KENEDY": "PRESIDENTE KENNEDY",
    "SAO JOAO DO TAUAPE": "TAUAPE", "SAO JOAO TAUAPE": "TAUAPE", "SAPIRANGA": "SAPIRANGA-COITE", "COITE": "SAPIRANGA-COITE",
    "VICENTE PIZON": "VICENTE PINZON", "VINCENTE PINZON": "VICENTE PINZON",
    "VILA ELLERY": "ELLERY", "VILLA ELLERY": "ELLERY", "VILA PERY": "VILA PERI",
    # grafias usadas nas listas de bairros do zoneamento
    "ENG. LUCIANO CAVALCANTE": "ENGENHEIRO LUCIANO CAVALCANTE", "QUINTINHO CUNHA": "QUINTINO CUNHA",
    "PQ PRESIDENTE VARGAS": "PARQUE PRESIDENTE VARGAS", "PREF. JOSE WALTER": "PREFEITO JOSE WALTER",
    "GUAJIRU": "GUAJERU", "GENIBAU": "PARQUE GENIBAU",
}


def bairro_padrao(texto: str | None) -> str | None:
    """Nome do bairro sem acento, em maiúsculas e, quando possível, igual ao nome oficial de Fortaleza.

    Tenta o texto inteiro, o texto antes de "(" e cada parte separada por vírgula, "/" ou " - ".
    Bairros de outras cidades (ou não reconhecidos) ficam como vieram, só padronizados.
    """
    t = " ".join(sem_acento(texto or "").upper().replace("´", "'").split()).strip(" .,;-")
    if not any(c.isalpha() for c in t):
        return None  # lixo como "." ou "..."
    candidatos = [t, t.split("(")[0]]
    for sep in (",", "/", " - "):
        candidatos += t.split("(")[0].split(sep)
    for c in candidatos:
        c = " ".join(c.split()).strip(" .,;-")
        c = ALIAS_BAIRRO.get(c, c)
        if c in BAIRROS_OFICIAIS:
            return c
    return t


def terapia(especialidade: str | None) -> str:
    """Sigla da terapia a partir do nome da especialidade enviado pela URL."""
    e = sem_acento(especialidade or "").lower()
    for trecho, sigla in (("fisio", "FISIO"), ("fono", "FONO"), ("ocupacional", "TO"), ("nutri", "NUTRI"), ("psic", "PSICO")):
        if trecho in e:
            return sigla
    return (especialidade or "Não informada").strip()


def nivel(qtd_terapias: int) -> str | None:
    for rotulo, minimo, maximo in NIVEIS:
        if minimo <= qtd_terapias <= maximo:
            return rotulo
    return None


def data(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def br(d: date | str | None) -> str:
    if isinstance(d, str):
        d = data(d)
    return d.strftime("%d/%m/%Y") if d else ""


def faixa_idade(valor) -> str | None:
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    if not n.is_integer():
        return None
    for rotulo, minimo, maximo in FAIXAS_IDADE:
        if minimo <= int(n) <= maximo:
            return rotulo
    return None


def eh_obito(a: dict) -> bool:
    return "bito" in (a["condicao_alta"] or "").lower()


def eh_monitoramento(a: dict) -> bool:
    return (a["servico"] or "").strip().lower().startswith("monitoramento")


def tem_terapias(a: dict) -> bool:
    return (a["possui_terapias"] or "").strip().upper() in ("SIM", "S")


def ativo_em(a: dict, dia: date) -> bool:
    adm, alta = a["_adm"], a["_alta"]
    if adm and adm > dia:
        return False
    if alta:
        return alta > dia
    return (a["status_origem"] or "").upper() != "ALTA"


def em_fortaleza(a: dict) -> bool:
    cidade = sem_acento(a.get("cidade") or "").casefold().strip()
    return not cidade or "fortaleza" in cidade


@dataclass
class Base:
    atend: list[dict]
    visitas: list[dict]
    sincronizado: str | None
    zonas: dict[str, dict] = field(default_factory=dict)  # {id: {"nome", "bairros": [nomes oficiais]}}
    por_id: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self):
        self.por_id = {a["origem_id"]: a for a in self.atend}

    def ativos(self, dia: date) -> list[dict]:
        return [a for a in self.atend if ativo_em(a, dia)]

    def visitas_entre(self, ini: date, fim: date) -> list[dict]:
        return [v for v in self.visitas if ini <= v["_data"] <= fim]

    def terapias_por_paciente(self, fim: date, dias: int = JANELA_TERAPIA, so_atendimentos: set[str] | None = None) -> dict[str, dict[str, date]]:
        """{paciente: {terapia: data da última visita}} nos `dias` até `fim`.

        `so_atendimentos`: considera só as visitas desses atendimentos (ex.: os ativos). Assim a alta encerra o ciclo:
        visitas de um atendimento que já recebeu alta não contam para "em terapia" nem para pendência.
        """
        ini = fim - timedelta(days=dias - 1)
        saida: dict[str, dict[str, date]] = {}
        for v in self.visitas:
            if ini <= v["_data"] <= fim and (so_atendimentos is None or v["atendimento_origem_id"] in so_atendimentos):
                a = self.por_id.get(v["atendimento_origem_id"])
                if not a:
                    continue
                atual = saida.setdefault(a["_pac"], {})
                if v["_ter"] not in atual or v["_data"] > atual[v["_ter"]]:
                    atual[v["_ter"]] = v["_data"]
        return saida

    def relatorios_pendentes(self) -> list[dict]:
        saida = []
        for a in self.atend:
            for r in a["_relatorios"]:
                saida.append({**r, "atendimento": a["origem_id"], "paciente": a["nome_paciente"],
                              "operadora": a["operadora"], "bairro": a["bairro"], "terapia": terapia(r.get("especialidade"))})
        return saida


_cache: dict = {"chave": None, "base": None}
_trava = threading.Lock()


def _zonas(atend: list[dict]) -> dict[str, dict]:
    """Catálogo das zonas de atendimento enviadas pela URL (a mesma zona vem repetida em cada atendimento)."""
    zonas: dict[str, dict] = {}
    for a in atend:
        if not a["zona_id"] or a["zona_id"] in zonas:
            continue
        partes = (a["zona_bairros"] or "").replace("\n", ",").split(",")
        bairros = [b for b in (bairro_padrao(x) for x in partes) if b]
        zonas[a["zona_id"]] = {"id": a["zona_id"], "nome": (a["zona_nome"] or a["zona_id"]).strip(), "bairros": sorted(set(bairros))}
    repetidos = Counter(z["nome"].upper() for z in zonas.values())
    for z in zonas.values():  # nomes iguais (ex.: duas zonas "SOBRAL") recebem o id para diferenciar
        if repetidos[z["nome"].upper()] > 1:
            z["nome"] = f"{z['nome']} ({z['id']})"
    return zonas


def carregar() -> Base:
    """Lê o espelho uma vez por sincronização (cache invalidado quando a URL traz dados novos)."""
    with connect() as conn:
        chave = tuple(conn.execute(
            "SELECT (SELECT COUNT(*) FROM dadosbi_atendimentos), (SELECT MAX(sincronizado_em) FROM dadosbi_atendimentos), "
            "(SELECT COUNT(*) FROM dadosbi_visitas_origem), (SELECT MAX(sincronizado_em) FROM dadosbi_visitas_origem) "
            + conn.dual).fetchone())
        with _trava:
            if _cache["chave"] == chave:
                return _cache["base"]
        atend = [dict(r) for r in conn.execute(
            "SELECT origem_id, nome_paciente, operadora, servico, status_origem, data_admissao, data_alta, condicao_alta, "
            "possui_terapias, idade, diagnostico, complexidade, cidade, bairro, relatorios_pendentes_json, "
            "inicio_orcamento, fim_orcamento, zona_id, zona_nome, zona_bairros FROM dadosbi_atendimentos ORDER BY id")]
        visitas = [dict(r) for r in conn.execute(
            "SELECT atendimento_origem_id, profissional_id, profissional, especialidade, data_visita FROM dadosbi_visitas_origem ORDER BY id")]
    for a in atend:
        a["_adm"], a["_alta"] = data(a["data_admissao"]), data(a["data_alta"])
        a["_pac"] = chave_paciente(a["nome_paciente"])
        a["_relatorios"] = json.loads(a.pop("relatorios_pendentes_json") or "[]")
        for campo in ("operadora", "servico", "diagnostico", "complexidade", "condicao_alta"):
            a[campo] = (a[campo] or "").strip() or None
        a["bairro"] = bairro_padrao(a["bairro"])  # a URL envia o mesmo bairro com várias grafias
        a["cidade"] = " ".join(sem_acento(a["cidade"] or "").upper().split()) or None
        a["_orc_ini"], a["_orc_fim"] = data(a["inicio_orcamento"]), data(a["fim_orcamento"])
        a["zona"] = a["zona_id"] or None
    # um único nome de exibição por paciente: a grafia mais frequente, preferindo a que não está toda em maiúsculas
    grafias: dict[str, Counter] = {}
    for a in atend:
        grafias.setdefault(a["_pac"], Counter())[" ".join(a["nome_paciente"].split())] += 1
    nome = {p: max(c.items(), key=lambda kv: (kv[1], not kv[0].isupper(), kv[0]))[0] for p, c in grafias.items()}
    for a in atend:
        a["nome_paciente"] = nome[a["_pac"]]
    for v in visitas:
        v["_data"], v["_ter"] = data(v["data_visita"]), terapia(v["especialidade"])
    visitas = [v for v in visitas if v["_data"]]
    base = Base(atend, visitas, chave[1], zonas=_zonas(atend))
    with _trava:
        _cache.update(chave=chave, base=base)
    return base


def periodo(ini: date | None, fim: date | None) -> tuple[date, date]:
    fim = fim or date.today()
    ini = ini or fim.replace(day=1)
    return (fim, ini) if ini > fim else (ini, fim)
