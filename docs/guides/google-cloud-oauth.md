# Guia Passo a Passo — Configuração no Google Cloud Console (OAuth 2.0)

Este guia explica como criar as credenciais OAuth 2.0 no **Google Cloud Console** para conectar o Personal Assistant à sua conta Google (**Google Calendar**, **Google Meet** e **Google Sheets**).

---

## 1. Criar ou Selecionar um Projeto

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. No seletor de projetos no topo da página, clique em **Novo projeto** (ou selecione um existente).
3. Dê um nome (ex: `personal-assistant`) e clique em **Criar**.
4. Certifique-se de que o projeto recém-criado está selecionado no topo.

---

## 2. Ativar as APIs Necessárias

No menu lateral esquerdo, acesse **APIs e Serviços -> Biblioteca** (ou pesquise na barra superior) e ative **todas as 3 APIs** abaixo:

1. **Google Calendar API** -> clique em **Ativar**
2. **Google Sheets API** -> clique em **Ativar**
3. **Google Drive API** -> clique em **Ativar** *(necessária para criar as planilhas iniciais automaticamente)*

---

## 3. Configurar a Tela de Permissão OAuth (OAuth Consent Screen)

No menu lateral, acesse **APIs e Serviços -> Tela de permissão OAuth** (ou *Google Auth Platform -> Público-alvo / Visão geral*):

1. Caso apareça a tela inicial, clique em **Começar** / **Configurar**.
2. Em **Tipo de usuário (User Type / Público-alvo)**, selecione **Externo** e clique em **Criar** / **Próxima**.
3. Preencha os campos obrigatórios:
   - **Nome do app**: `Personal Assistant`
   - **E-mail de suporte do usuário**: seu e-mail `@gmail.com`
   - **Dados de contato do desenvolvedor**: seu e-mail `@gmail.com`
4. Clique em **Salvar e continuar**.
5. **Escopos** (se exibido): clique em **Salvar e continuar** (o script `auth_google` solicitará os escopos necessários automaticamente).
6. **Usuários de teste (Test users)**:
   - Clique em **+ Add Users** e adicione o seu próprio e-mail `@gmail.com` que será conectado ao assistente.
   - Salve e continue.

> **Importante (Expiração de 7 dias do Token):**
> Enquanto o aplicativo ficar no status **Em teste (Testing)**, o `refresh_token` do Google expira a cada **7 dias**.
> Para uso contínuo sem precisar reautenticar toda semana:
> - Vá em **Tela de permissão OAuth / Público-alvo** e clique em **Publicar aplicativo (Publish App)** -> **Confirmar**.
> - Como o app é para seu uso pessoal (sem verificação pública do Google), no momento do login aparecerá a tela *"O Google não verificou este app"*. Basta clicar em **Avançado -> Acessar personal-assistant (não seguro)** uma única vez.

---

## 4. Criar o ID do Cliente OAuth (`credentials.json`)

1. No menu lateral, acesse **APIs e Serviços -> Credenciais** (ou *Google Auth Platform -> Clientes*).
2. Clique em **+ Criar credenciais -> ID do cliente OAuth**.
3. Em **Tipo de aplicativo**, selecione **App para computador (Desktop app)**.
4. Dê um nome (ex: `personal-assistant-desktop`) e clique em **Criar**.
5. Na janela de confirmação, clique em **Fazer download do JSON**.
6. Renomeie o arquivo baixado para `credentials.json` e mova para a pasta `credentials/` na raiz do projeto:

```text
personal-assistant/
└── credentials/
    └── credentials.json
```

---

## 5. Autorizar a Conta e Criar as Planilhas

Com o `credentials/credentials.json` no lugar, execute localmente (fora do Docker, usando o `.venv`) para abrir o navegador e gerar o `token.json`:

```bash
.venv/bin/python -m scripts.auth_google
```

Em seguida, crie automaticamente as planilhas **Controle Veicular** e **Orçamento Doméstico** no seu Google Drive:

```bash
.venv/bin/python -m scripts.setup_sheets
```

Copie os dois IDs exibidos no terminal para o seu `.env`:

```env
GOOGLE_SHEETS_CAR_ID=id_da_planilha_veicular
GOOGLE_SHEETS_BUDGET_ID=id_da_planilha_orcamento
```

Por fim, recrie o container para carregar o `token.json` e os novos IDs:

```bash
docker compose up -d
```

Nos logs (`docker compose logs -f`), você verá `tools_enabled=12` (ou `8` caso opte por usar apenas Calendar sem Sheets).
