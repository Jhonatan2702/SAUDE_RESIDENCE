# TST-GESTÃO

Painéis de acompanhamento (Flask + SQLite) alimentados **exclusivamente** pela URL de dados da Saúde Residence.

O sistema não tem cadastro próprio de pacientes. O banco local (SQLite) guarda apenas:
- os **usuários** e seus perfis de acesso;
- o **espelho da URL** (tabelas `dadosbi_*`), atualizado na inicialização e **a cada hora**.

> A primeira versão do projeto era baseada na planilha do Google Planilhas. Na versão 2 foram removidos cadastros manuais, importação de planilhas, prontuário, listas suspensas, relatórios sobre a planilha, API de entrada/saída, webhooks e a troca para SQL Server/Oracle: tudo vem da URL. Na primeira execução da versão 2, as tabelas antigas saem do banco e uma cópia completa fica em `dados\backup_antes_v2_*.db`.

## Instalação e uso
- **Instalar:** duplo clique em `install.bat` (Python 3.10+, ambiente `.venv`, dependências e atalhos na Área de Trabalho).
- **Usar:** duplo clique no atalho **TST-GESTÃO**. O ícone fica na bandeja do Windows (duplo clique abre; botão direito → Sair).
- **Primeiro acesso:** `admin` / `admin`, com troca de senha obrigatória.
- **Rede local:** em outros computadores, acesse `http://IPv4-DO-SERVIDOR:8765` (libere a porta TCP 8765 no firewall, rede privada).
- **Executável:** `build_exe.bat` gera `dist\TST-GESTAO.exe`. Os dados ficam em `dist\dados`, fora do EXE.

> O espelho só é atualizado enquanto o aplicativo está aberto. Deixe o TST-GESTÃO rodando no computador servidor.

> **Primeira instalação:** copie `dist\config.json` (gerado junto com o `.exe`) para a pasta `dados` do cliente: a URL da Saúde Residence já vem configurada e fica **fixa** na tela de *Integração com a URL*, com o botão *Alterar endereço* para mudar à mão se preciso. A URL fica só em `dados\config.json`, nunca dentro do programa, que é publicado para as atualizações, e as atualizações automáticas preservam esse arquivo.

## Atualizações automáticas (com assinatura digital)
Só o computador servidor precisa ser atualizado: quem acessa pelo navegador já vê a versão nova.

**No computador do cliente (administrador):** quando existe versão nova, aparece o aviso *"Nova versão disponível"*. Em *Integração com a URL → Atualizações do sistema* você vê as novidades e clica em **Atualizar agora**, que pede confirmação. O sistema baixa, confere a assinatura e reinicia em segundos. A pasta `dados` é mantida, e a versão anterior fica guardada como `TST-GESTAO.antigo.exe`: para voltar, feche o aplicativo e renomeie esse arquivo para `TST-GESTAO.exe`. A consulta é automática a cada 6 horas, ou pelo botão *Buscar atualizações* (também no menu do ícone da bandeja).

