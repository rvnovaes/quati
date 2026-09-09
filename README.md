<p align="center">
  <img src="static/img/quati-mascote.png" alt="Mascote do Quati, um quati de terno com pasta" width="200">
</p>

Quati
===========

O Quati é um sistema web de gestão de logística jurídica que permite o controle de processos desde a prestação do serviço até o seu efetivo pagamento. O solicitante cadastra as providências que precisam ser cumpridas e o sistema identifica o melhor profissional para cumpri-las, considerando proximidade, preço e avaliação. O correspondente é avisado por e-mail e pode aceitar ou recusar a providência.

O fluxo reúne ordens de serviço (OS), distribuição e aceite, prazos, questionários, anexos, registros de execução e controle de valores a pagar e receber entre escritórios e parceiros.

Atualizações recentes
--------------------

- **Questionários:** autenticação e permissão no escritório selecionado, com isolamento na leitura, criação, edição e exclusão em lote.
- **Anexos:** exclusão de arquivos sem compartilhamento dentro de uma transação, com limpeza após commit. Anexos compartilhados, cópias e referências legadas continuam protegidos. A exclusão exige POST com CSRF; o acesso interno valida o escritório e o externo valida o hash da OS.
- **Pastas e legado:** abertura e salvamento sem depender de registros fictícios de importações antigas. Listagens, buscas, APIs, formulários e autocompletes usam seus filtros normais de escritório, atividade e relacionamento.
- **Faturamento:** filtros de OS faturadas e não faturadas corrigidos para o Django atual, com cobertura também da opção “Todas”.

Não haverá novas importações de dados antigos. Campos históricos, vínculos existentes e a importação operacional de planilhas foram preservados. Veja as decisões e os limites em [Retirada das regras de importação legada](docs/LEGADO.md).

Stack
-----

- Python 3.12, Django 5.2 LTS, PostgreSQL 16, Redis 7, RabbitMQ 3
- Celery 5 (tarefas assíncronas e agendadas), Django Channels 4 + Daphne (chat via WebSocket)
- Gunicorn (HTTP), nginx (proxy reverso, estáticos e mídia), Postfix (envio de e-mail)
- Tudo orquestrado por Docker Compose

Como rodar
----------

1. Copie `.env.example` para `.env` e ajuste (pelo menos `SECRET_KEY` em produção).
2. Escolha o ambiente:

   ```bash
   make set_env_development   # runserver com reload, Mailpit, portas expostas
   make set_env_production    # gunicorn, nginx em 80/443, Postfix
   ```

3. Primeira subida (build, migrations, seed, collectstatic):

   ```bash
   make bootstrap
   ```

   O seed (`scripts/seed_db.sh`, também disponível como `make seed`) carrega as fixtures essenciais, cria grupos e permissões e o usuário `admin` (senha `admin`, ou `SEED_ADMIN_PASSWORD`) com escritório padrão. O seed também carrega as 6.716 cidades brasileiras (`manage.py seed_cities`). Para um ambiente de demonstração, `make seed_demo` (ou `SEED_DEMO=1` no seed) povoa todos os cadastros: correspondentes, solicitantes, supervisor, financeiro, clientes com endereços e contatos, empresa e preposto, instâncias, órgãos, varas, complementos de comarca, centros de custo, tipos de movimentação, políticas e tabelas de preço, equipes, questionários, regras de anexo, um escritório correspondente em rede (`lima.souza`), pastas, processos e 40 OS distribuídas pelos status, com prazos nos próximos dias, histórico de 5 meses para os relatórios e 3 OS delegadas ao escritório correspondente. Usuários de demonstração (`ana.ribeiro`, `carlos.mota`, `juliana.ferraz`, `marcos.lima`, `beatriz.campos`, `rafael.nunes`, `helena.prado`, `otavio.reis`, `lucas.andrade`, `lima.souza`, `paulo.souza`) usam a senha `quati123`.

4. Nas próximas vezes: `make up`, `make logs`, `make down`.

Endereços em desenvolvimento:

| Serviço | URL |
|---|---|
| Django (runserver) | http://localhost:8000 |
| nginx | http://localhost:8080 |
| Mailpit (e-mails de teste) | http://localhost:8026 |
| Flower (Celery) | http://localhost:5555 |
| RabbitMQ management | http://localhost:8083 (guest/guest) |
| PostgreSQL | localhost:57002 (ezl/ezl) |

Comandos úteis: `make shell`, `make psql`, `make migrate`, `make migrations`, `make test`, `make check`.

Testes e validação
------------------

Com o serviço `web` em execução:

```bash
docker compose exec -T web pytest -q --tb=short
```

