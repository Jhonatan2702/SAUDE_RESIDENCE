from __future__ import annotations

from werkzeug.security import generate_password_hash

from .banco import BASE_DIR, DATA_DIR, DB_PATH, Conexao, ErroIntegridade, conectar, criar_estrutura  # noqa: F401

LISTAS = {
    "operadoras": "Operadoras",
    "empresas": "Empresas",
    "profissionais": "Profissionais",
    "diagnosticos": "Diagnósticos",
    "motivos_alta": "Motivos de alta",
    "complexidades": "Complexidade",
    "servicos": "Serviços",
    "situacoes": "Situações",
    "frequencias": "Frequências",
    "terapias": "Terapias",
    "modalidades": "Modalidades",
    "tipos_evolucao": "Tipos de registro do prontuário",
    "categorias_anexo": "Categorias de anexo",
}

SEEDS = {
    "tipos_evolucao": ["Evolução", "Anamnese", "Intercorrência", "Orientação", "Visita", "Observação"],
    "categorias_anexo": ["Documento", "Exame", "Receita", "Laudo", "Relatório", "Outros"],
    "complexidades": ["Básico", "Intermediário", "Intensivo"],
    "terapias": ["PSICO", "NUTRI", "TO", "FONO", "FISIO"],
    "situacoes": ["Pendente", "Realizada", "Cancelada", "Suspensa"],
    "frequencias": ["Diária", "Semanal", "Quinzenal", "Mensal"],
    "modalidades": ["Domiciliar", "Ambulatorial", "Teleatendimento"],
    "motivos_alta": ["Alta clínica", "Óbito", "Transferência", "Desistência", "Perda de elegibilidade"],
}

EVENTOS = ["Admissão", "Alta", "Óbito", "Internação", "Retorno"]
NIVEIS = {"consulta": 1, "operador": 2, "gestor": 3, "admin": 4}


def connect() -> Conexao:
    return conectar()


def garantir_opcao(conn: Conexao, lista: str, valor: str) -> None:
    """Insere o valor na lista suspensa se ainda não existir (portável entre os motores)."""
    try:
        conn.execute(
            f"INSERT INTO opcoes (lista, valor) SELECT ?, ? {conn.dual} "
            "WHERE NOT EXISTS (SELECT 1 FROM opcoes WHERE lista = ? AND valor = ?)",
            (lista, valor, lista, valor),
        )
    except ErroIntegridade:
        conn.rollback()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        criar_estrutura(conn)
        for lista, valores in SEEDS.items():
            for v in valores:
                garantir_opcao(conn, lista, v)
        if not conn.execute("SELECT 1 FROM usuarios").fetchone():
            conn.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, nivel, trocar_senha) "
                "VALUES ('admin', 'Administrador', ?, 'admin', 1)",
                (generate_password_hash("admin"),),
            )