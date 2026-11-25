# Guia Passo a Passo — Configuração no Google Cloud Console (OAuth 2.0)

Este guia explica como criar as credenciais OAuth 2.0 no **Google Cloud Console** (interface atual **Google Auth Platform**) para conectar o Personal Assistant à sua conta Google (**Google Calendar**, **Google Meet** e **Google Sheets**).

---

## 1. Criar ou Selecionar um Projeto

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. No seletor de projetos no topo da página, clique em **Novo projeto** (ou selecione um existente, como `My First Project`).
3. Dê um nome (ex: `personal-assistant`) e clique em **Criar**.
4. Certifique-se de que o projeto correto está selecionado no topo.

---

## 2. Ativar as APIs Necessárias

No menu lateral esquerdo, acesse **APIs e Serviços -> Biblioteca** (ou pesquise na barra superior) e ative **todas as 3 APIs** abaixo:

1. **Google Calendar API** -> clique em **Ativar**
2. **Google Sheets API** -> clique em **Ativar**
3. **Google Drive API** -> clique em **Ativar** *(necessária para criar as planilhas iniciais automaticamente)*

---

## 3. Configurar a Google Auth Platform (Tela de Permissão)

No menu lateral, acesse **APIs e Serviços -> Tela de permissão OAuth** (você será direcionado para a **Google Auth Platform**):

1. Na tela inicial (*Visão geral*), clique em **Começar** (se ainda não estiver configurado).
2. Preencha o assistente inicial:
   - **Nome do app**: `Personal Assistant`
   - **E-mail de suporte do usuário**: seu e-mail `@gmail.com`
   - **Público-alvo**: selecione **Externo**
   - **Dados de contato**: seu e-mail `@gmail.com`
   - Aceite a política de dados e clique em **Criar**.
3. Após criar, você cairá na tela **Visão geral de OAuth** com o menu lateral da **Google Auth Platform** (*Visão geral*, *Branding*, *Público-alvo*, *Clientes*, *Acesso a dados*).

### Configurar Público-alvo (Usuários de Teste / Publicação)

1. No menu lateral esquerdo da Google Auth Platform, clique em **Público-alvo**.
2. Em **Usuários de teste**, clique em **+ Add users**, informe o seu `@gmail.com` e salve.

> **Importante (Expiração de 7 dias do Token):**
> Enquanto o aplicativo ficar no status **Em teste (Testing)**, o `refresh_token` do Google expira a cada **7 dias**.
> Para uso contínuo sem precisar reautenticar toda semana:
> - Na mesma aba **Público-alvo**, clique em **Publicar aplicativo (Publish App)** -> **Confirmar**.
> - Como o app é para seu uso pessoal (sem verificação pública do Google), no momento do login aparecerá a tela *"O Google não verificou este app"*. Basta clicar em **Avançado -> Acessar personal-assistant (não seguro)** uma única vez.

---

## 4. Criar o Cliente OAuth (`credentials.json`)

1. Na tela **Visão geral**, clique no botão **Criar um cliente OAuth** (ou acesse **Clientes -> + Criar cliente** no menu lateral esquerdo).
2. Em **Tipo de aplicativo**, selecione **App para computador (Desktop app)**.
3. Dê um nome (ex: `personal-assistant-desktop`) e clique em **Criar**.
4. Na janela de confirmação, clique em **Fazer download do JSON**.
5. Renomeie o arquivo baixado para `credentials.json` e mova para a pasta `credentials/` na raiz do projeto:

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
