Quati
===========

O Quati é um sistema web de gestão de logística jurídica que permite o controle de processos desde a prestação do serviço até o seu efetivo pagamento. O solicitante cadastra as providências que precisam ser cumpridas e o sistema identifica o melhor profissional para cumpri-las, considerando proximidade, preço e avaliação. O correspondente é avisado por e-mail e pode aceitar ou recusar a providência.

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

   O seed (`scripts/seed_db.sh`, também disponível como `make seed`) carrega as fixtures essenciais, cria grupos e permissões e o usuário `admin` (senha `admin`, ou `SEED_ADMIN_PASSWORD`) com escritório padrão. Para um ambiente de demonstração, `make seed_demo` (ou `SEED_DEMO=1` no seed) cria correspondentes, solicitantes, clientes, processos e 19 OS distribuídas pelos status, com prazos nos próximos dias. Usuários de demonstração (`ana.ribeiro`, `carlos.mota`, `juliana.ferraz`, `marcos.lima`, `beatriz.campos`, `rafael.nunes`) usam a senha `quati123`.

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

O tema fica em `core/static/quati/quati.css` (tokens de cor para tema claro e escuro, tipografia Bricolage Grotesque / Manrope / JetBrains Mono) e sobrescreve o tema Ample sem mudar o HTML das telas. O seletor claro/escuro (`core/static/quati/theme.js`) guarda a escolha no navegador. A marca está em `core/templates/skeleton/includes/brand.html`: para usar o logo definitivo, troque o `<svg>` por uma `<img>`.

Histórico
---------

Veja `docs/CHANGELOG-modernizacao.md` para o que mudou na modernização de 2026 (remoção do Advwin, Gerencianet, SendGrid, S3 e servidor Windows).
