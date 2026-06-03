# Dashboard Rewards - Firestore

## Fluxo de envio

O app Python le os pontos do Microsoft Rewards antes e depois das etapas que alteram saldo:

1. Antes do Conjunto diario.
2. Depois do Conjunto diario.
3. Antes de Pesquisar com o Bing.
4. Depois de Pesquisar com o Bing.
5. Antes de Navegar com Edge.
6. Depois de Navegar com Edge.

Se uma etapa falhar, o app tenta fazer a leitura `after` com `status: "falhou"`.
Brotato nao gera evento de pontos porque nao altera o saldo diretamente.

A leitura abre o painel do Rewards, usa o alvo visual `Exibir painel` como trava de seguranca, executa double click na posicao configurada do numero grande de pontos e copia via clipboard.

O double click so e executado se `Exibir painel` for encontrado. Isso evita clicar em uma posicao absoluta quando o painel do Rewards nao esta aberto.

## Configuracao no app Python

As configuracoes ficam em `config.json`, na chave `dashboard`.

```json
{
  "dashboard": {
    "ativada": true,
    "api_endpoint": "",
    "api_secret": "",
    "user_uid": "",
    "source": "python_app",
    "bearer_token": "",
    "firebase": {
      "apiKey": "AIza...",
      "authDomain": "personalrewardsdashboard.firebaseapp.com",
      "projectId": "personalrewardsdashboard",
      "storageBucket": "personalrewardsdashboard.firebasestorage.app",
      "messagingSenderId": "990756612461",
      "appId": "1:990756612461:web:ed86a992035287ec1fd264"
    },
    "leitura_pontos": {
      "tentativas": 3,
      "click_offset_x": -245,
      "click_offset_y": -38,
      "double_click_x": null,
      "double_click_y": null,
      "restaurar_clipboard": true,
      "min_points": null,
      "max_auto_drop": null,
      "max_raw_text_chars": 40
    }
  }
}
```

`user_uid` precisa ser preenchido com o UID do usuario autenticado no Firebase.

`double_click_x` e `double_click_y` sao capturados pelo app Python na aba `Configuracoes > Dashboard`.
Coloque o mouse em cima do numero grande de pontos e pressione `F9` no modo de captura.
Os campos antigos `click_offset_x` e `click_offset_y` ficam apenas como fallback legado enquanto a posicao absoluta nao for capturada.

As validacoes impedem envios claramente errados:

- `max_raw_text_chars` rejeita textos longos/copias da pagina inteira.
- `min_points` e opcional. Se vazio ou `null`, o app aceita qualquer saldo numerico bem formatado.
- `max_auto_drop` e opcional. Se vazio ou `null`, o app aceita quedas grandes causadas por resgates.
- O formato do numero tambem e validado. Exemplos validos: `90.296`, `90,296`, `90296`, `11.624`.
  Um texto como `1,1624` e rejeitado porque nao segue agrupamento de milhares.

Se `api_endpoint` estiver preenchido, o app envia um JSON para essa API usando `POST`.
Se `api_endpoint` estiver vazio, o app tenta gravar diretamente no Firestore via REST.

## Caminho Firestore

Quando usa Firestore direto, cada evento e salvo em:

```text
users/{uid}/rewardEvents/{eventId}
```

O `{uid}` vem de `dashboard.user_uid`.

## Documento `rewardEvents`

Campos enviados:

```ts
type RewardEvent = {
  schemaVersion: number
  points: number
  createdAt: Timestamp
  localTime: string
  source: string
  stage: string
  phase: "before" | "after"
  status: string
  runId: string
  logId?: string
  notes?: string
  rawText?: string
  readMethod?: string
  readPositionSource?: string
  deltaFromPreviousRead?: number
  readAnchor?: {
    x: number
    y: number
  }
  readClick?: {
    x: number
    y: number
  }
}
```

Exemplo:

```json
{
  "schemaVersion": 1,
  "points": 86030,
  "createdAt": "2026-06-03T05:12:30Z",
  "localTime": "2026-06-03T02:12:30",
  "source": "python_app",
  "stage": "conjunto_diario",
  "phase": "after",
  "status": "ok",
  "runId": "run_20260603_021100_a1b2c3d4",
  "logId": "execucao_20260603_021100.log",
  "notes": "Conjunto diario concluido.",
  "rawText": "86.030",
  "readMethod": "double_click_clipboard",
  "readPositionSource": "posicao_capturada",
  "deltaFromPreviousRead": 30,
  "readAnchor": {
    "x": 552,
    "y": 250
  },
  "readClick": {
    "x": 307,
    "y": 212
  }
}
```

## Valores de `stage`

Valores usados atualmente:

```text
conjunto_diario
pesquisar_bing
navegar_edge
```

Eventos antigos podem existir com `inicio`, `final`, `brotato` ou `erro`, mas o fluxo novo nao cria esses stages para pontuacao.

## Valores de `phase`

Valores usados atualmente:

```text
before
after
```

## Valores de `status`

Valores usados atualmente:

```text
ok
falhou
```

O frontend pode aceitar outros valores no futuro, como:

```text
cancelado
parcial
incompleto
```

## Agrupamento no frontend

O frontend deve:

1. Buscar todos os documentos de `users/{uid}/rewardEvents`.
2. Agrupar por data local derivada de `localTime` ou `createdAt`.
3. Ordenar os eventos do dia por horario.
4. Considerar o ultimo evento do dia como saldo final daquele dia.
5. Calcular o delta diario comparando o saldo final com o saldo final do dia anterior.
6. Se o delta for negativo e nao houver resgate vinculado, mostrar `resgate provavel`.

## Resgates

Os resgates cadastrados pelo frontend devem ficar em:

```text
users/{uid}/redemptions/{redemptionId}
```

Formato sugerido:

```ts
type Redemption = {
  id: string
  title: string
  pointsSpent: number
  redeemedAt: Timestamp
  relatedDate: string
  orderNumber?: string
  notes?: string
  createdAt: Timestamp
  updatedAt: Timestamp
}
```

`relatedDate` deve usar `YYYY-MM-DD` e apontar para o dia em que a queda de pontos foi detectada.

## Observacao sobre seguranca

A configuracao web do Firebase identifica o projeto, mas nao autentica o Python como usuario.

Para gravar direto no Firestore, existem tres caminhos:

1. Usar regras temporariamente permissivas para `users/{uid}/rewardEvents`.
2. Informar um `bearer_token` valido do Firebase Auth, se quiser usar regras por usuario.
3. Preferencialmente no futuro, usar `api_endpoint` com uma API propria protegida por secret, e essa API grava no Firestore.

Para a primeira versao pessoal, o app ja esta preparado para Firestore direto e para API futura.
