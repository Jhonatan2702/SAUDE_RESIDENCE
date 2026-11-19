/* Conteúdo dos tours guiados. Cada tour: nome, resumo (convite) e passos {alvo, card, aba, titulo, texto, nivel}.
   alvo = seletor CSS do elemento destacado (sem alvo = caixa central); card = destacar o card inteiro;
   aba = abre essa aba antes do passo; nivel = só para perfis a partir desse nível (2 gestor, 3 admin). */
window.GUIA = {
  'boas-vindas': {
    nome: 'Boas-vindas', resumo: 'Conheça as partes principais da ferramenta.',
    passos: [
      {titulo: 'Bem-vindo ao TST-GESTÃO 👋',
        texto: '<p>Aqui você acompanha pacientes, terapias e equipe com os dados que vêm direto do sistema da Saúde Residence.</p>' +
          '<p><b>Nada é digitado aqui:</b> a cada hora o sistema busca as informações novas sozinho. Este tour leva cerca de 1 minuto.</p>'},
      {alvo: '.menu nav', titulo: 'Menu', texto: '<p>As páginas que o seu perfil pode abrir. O <b>Painel BI</b> é a visão de gestão; o <b>Painel operacional</b> reúne as listas do dia a dia.</p><p>A <b>Ajuda</b>, no fim do menu, tem o guia completo.</p>'},
      {alvo: '#sino', titulo: 'Avisos', texto: '<p>A cada sincronização, o sistema compara os dados com os anteriores e avisa o que <b>mudou e pede atenção</b>: óbitos, altas, novas admissões, novas pendências de terapia, bairros sem profissional, relatórios atrasados e orçamentos vencidos.</p><p>O aviso aparece no canto da tela: <b>vermelho</b> é crítico e fica até você fechar; os outros somem sozinhos. Todos ficam guardados aqui no sino.</p>'},
      {alvo: '.sinc', titulo: 'Quando os dados foram atualizados', texto: '<p>Mostra a última vez que os dados chegaram do sistema do cliente. Verde = tudo certo.</p><p>Se ficar <b>vermelho</b> ou a hora estiver muito antiga, avise o administrador: os números podem estar desatualizados.</p>'},
      {alvo: '#busca-global', titulo: 'Busca rápida', texto: '<p>Digite parte do nome de um <b>paciente</b> ou <b>profissional</b> para abrir o resumo completo dele.</p><p>Exemplos: terapias e pendências do paciente, ou os pacientes, bairros e relatórios do profissional.</p>'},
      {alvo: '#periodo', titulo: 'Filtro de período', texto: '<p>Escolha o intervalo analisado: <b>Este mês</b>, <b>Mês anterior</b>, <b>90 dias</b>, <b>Ano</b> ou datas livres.</p><p>Vale para a página inteira e fica guardado para a próxima vez.</p>'},
      {alvo: '.abas', titulo: 'Abas', texto: '<p>Cada aba responde a um tipo de pergunta. Na primeira vez em cada aba aparece um convite para um tour curto dela.</p>'},
      {alvo: '.kpi[data-det]', card: true, titulo: 'Todo número leva às pessoas', texto: '<p>Cards com <b>“Ver pacientes →”</b>, barras, linhas de tabela e bairros do mapa são clicáveis.</p>' +
          '<p>Abre a lista de quem compõe o número, com <b>busca</b> e <b>Exportar CSV</b> (abre no Excel). Clique num paciente ou profissional para abrir o <b>resumo completo</b> dele, e dali navegue para os outros.</p>'},
      {alvo: '.info', titulo: 'Como o número é calculado', texto: '<p>Passe o mouse no <b>ⓘ</b> ao lado de cada título para ler a regra de cálculo em linguagem simples.</p>'},
      {alvo: '#btn-tour', titulo: 'Reveja quando quiser', texto: '<p><b>Tour desta tela</b> refaz o tour da aba aberta. <b>Ajuda</b> abre o guia completo, com rotinas sugeridas e glossário.</p><p>Bom trabalho!</p>'},
    ],
  },

  // ------------------------------------------------------------------ Painel BI
  'painel:geral': {
    nome: 'Visão geral', resumo: 'O resumo da carteira em uma tela.',
    passos: [
      {aba: 'geral', alvo: '#k-geral', titulo: 'Os números do período', texto: '<p>O resumo da carteira no período escolhido:</p><ul><li><b>Pacientes ativos</b> na data final.</li><li><b>Monitoramento com terapias</b>.</li><li><b>Mortalidade</b>.</li><li><b>Terapias pendentes</b>.</li><li>Admissões e altas.</li><li>Visitas.</li><li>Ativos sem visita.</li><li>Relatórios pendentes.</li><li>Orçamentos vencidos.</li></ul><p>A borda colorida indica o tipo: azul informa, verde é entrada, laranja pede atenção e vermelho é crítico.</p>'},
      {aba: 'geral', alvo: '.kpi[data-valor="vencido"]', card: true, titulo: 'Orçamentos vencidos', texto: '<p>Atendimentos <b>em andamento</b> cujo orçamento (autorização da operadora) já venceu.</p><p><b>O que fazer:</b> abra a lista e encaminhe a renovação com cada operadora.</p>'},
      {aba: 'geral', alvo: '#l-orc', card: true, titulo: 'Situação dos orçamentos', texto: '<p>Todos os atendimentos ativos, do mais urgente (vencido) ao mais tranquilo.</p><p>Olhe toda semana a faixa <b>“vence em até 7 dias”</b> para agir antes de vencer.</p>'},
      {aba: 'geral', alvo: '#c-visitas', card: true, titulo: 'Visitas por mês', texto: '<p>Tendência do volume de visitas. Clique num ponto para ver as visitas daquele mês.</p><p><b>Atenção:</b> o mês atual ainda está em andamento, então aparece mais baixo.</p>'},
      {aba: 'geral', alvo: '#c-fluxo', card: true, titulo: 'Entradas e saídas', texto: '<p>Admissões (azul), altas (verde-água) e óbitos (laranja) de cada mês.</p><p>Mais admissões que altas = carteira crescendo.</p>'},
    ],
  },
  'painel:mapa': {
    nome: 'Mapa por bairro', resumo: 'Onde estão os pacientes, as pendências e a equipe.',
    passos: [
      {aba: 'mapa', alvo: '#mapa-metrica', titulo: 'O que o mapa mostra', texto: '<p>Escolha o indicador que pinta o mapa: pacientes ativos, em terapia, <b>terapia pendente</b>, visitas, profissionais no período, <b>profissionais que cobrem</b> (atenderam no bairro nos últimos 180 dias), <b>altas</b> ou <b>relatórios pendentes</b>.</p><p>Ao ver profissionais, o contorno <b>laranja</b> marca bairro sem visita no período mas com alguém que cobre; o <b>vermelho</b>, bairro sem ninguém.</p><p>Pendências e relatórios aparecem em laranja; os demais, em azul.</p>'},
      {aba: 'mapa', alvo: '#mapa-terapia', titulo: 'Filtrar por terapia', texto: '<p>Mostra só uma terapia (Fisio, Fono, TO, Nutri, Psico). Exemplo: onde estão os pacientes de Fono com pendência.</p>'},
      {aba: 'mapa', alvo: '#mapa-zona', titulo: 'Destacar uma zona', texto: '<p>As <b>zonas de atendimento</b> do cliente (ex.: ALDEOTA 7) agrupam vários bairros. Escolha uma para contornar os bairros dela no mapa.</p>'},
      {aba: 'mapa', alvo: '#mapa-svg', titulo: 'Como ler o mapa', texto: '<p>Quanto <b>mais escuro</b>, maior o número; cinza = nenhum. A legenda abaixo mostra as faixas.</p><p><b>Passe o mouse</b> num bairro para ver os números dele. <b>Clique</b> para abrir a <b>ficha do bairro</b>: profissionais que atendem lá, pacientes, pendências, terapias, relatórios, operadoras e zonas.</p>'},
      {aba: 'mapa', alvo: '#mapa-info', card: true, titulo: 'Números do bairro', texto: '<p>Todos os indicadores do bairro escolhido (ou da cidade inteira). Cada número abre a lista de pacientes, visitas ou profissionais daquele bairro, e o botão abre a ficha completa.</p>'},
      {aba: 'mapa', alvo: '#mapa-zonas', card: true, titulo: 'Ranking de zonas e de bairros', texto: '<p>As zonas e os bairros com mais casos do indicador escolhido. Clique num bairro do ranking para abrir a ficha dele.</p>'},
    ],
  },
  'painel:terapias': {
    nome: 'Terapias', resumo: 'Quantos pacientes em cada terapia e quem está pendente.',
    passos: [
      {aba: 'terapias', alvo: '#k-terapias', titulo: 'Resumo das terapias', texto: '<p><b>Pacientes em terapia</b>: com visita de terapia nos últimos 90 dias.</p><p><b>Monitoramento com terapias</b>: pacientes do serviço Monitoramento indicados com terapias.</p><p><b>Pendentes</b> e <b>indicados sem nenhuma terapia</b> são os alertas.</p>'},
      {aba: 'terapias', alvo: '#ter-blocos', titulo: 'Pacientes por terapia', texto: '<p>Quantos pacientes estão em cada terapia (ex.: 72 em Fisio). Embaixo: pacientes e visitas no período e quantos estão pendentes.</p><p>Clique num bloco para ver os pacientes.</p>'},
      {aba: 'terapias', alvo: '#l-pend', card: true, titulo: 'Quem está com terapia pendente', texto: '<p>Pacientes em terapia, mas <b>sem visita há mais de 15 dias</b> naquela terapia.</p><p>A barra vermelha mostra quem é indicado com terapias e não teve nenhuma visita em 90 dias.</p><p><b>O que fazer:</b> abra a lista e verifique a agenda com o profissional.</p>'},
      {aba: 'terapias', alvo: '#c-ter-visitas', card: true, titulo: 'Volume de visitas por terapia', texto: '<p>Total de visitas de cada terapia no período. Clique numa barra para ver as visitas.</p>'},
    ],
  },
  'painel:complexidade': {
    nome: 'Complexidade', resumo: 'Pacientes por quantidade de terapias.',
    passos: [
      {aba: 'complexidade', alvo: '#niveis', titulo: 'Os três níveis', texto: '<p>A complexidade é medida pela <b>quantidade de terapias diferentes</b> que o paciente recebeu nos últimos 90 dias:</p><ul><li><b>Básico</b>: 1 ou 2 terapias.</li><li><b>Intermediário</b>: 3.</li><li><b>Intensivo</b>: 4 ou mais.</li></ul><p>Clique num nível para ver os pacientes.</p>'},
      {aba: 'complexidade', alvo: '#t-cx', card: true, titulo: 'Quais terapias formam cada nível', texto: '<p>Cada linha é um nível e cada coluna, uma terapia. Exemplo: quantos pacientes intensivos fazem Fono. Os números são clicáveis.</p>'},
      {aba: 'complexidade', alvo: '#l-cx-url', card: true, titulo: 'Complexidade do sistema do cliente', texto: '<p>A complexidade que vem cadastrada no sistema da Saúde Residence, para comparar com a calculada pelas terapias.</p>'},
    ],
  },
  'painel:movimentacao': {
    nome: 'Movimentação e mortalidade', resumo: 'Admissões, altas, óbitos e quem foi a óbito.',
    passos: [
      {aba: 'movimentacao', alvo: '#k-mov', titulo: 'Mortalidade no período', texto: '<p><b>Mortalidade</b> = pacientes que foram a óbito ÷ pacientes atendidos no período.</p><p>Clique para ver <b>quem foi a óbito</b>.</p>'},
      {aba: 'movimentacao', alvo: '#t-dma', card: true, titulo: 'Dia · mês · ano', texto: '<p>Os mesmos indicadores no <b>dia</b>, no <b>mês</b> e no <b>ano</b> da data final, lado a lado. Cada número abre a lista.</p>'},
      {aba: 'movimentacao', alvo: '#l-motivos', card: true, titulo: 'Motivos de alta', texto: '<p>Por que os pacientes saíram. Troque entre Dia, Mês e Ano nos botões. Óbitos aparecem em vermelho.</p>'},
      {aba: 'movimentacao', alvo: '#c-mort', card: true, titulo: 'Mortalidade mês a mês', texto: '<p>Mostra se a taxa está estável, subindo ou caindo. Clique num ponto para ver os óbitos do mês.</p>'},
      {aba: 'movimentacao', alvo: '#t-obitos', card: true, titulo: 'Quem foi a óbito', texto: '<p>A lista nominal dos óbitos do período, com operadora, serviço e tempo de atendimento. Clique para ver o histórico de visitas.</p>'},
    ],
  },
  'painel:perfil': {
    nome: 'Perfil dos pacientes', resumo: 'Operadoras, serviços, diagnósticos e idade.',
    passos: [
      {aba: 'perfil', alvo: '#l-oper', card: true, titulo: 'Operadoras e serviços', texto: '<p>Quantos pacientes ativos há em cada convênio e em cada serviço contratado, com o percentual sobre o total. Útil em negociações.</p>'},
      {aba: 'perfil', alvo: '#l-diag', card: true, titulo: 'Diagnósticos', texto: '<p>Os diagnósticos mais frequentes entre os pacientes ativos, como vêm do sistema do cliente.</p>'},
      {aba: 'perfil', alvo: '#c-idade', card: true, titulo: 'Faixa etária', texto: '<p>Distribuição por idade; a média aparece no canto. Clique numa barra para ver os pacientes.</p>'},
    ],
  },
  'painel:profissionais': {
    nome: 'Profissionais', resumo: 'Carga da equipe e disponibilidade por bairro.',
    passos: [
      {aba: 'profissionais', alvo: '#t-prof', card: true, titulo: 'Profissional × atendimentos', texto: '<p>Os 15 profissionais com mais visitas no período: pacientes, dias trabalhados e bairros atendidos.</p><p>Clique para ver as visitas. Clique no título de uma coluna para ordenar.</p>'},
      {aba: 'profissionais', alvo: '#l-rel', card: true, titulo: 'Relatórios pendentes', texto: '<p>Relatórios que ainda não foram entregues, por terapia. A lista completa fica no Painel operacional.</p>'},
      {aba: 'profissionais', alvo: '#abr-busca', card: true, titulo: 'Disponibilidade de bairro', texto: '<p>Onde cada profissional atendeu no período. Digite um <b>bairro</b> para descobrir quem já atende lá, ou um <b>nome</b> para ver a região do profissional.</p>'},
    ],
  },

  // ------------------------------------------------------------------ Painel operacional
  'operacional:relatorios': {
    nome: 'Relatórios pendentes', resumo: 'O que falta entregar, por quem e desde quando.',
    passos: [
      {aba: 'relatorios', alvo: '#k-rel', titulo: 'Resumo', texto: '<p>Total de relatórios pendentes, pacientes e profissionais envolvidos e a <b>competência mais antiga</b> (o atraso maior).</p><p>Esta lista não depende do período: um relatório some daqui quando é entregue no App.</p>'},
      {aba: 'relatorios', alvo: '#l-rel-comp', card: true, titulo: 'Por competência', texto: '<p>Mês de referência dos relatórios, <b>do mais antigo para o mais recente</b>. Comece cobrando os do topo.</p>'},
      {aba: 'relatorios', alvo: '#l-rel-prof', card: true, titulo: 'Por profissional', texto: '<p>Quem tem mais relatórios a entregar. Útil para conversar com cada profissional.</p>'},
      {aba: 'relatorios', alvo: '#rel-busca', card: true, titulo: 'Encontrar e exportar', texto: '<p>Busque por paciente, profissional ou terapia, filtre pela terapia e use <b>Exportar CSV</b> para enviar a lista por e-mail ou abrir no Excel.</p><p>As barras acima e cada linha da tabela também são clicáveis: abrem a lista filtrada e o histórico do paciente.</p>'},
    ],
  },
  'operacional:profissional': {
    nome: 'Profissional × atendimento', resumo: 'Os pacientes de cada profissional.',
    passos: [
      {aba: 'profissional', alvo: '#prof-busca', card: true, titulo: 'Escolha um profissional', texto: '<p>Lista de quem atendeu no período: visitas, pacientes, dias e bairros. Busque pelo nome.</p><p><b>Clique na linha</b> para ver os pacientes dele, com a primeira e a última visita de cada um.</p>'},
    ],
  },
  'operacional:abrangencia': {
    nome: 'Região de abrangência', resumo: 'Onde a equipe atende e onde falta cobertura.',
    passos: [
      {aba: 'abrangencia', alvo: '#k-abr', titulo: 'Cobertura em números', texto: '<p>Profissionais ativos, bairros atendidos e os alertas:</p><ul><li>Bairros que dependem de <b>um único profissional</b>.</li><li>Bairros e zonas <b>sem cobertura</b>: têm pacientes indicados para terapia, mas nenhum profissional no período.</li></ul>'},
      {aba: 'abrangencia', alvo: '#abr-mapa', titulo: 'Mapa de cobertura', texto: '<p>Mais escuro = mais profissionais atendendo no bairro. Contorno <b>laranja</b> = bairro descoberto no período, mas com profissional que cobre a região (atendeu lá nos últimos 180 dias). Contorno <b>vermelho</b> = ninguém atendeu lá em 180 dias.</p><p><b>Clique num bairro</b> para abrir a ficha completa (profissionais, pacientes, pendências e relatórios) e filtrar a tabela abaixo.</p>'},
      {aba: 'abrangencia', alvo: '#abr-prof', titulo: 'Região de um profissional', texto: '<p>Escolha um profissional para ver no mapa <b>a região dele</b>: pintado onde atendeu no período e contornado tudo o que ele cobre nos últimos 180 dias.</p>'},
      {aba: 'abrangencia', alvo: '#t-zonas', card: true, titulo: 'Cobertura por zona', texto: '<p>As zonas de atendimento do cliente, com as sem cobertura no topo. Clique numa zona para destacar os bairros dela no mapa.</p>'},
      {aba: 'abrangencia', alvo: '#abr-busca', card: true, titulo: 'Quem atende onde', texto: '<p>Tabela profissional × zona × bairro. Para encontrar alguém que já atende perto de um paciente novo, digite o bairro ou a zona. Clique numa linha para abrir a ficha do bairro.</p>'},
    ],
  },
  'operacional:fichas': {
    nome: 'Fichas realizadas no App', resumo: 'Tudo o que foi registrado no App no período.',
    passos: [
      {aba: 'fichas', alvo: '#k-fichas', titulo: 'Fichas do período', texto: '<p>Cada visita registrada no App pelo profissional conta como uma ficha. Os cards mostram o total, os pacientes, os profissionais e o volume por terapia.</p>'},
      {aba: 'fichas', alvo: '#fic-busca', card: true, titulo: 'Conferir e exportar', texto: '<p>Busque um paciente ou profissional, filtre por terapia e exporte. Use, por exemplo, para conferir o que cada profissional registrou na semana.</p>'},
    ],
  },
  'operacional:precos': {
    nome: 'Tabela de preços', resumo: 'Aguardando os valores do sistema do cliente.',
    passos: [
      {aba: 'precos', alvo: '#aba-precos .card', titulo: 'Em breve', texto: '<p>Esta tabela será preenchida automaticamente quando o sistema do cliente passar a enviar os valores por empresa.</p>'},
    ],
  },

  // ------------------------------------------------------------------ Administração
  'integracao': {
    nome: 'Integração com a URL', resumo: 'Saúde da sincronização e mudanças nos dados.',
    passos: [
      {alvo: '#k-sync', titulo: 'Situação da sincronização', texto: '<p>Última execução, última vez que deu certo e quantos atendimentos e visitas estão guardados.</p><p>A sincronização roda sozinha a cada hora, <b>enquanto o aplicativo estiver aberto</b> no computador servidor.</p>'},
      {alvo: '#sync', titulo: 'Sincronizar agora', texto: '<p>Busca os dados na hora, sem esperar a próxima rodada automática. Útil depois de uma correção no sistema do cliente.</p>'},
      {alvo: '#t-alertas', card: true, titulo: 'Monitor de alterações', texto: '<p>Avisa quando o sistema do cliente passa a enviar <b>campos novos</b> ou categorias novas, como um serviço ou uma operadora.</p><p>Campo novo = oportunidade de um indicador novo no painel. Marque como visto depois de avaliar.</p>'},
    ],
  },
  'usuarios': {
    nome: 'Usuários e perfis', resumo: 'Quem acessa e o que cada perfil vê.',
    passos: [
      {alvo: '#novo', titulo: 'Novo usuário', texto: '<p>Crie um acesso com login, nome, <b>perfil</b> e senha inicial. A pessoa troca a senha no primeiro acesso.</p>'},
      {alvo: '.perfis', card: true, titulo: 'Perfis de acesso', texto: '<p><b>Operacional</b> vê só o Painel operacional. <b>Gestor</b> vê também o Painel BI. <b>Administrador</b> vê tudo.</p><p>Cada perfil abre direto na sua página.</p>'},
      {alvo: '#t-usuarios', card: true, titulo: 'Editar ou desativar', texto: '<p>Para alguém que saiu da equipe, prefira <b>Inativo</b> a excluir: a pessoa perde o acesso e o registro fica guardado.</p>'},
    ],
  },
};