**Assinatura digital:** cada versão é assinada com uma chave que só existe no computador de quem publica (`chaves\atualizacao_privada.pem`). O sistema instalado tem a chave pública correspondente e **recusa qualquer arquivo que não tenha sido assinado por ela**. Assim, mesmo que alguém troque o arquivo no GitHub, a atualização falsa não é instalada.
- **Faça backup da pasta `chaves\`** (pen drive ou cofre de senhas). Sem ela, os computadores instalados não aceitarão novas versões e será preciso reinstalar manualmente.
- A pasta `chaves\` está no `.gitignore` e nunca deve ir para o GitHub.

**Para publicar uma versão nova (no seu computador):**
1. Aumente `VERSAO` em `tst_gestao/versao.py` (ex.: `2.1.0` → `2.1.1`).
2. Rode `publicar_atualizacao.bat "O que mudou nesta versão"`. Ele gera o `.exe`, assina e publica no repositório **público** de versões `Jhonatan2702/tst-gestao-atualizacoes` (só os executáveis, sem código-fonte nem dados).
3. A publicação automática usa um token do GitHub em `chaves\github_token.txt`. Sem token, o script mostra o passo a passo para publicar pela página do GitHub.

## Avisos da sincronização (pop-up e sino)
A cada sincronização bem-sucedida, `notificacoes.py` compara a situação com a sincronização anterior e grava **só o que mudou**:
- 🔴 **Crítico** (fica na tela até fechar): óbitos registrados; bairros com paciente de terapia indicada e nenhum profissional em 180 dias; falha na sincronização (só administrador).
- 🟠 **Atenção:** novos pacientes com terapia pendente; relatórios que passaram de 60 dias; orçamentos que venceram (só gestor e administrador).
- 🔵 **Informação:** novas admissões (destacando quem tem terapia indicada); altas; campos novos na URL (só administrador).

Aparecem como pop-up no canto (no máximo 3, os mais graves primeiro) e ficam guardados no **sino** do menu, com contador de não lidos. A primeira sincronização só registra a situação, para não avisar sobre o passado.

## Ajuda dentro do sistema
- **Tour de boas-vindas:** abre sozinho no primeiro acesso de cada usuário e mostra menu, atualização dos dados, filtro de período, abas e como abrir as listas de pacientes.
- **Tour de cada aba:** na primeira visita a uma aba aparece um convite; o botão **Tour desta tela**, no topo, refaz o tour quando quiser. O conteúdo dos tours fica em `tst_gestao/static/guia.js` e o teste `tests/test_ajuda.py` confere se todo elemento citado existe na tela.
- **Ajuda e primeiros passos** (menu): como começar, de onde vêm os dados, rotina sugerida (diária, semanal, mensal), o que cada tela responde (com atalho para o tour), glossário e perguntas frequentes. Mostra só o que o perfil do usuário enxerga.

## Perfis de acesso
| Perfil | Página inicial | Acesso |
|---|---|---|
| **Operacional** | Painel operacional | Relatórios pendentes · Profissional × atendimento · Região de abrangência · Fichas realizadas no App · Tabela de preços |
| **Gestor** | Painel BI | Painel BI completo + Painel operacional |
| **Administrador** | Painel BI | Tudo, incluindo Usuários e Integração com a URL |

Os níveis da versão anterior (Consulta e Operador) são convertidos automaticamente para **Operacional**.

## Painel BI (Gestor e Administrador)
Organizado em abas; todo número é clicável e abre a lista de pacientes que o compõe (com busca e exportação CSV).

- **Visão geral:** pacientes ativos, pacientes com terapias, monitoramento com terapias, mortalidade, pacientes com terapia pendente, admissões e altas com terapias (com o total do período como observação), visitas, ativos sem visita (só Monitoramento, ID, Plantão e Serv. Prof. Não Méd.) e relatórios pendentes dos 2 últimos meses (no detalhe, caixas "Somente <ano>" e "Somente 2 últimos meses" vêm marcadas); séries mensais de visitas e de admissões, altas e óbitos.
- **Resumo do profissional e do paciente:** busca rápida no topo dos painéis, ou clique no nome em qualquer lista. O do profissional traz visitas, pacientes, dias, bairros, zonas, pacientes pendentes, relatórios e evolução mensal. O do paciente traz dados, situação de cada terapia, atendimentos e orçamentos, profissionais, histórico de visitas, relatórios e evolução mensal. Links diretos: `?profissional=Nome` e `?paciente=Nome`.
- **Ficha do bairro:** clicar num bairro (mapa, rankings, tabelas de abrangência) abre zonas, profissionais, pacientes com terapias e pendências, relatórios e operadoras do bairro, descendo até o histórico de cada paciente. Link direto: `/painel?bairro=Meireles#mapa`.
- **Mapa por bairro:** mapa de Fortaleza pintado pelo indicador escolhido (pacientes ativos, em terapia, terapia pendente, visitas, profissionais, relatórios pendentes), com filtro por terapia, destaque de uma zona de atendimento e ranking de bairros e de zonas.
- **Terapias:** número de pacientes por terapia (Fisio, Fono, TO, Nutri, Psico), pacientes com terapia pendente por terapia e visitas do período por terapia.
- **Complexidade:** Básico (1–2 terapias), Intermediário (3) e Intensivo (4 ou mais), com o cruzamento complexidade × terapia.
- **Movimentação e mortalidade:** quadro dia · mês · ano, motivos de alta, mortalidade por mês e lista de **quem foi a óbito** no período.
- **Perfil dos pacientes:** operadoras, serviços, diagnósticos, faixa etária, cidades e mapa de bairros de Fortaleza.
- **Profissionais:** profissional × atendimentos, relatórios pendentes por terapia e disponibilidade de bairro por profissional.