A suíte usa PostgreSQL em um banco de testes separado, uploads temporários e substitutos locais para e-mail, cache, Channels e transporte do Celery. Execute as suítes sequencialmente, pois compartilham o banco de testes.

Última validação das correções, em **08/09/2026**: **145 testes e 16 subtestes aprovados**, sem falhas ou `xfail`. Permanecem 11 avisos de tabelas e paginação. Os quatro defeitos inicialmente reproduzidos (BUG-001 a BUG-004) foram corrigidos; isso não representa cobertura completa da aplicação. Navegador/JavaScript e integrações externas reais não foram validados por essa suíte.

Veja [a documentação da suíte de testes](docs/TESTES.md) para os contratos cobertos, isolamento, relatórios e histórico das correções. A [análise de candidatos a código morto](docs/ANALISE-codigo-morto.md) registra o levantamento anterior; candidatos exigem avaliação de uso antes de serem removidos.

E-mail
------

Em desenvolvimento os e-mails vão para o Mailpit. Em produção o serviço `postfix` do compose entrega diretamente (ou via `POSTFIX_RELAYHOST`). Configure no `.env`: `EMAIL_HOST=postfix`, `EMAIL_PORT=587`, `POSTFIX_HOSTNAME`, `POSTFIX_ALLOWED_SENDER_DOMAINS` e, para boa entregabilidade, registros SPF/DKIM/PTR do domínio remetente.

Se `DEFAULT_TO_EMAIL` estiver definido, todos os e-mails são redirecionados para esse endereço (útil em homologação).

Os e-mails de OS são templates Django em `task/templates/mail/`. A tabela `EmailTemplate` (admin) guarda o caminho do template por status.

Arquivos
--------

Uploads ficam no volume Docker `web-media` (`/app/media` no container), servidos pelo nginx em `/media/`.

HTTPS em produção
-----------------

Coloque o certificado e a chave em `containers/nginx/certs/` e adicione um bloco `listen 443 ssl` em `containers/nginx/templates/default.conf.template`, ou use um certbot/Traefik externo na frente do nginx.

Identidade visual (Quati)
-------------------------

O tema fica em `core/static/quati/quati.css` (tokens de cor para tema claro e escuro, tipografia Bricolage Grotesque / Manrope / JetBrains Mono) e sobrescreve o tema Ample sem mudar o HTML das telas. O seletor claro/escuro (`core/static/quati/theme.js`) guarda a escolha no navegador.

A marca está em `core/templates/skeleton/includes/brand.html`, que já utiliza o ícone do Quati e o nome do produto. Os arquivos de identidade visual estão versionados em `static/img/`: `quati-mascote.png` (também exibido no início deste README), `quati-registro.png` e os ícones de 96 e 192 pixels.

Histórico
---------

Veja `docs/CHANGELOG-modernizacao.md` para o que mudou na modernização de 2026 (remoção do Advwin, Gerencianet, SendGrid, S3 e servidor Windows).

Possibilidades de desenvolvimento
---------------------------------

A estrutura de OS, parceiros, prazos, questionários, evidências e pagamentos pode servir de base para gestão de serviços em campo além da correspondência jurídica. As possibilidades abaixo são direções de evolução, não módulos já implementados.

| Possibilidade | Aplicação do fluxo |
|---|---|
| Vistorias e inspeções | Distribuir visitas, aplicar checklists, registrar fotos e localização, revisar entregas e remunerar vistoriadores. |
| Manutenção e assistência técnica | Encaminhar chamados a técnicos, controlar prazos, documentar serviços e acompanhar custos. |
| Diligências documentais | Organizar certidões, protocolos, entregas e retiradas em cartórios e órgãos públicos. |
| Operações imobiliárias | Gerenciar vistorias de entrada e saída, entrega de chaves, visitas técnicas e documentação de imóveis. |
| Auditoria de campo | Distribuir inspeções em unidades, coletar evidências e respostas padronizadas e solicitar complementações. |

**Vistorias e inspeções são o primeiro caminho proposto**, por aproveitarem diretamente questionários, anexos, execução em campo, revisão e pagamento por serviço.

Para atender outros setores, a principal evolução é permitir uma OS independente de movimentação, processo e pasta, com uma estrutura como **cliente → contrato ou projeto → local/ativo → ordem de serviço**. Exemplo: uma administradora solicita a vistoria de um imóvel, distribui para um parceiro, recebe fotos e checklist, pede ajustes e aprova o pagamento.

Antes dessa expansão, será necessário validar a experiência no celular, definir suporte a trabalho sem internet, recorrência de visitas, organização de evidências e permissões por papel. Essas capacidades não foram comprovadas na análise atual.
