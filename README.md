# TST-GESTÃO

Sistema de gestão local (Flask + SQLite) com login, níveis de acesso, cadastros e painel BI.

## Instalação (para quem baixar o projeto)
Dê duplo clique em **`install.bat`**: ele localiza (ou instala via winget) o Python 3.10+, cria o ambiente `.venv`, instala as dependências e cria os atalhos **TST-GESTÃO** na Área de Trabalho. Requer Windows e internet na primeira vez.

## Gerar executável para Windows
Execute **`build_exe.bat`** depois de instalar o projeto. O script cria um executável único em `dist\TST-GESTAO.exe`; Python não precisa estar instalado no computador que vai executar o arquivo. Para distribuição, envie o EXE (e opcionalmente um atalho para ele). O primeiro uso cria `dist\dados` ao lado do executável. Essa pasta contém o banco, configurações e anexos, portanto deve ser mantida e incluída nos backups; ela não é embutida no EXE. A geração exige internet para instalar o PyInstaller na primeira vez.

## Uso
- Dê duplo clique no atalho **TST-GESTÃO** (Área de Trabalho ou pasta do projeto). Nenhum terminal é aberto.
- O ícone aparece na bandeja do Windows (clique duplo = abrir, botão direito = Sair).
- Primeiro acesso: `admin` / `admin` (a troca de senha é obrigatória).
- Para recriar os atalhos: `.venv\Scripts\python.exe criar_atalhos.py`.
- **Acesso pela rede local:** inicie o TST-GESTÃO no computador que hospeda os dados. Nesse computador, execute `ipconfig` e anote o endereço IPv4 da rede local. Nos outros dispositivos conectados à mesma rede, acesse `http://ENDEREÇO-IPv4:8765` (por exemplo, `http://192.168.1.25:8765`). Se o Windows perguntar, permita o acesso em redes privadas; caso não apareça o aviso e a conexão falhe, crie uma regra de entrada no Firewall do Windows para a porta TCP `8765`, limitada à rede privada.

## Níveis de acesso
Consulta (visualiza) · Operador (cadastra/edita) · Gestor (exclui e gerencia listas) · Admin (tudo + usuários).

## Dados
Banco em `dados\tst_gestao.db` (faça backup copiando este arquivo). Erros de inicialização: `dados\erro.log`.

## Regras do BI
- Altas, admissões e óbitos vêm da tabela MOVIMENTACAO; cadastrar admissão/alta no paciente gera o evento automaticamente, e registrar o evento atualiza o paciente.
- Distribuições (bairro, cidade, complexidade, idade, diagnóstico, serviço, operadora) consideram pacientes ativos (sem data de alta).
- Mortalidade = óbitos do período ÷ pacientes expostos no período (admitidos até o fim e sem alta antes do início).
- Pendências = terapias do mês atual com situação “Pendente” de pacientes ativos.

## Integrações API (menu *Integrações API*, somente Admin)
- **Chaves de API** (leitura ou escrita) geradas na tela; a chave é exibida uma única vez e guardada apenas como hash.
- **Saída:** `GET /api/v1/pacientes|terapias|movimentacao` (filtros, `limit`/`offset`) e `GET /api/v1/indicadores`.
- **Entrada:** `POST /api/v1/pacientes|terapias|movimentacao` (objeto ou lista, upsert) e `POST /api/v1/importar/<recurso>` (.xlsx/.csv). A tela também permite importar planilhas.
- **Webhooks:** POST JSON assinado (`X-TST-Signature: sha256=HMAC`) nos eventos `paciente.criado/atualizado`, `terapia.criada/atualizada`, `movimentacao.criada`.
- **Saúde Residence BI:** a aplicação sincroniza pacientes e visitas na inicialização e a cada hora; Admin também pode sincronizar pela tela. O ID externo vira o código local, e cada visita é registrada uma única vez como evolução do tipo “Visita”. Campos não fornecidos pela origem são preservados e pacientes ausentes na resposta não são excluídos. A URL padrão é a fornecida pela equipe; pode ser substituída pela variável `TST_DADOSBI_URL`. A URL atual usa HTTP sem criptografia: solicite HTTPS antes de transmitir dados pessoais/de saúde e restrinja o acesso à rede autorizada.
- A aplicação escuta na rede local na porta `8765`. Exemplos completos na própria tela.

## Prontuário do paciente
- Botão **Prontuário** em cada linha de *Pacientes*: ficha, **linha do tempo** (evoluções, movimentações, terapias e anexos), evoluções e anexos.
- Registros clínicos (operador+): tipo, profissional e texto, com autor e data/hora; não são editáveis, apenas excluídos por Gestor+.
- Anexos (operador+): documentos, exames, receitas, laudos, relatórios e outros (pdf, imagens, doc/docx, xls/xlsx, csv, txt; até 20 MB). Ficam em `dados\anexos\` — inclua essa pasta no backup junto com o `.db`.
- Os tipos de registro e as categorias de anexo são editáveis em *Listas suspensas*.

## Banco de dados (menu *Banco de dados*, somente Admin)
Permite testar, criar a estrutura, migrar os dados e passar a usar **SQL Server** ou **Oracle** no lugar do SQLite.
- SQL Server: requer ODBC Driver 17/18; o banco pode ser criado pela tela (inclui LocalDB `(localdb)\MSSQLLocalDB`).
- Oracle: o usuário/schema precisa existir com permissão de criar tabelas (conexão direta, sem Oracle Client).
- A migração preserva os códigos, confere as contagens e desfaz tudo em caso de erro. Anexos continuam em `dados\anexos`.
- A configuração fica em `dados\banco.json` (senha protegida pelo Windows). Para voltar ao SQLite, apague esse arquivo.
- Validado em SQL Server real (LocalDB); Oracle validado por testes de tradução de SQL/DDL.

## Testes
`.venv\Scripts\python.exe -m pytest tests`

## Relatórios

Menu **Relatórios** (todos os níveis de acesso): um relatório para cada análise do Painel BI (altas, motivos de alta, admissões, pendências por terapia, mortalidade, bairro/cidade, complexidade, idade, diagnóstico, serviço/operadora) e três listagens (pacientes, terapias, movimentação).

- Filtros por período (dia/mês/ano + data de referência), mês ou situação, conforme o relatório.
- **Imprimir / Salvar PDF**: layout A4 paisagem com cabeçalho, logo, filtros, data/usuário e numeração de páginas. Na janela de impressão escolha "Salvar como PDF".
- **CSV (Excel)**: exporta as mesmas tabelas (separador `;`, UTF-8).