## Regras de cálculo
- **Atendimento:** episódio enviado pela URL (id da admissão). **Paciente:** pessoa distinta, identificada pelo nome normalizado (sem acento, maiúsculas e espaços extras), porque a URL não envia CPF ou código. Homônimos são contados como uma pessoa.
- **Ativo na data:** atendimento admitido até a data e sem alta até ela; sem data de alta, vale o status da URL.
- **Terapia:** especialidade da visita (Fisioterapia → FISIO, Fonoaudiologia → FONO, Terapeuta Ocupacional → TO, Nutricionista → NUTRI, Psicólogo → PSICO).
- **Pacientes por terapia:** pacientes ativos com ao menos uma visita da terapia nos **últimos 90 dias** até a data final, contando só visitas de atendimentos **ativos**: a alta encerra o ciclo, e visitas de um atendimento encerrado não geram pendência, mesmo se o paciente for readmitido.
- **Complexidade:** quantidade de terapias diferentes que o paciente ativo recebeu nos últimos 90 dias.
- **Terapia pendente:** paciente ativo indicado com terapias (`possuiterapias = SIM`) que fez a terapia nos últimos 90 dias, mas está há mais de **5 dias** sem visita dela. Também conta quem é indicado com terapias e não teve nenhuma visita de terapia em 90 dias.
- **Monitoramento com terapias:** pacientes ativos no serviço *Monitoramento* com `possuiterapias = SIM`.
- **Mortalidade:** pacientes que foram a óbito no período (condição de alta “Óbito”) ÷ pacientes atendidos no período (admitidos até o fim e sem alta antes do início) × 100.
- **Altas:** não incluem óbitos, que são contados à parte.
- **Bairro:** convertido para o nome oficial dos 121 bairros de Fortaleza (erros de digitação, abreviações e nomes antigos estão em `ALIAS_BAIRRO`, em `fonte.py`). Bairros de outras cidades ficam como vieram.
- **Cobertura de um bairro ou zona:** “Atendendo no período” = profissional com visita lá dentro do período. “Cobre o bairro/zona” = atendeu alguém lá nos **últimos 180 dias** (`JANELA_COBERTURA`, em `fonte.py`), mesmo sem visita agora. No mapa de cobertura, contorno **laranja** = descoberto no período mas com quem cubra; **vermelho** = ninguém em 180 dias.
- **Altas por bairro e por profissional:** atendimentos com data de alta no período (sem óbitos), pelo bairro do atendimento; na ficha do profissional, as altas dos pacientes que ele atendeu nos últimos 180 dias.
- **Zona de atendimento:** campo `zoneamento` da URL (id, nome e bairros). Pacientes contam pela zona do atendimento mais recente que tenha zona.
- **Orçamento:** situação do orçamento de cada atendimento ativo na data final: vencido (fim antes da data), vence em até 7 dias, em 8 a 30 dias, vigente por mais de 30 dias ou sem orçamento.

## Painel operacional (todos os perfis)
- **Relatórios pendentes:** lista atual da URL, com filtros por terapia e busca, agrupada por terapia, profissional e competência (as mais antigas primeiro).
- **Profissional × atendimento:** profissionais com visitas no período; clique para ver os pacientes de cada um.
- **Região de abrangência:** mapa de cobertura (profissionais por bairro, bairros sem cobertura em vermelho, região de um profissional escolhido), cobertura por **zona de atendimento** e tabela profissional × zona × bairro. É a cobertura observada nas visitas, não a agenda do profissional.
- **Fichas realizadas no App:** cada visita enviada pela URL é uma ficha registrada no App.
- **Tabela de preços:** aguardando a URL enviar valores por empresa.

## Campos da URL e onde são usados
A URL libera campos aos poucos; o monitor de alterações (Integração com a URL) avisa quando surge um campo novo.

| Campo | Desde | Uso |
|---|---|---|
| `id`, `nmpaciente`, `status`, `dataadmissao`, `dataalta`, `condicaoalta` | início | pacientes ativos, admissões, altas, óbitos e mortalidade |
| `nmoperadora`, `nmservico`, `possuiterapias` | início | perfil, monitoramento com terapias, pendências |
| `datainicioorcamento`, `datafimorcamento` | início | situação dos orçamentos (desde a versão 2) |
| `visitas[]` (data, profissional, especialidade) | início | terapias, complexidade, pendências, profissionais, fichas, abrangência |
| `idade`, `diagnostico`, `complexidade`, `cidade`, `bairro` | 05/11/2026 | perfil dos pacientes, mapa, complexidade informada |
| `relatoriospendentes[]` | 05/11/2026 | relatórios pendentes |
| `zoneamento` (id, nome, bairros) | 18/11/2026 | zonas de atendimento no mapa e na cobertura |

Não usados de propósito: `idoperadora` e `idespecialidade` (o nome já identifica) e `relatoriospendentes[].id` (exibido só na lista).

## O que a URL ainda não envia
Preços por empresa, tipo de ficha ou relatório realizado, situação detalhada da terapia (frequência, sessões), telefone, data de nascimento e um identificador único do paciente. Quando a equipe de dados incluir esses campos, o **monitor de alterações** (Integração com a URL) avisa que surgiram campos novos.

## Integração com a URL (Administrador)
- Status da última sincronização, botão **Sincronizar agora** e contagem do espelho.
- **Monitor de alterações:** compara campos, tipos e categorias a cada resposta, sem guardar dados de pacientes.
- A URL é configurada na própria tela (fica em `dados\config.json`) ou pela variável `TST_DADOSBI_URL`. A URL atual usa **HTTP sem criptografia**: solicite HTTPS à equipe de dados.
- Registros que deixam de vir na resposta não são apagados, para que uma resposta parcial não esvazie os painéis.

## Hospedagem no Render (site) com banco no Neon
O mesmo código também roda como site. O executável continua igual, com SQLite. No servidor, o sistema usa PostgreSQL (Neon gratuito) **sempre que a variável `DATABASE_URL` existir**, porque o disco do Render gratuito é apagado a cada reinício e os usuários se perderiam.

| Arquivo | Para quê |
|---|---|
| `wsgi.py` | entrada do servidor (`gunicorn wsgi:app`): sem janela, sem bandeja e sem atualizador (a versão nova chega pelo deploy) |
| `requirements-servidor.txt` | dependências do servidor (Flask, psycopg, gunicorn) |
| `render.yaml` | configuração do serviço no Render (plano gratuito, região Virginia, 1 worker) |

Variáveis de ambiente no Render:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | connection string do Neon (`postgresql://...`) |
| `TST_ADMIN_SENHA` | senha do **primeiro** login do `admin` (troca obrigatória no 1º acesso). Sem ela o site não sobe: no servidor nunca existe admin/admin |
| `TST_DADOSBI_URL` | URL da Saúde Residence (no servidor ela vem daqui, não da tela de Integração) |
| `SECRET_KEY` | gerada pelo Render; mantém as sessões abertas entre reinícios |
| `TST_HOSPEDADO` | `1`: cookies só por HTTPS, atrás do proxy do Render |

- **Um worker só:** a sincronização de hora em hora roda dentro do processo, e cada worker a mais repetiria a rotina.
- **Plano gratuito dorme:** depois de cerca de 15 minutos sem acesso, o Render desliga o site, e a sincronização de hora em hora para. Um serviço como o cron-job.org chamando `/saude` a cada 10 minutos mantém o site acordado. A rota `/saude` não abre o banco, então o Neon continua livre para dormir.
- **Testar no Postgres localmente:** defina `DATABASE_URL` e `TST_ADMIN_SENHA` e rode o pytest. Os mesmos testes valem para os dois bancos.

## Backup
No executável, o banco fica em `dados\tst_gestao.db`. Como o espelho é refeito pela URL, o essencial no backup é a tabela de usuários: copie o arquivo com o aplicativo fechado.

## Estrutura do código
```
main.py                  inicialização: servidor, janela, bandeja e agendamento do espelho
tst_gestao/
  app.py                 cria a aplicação e registra as áreas
  seguranca.py           sessão, CSRF e perfis de acesso
  espelho.py             sincronização da URL → banco local, monitor de formato e status
  fonte.py               leitura do espelho (com cache) e regras comuns (paciente, ativo, terapia)
  painel.py              cálculos do Painel BI e detalhamentos
  operacional.py         cálculos do Painel operacional
  banco.py, db.py        SQLite (executável) ou PostgreSQL (DATABASE_URL), estrutura e inicialização
wsgi.py                  entrada do servidor na hospedagem (Render)
  rotas/                 auth.py · paineis.py · admin.py
  templates/, static/    telas; app.css é o sistema de design (tokens → componentes → páginas)
tests/                   pytest com uma URL simulada (cenário controlado)
```

## Testes
`.venv\Scripts\python.exe -m pytest tests`

## Dados e privacidade
A pasta `dados\` contém nomes e diagnósticos de pacientes e a chave de sessão; `_arquivo\` guarda documentos de trabalho (planilha, PDFs, apresentação). As duas estão no `.gitignore` e **não devem ser versionadas nem enviadas ao GitHub**.
