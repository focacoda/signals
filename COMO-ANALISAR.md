# Como analisar a plataforma

## 1. Subir

Duplo clique em `iniciar.bat`, ou:

```bash
python run.py
```

Depois abra `http://127.0.0.1:8000`.

## Prazos: M5 e M15

Cada ativo é avaliado **duas vezes por ciclo**, uma por prazo. O prazo define
o timeframe das velas — não existe analisar M5 e apostar M15:

| Prazo | Velas analisadas | Confiança mínima | Projeta |
|---|---|---|---|
| **M5** | 5 minutos | **80%** | o próximo candle de 5 min |
| **M15** | 15 minutos | **80%** | o próximo candle de 15 min |

O mesmo ativo pode ter sinais válidos nos dois prazos ao mesmo tempo — um M5
em aberto não bloqueia um M15. O cooldown é por (ativo, prazo) e nunca é
menor que a duração do candle, para não sair dois sinais do mesmo candle.

> **M1 está desligado.** Em 60 segundos a confluência atual não separa sinal
> de ruído. A estrutura continua aceitando M1: basta voltar `1: 60` em
> `TIMEFRAMES`, em `MIN_CONFIDENCE_BY_EXPIRY` e em `EMIT_WINDOW_BY_EXPIRY`
> quando houver uma estratégia específica para ele.

### Os N segundos de emissão

O sinal só é publicado nos **últimos N segundos** antes do candle fechar.
Fora dessa janela, a avaliação é calculada e aparece no dashboard (com a
contagem "entra em …"), mas **nada é emitido**.

| Prazo | Candle | Janela de emissão | Fração do candle |
|---|---|---|---|
| **M5** | 300 s | **últimos 20 s** | 7% |
| **M15** | 900 s | **últimos 30 s** | 3% |

Exemplo concreto em M15: o candle abre em 10h00 e fecha em 10h15. O sinal é
publicado entre **10h14:30 e 10h15:00**. Se a confluência já estiver acima de
80% às 10h03, o card mostra "entra em 11m30s" — e só emite quando o relógio
entrar na janela.

**A confluência é reavaliada dentro da janela.** Não vale a leitura feita 11
minutos antes: ao entrar nos últimos 30 s, o motor busca as velas de novo e
recalcula. Se a direção virou ou a confiança caiu abaixo do piso, o sinal não
sai. Só é publicado o consenso que ainda está de pé no instante da emissão.

Ajustável por variável de ambiente:

```bash
EMIT_WINDOW_M5=20 EMIT_WINDOW_M15=30
MIN_CONFIDENCE_M5=80 MIN_CONFIDENCE_M15=80
```

## 2. O que olhar primeiro (aba "Ao vivo")

Cada card de ativo mostra:

| Campo | Significado |
|---|---|
| ▲ CALL / ▼ PUT | direção que a confluência de indicadores aponta |
| `NN% confiança` | força do consenso, já penalizada por volatilidade baixa |
| `auditável` | a fonte permite que terceiro confira o preço de fechamento |
| motivos | **por que** o sinal foi emitido, em texto |

Regra prática: **confiança 100% quase sempre significa mercado travado**, não
qualidade. Quando a volatilidade cai, o `vol_factor` reduz o score. Em OTC a
volatilidade é baixa por natureza, então a confiança satura com facilidade —
compare com o RSI e a inclinação mostrados antes de julgar.

## 3. Aba "Track record" — o número que importa

Este é o único número honesto do sistema, porque é calculado sobre sinais
gravados **antes** de o resultado existir.

- **Ponto de equilíbrio** com payout 85% é **54,05%**.
  - Acertar mais que isso: lucro.
  - Acertar menos: prejuízo, mesmo acertando "mais da metade".
- **Abaixo de 100 operações decididas**, trate a taxa como ruído.

### O que já medi (dados reais, outubro/2026)

| Componente testado | Taxa | vs. aleatório (50%) |
|---|---|---|
| Cruzamento de EMA | 44,4% | pior |
| RSI | 44,2% | pior |
| Inclinação de curto prazo | 46,4% | pior |
| **Reversão em banda de Bollinger** | 55,1% | **+5 p.p.** |

A reversão em Bollinger foi o único com sinal positivo. Mas ao dividir a
série em 4 períodos independentes:

```
fold 1: 26,83%    fold 2: 45,45%    fold 3: 48,78%    fold 4: 64,29%
```

Um período de cada quatro acima do equilíbrio, amplitude de 37 p.p. **Isso
é mudança de regime, não edge.** Por isso a estratégia combinada — que
mistura tendência, RSI e Bollinger — fica em ~49%, abaixo do equilíbrio.

## 4. O teste que você deve rodar

Aba **Backtest**, escolha um ativo e compare:

1. Rode `BTCUSD`, expiração 5, confiança 60, 1500 barras → anote a taxa.
2. Suba a confiança para 80. Se a taxa **melhorar muito**, pode ser que o
   filtro esteja funcionando — ou pode ser que ele só reduziu a amostra.
3. Compare o número de operações. Com menos de 100, não conclua nada.
4. Repita em outro ativo. **Se o resultado não se repete, não é edge.**

O backtest mostra o alerta vermelho sempre que a taxa fica abaixo do ponto
de equilíbrio. Isso é intencional: prefiro que a tela te diga a verdade a
te entregar um número bonito.

## 5. Consultas no terminal

```bash
python -m tools.relatorio
```

```bash
python -m tools.relatorio --ativo BTCUSD
```

```bash
python -m tools.relatorio --por-hora
```

Ou duplo clique em `consultar.bat`.

## 6. Calculadoras

| Ferramenta | Para que serve |
|---|---|
| Staking | quanto apostar e qual taxa é o ponto de equilíbrio |
| Valor do pip | quanto vale 1 pip em dinheiro real |
| Drawdown | quanto % é preciso ganhar para se recuperar |
| Margem | margem exigida por alavancagem |
| Plano de risco | quantos trades até estourar limites de prop firm |

## 7. Fonte de dados

Fonte única: **IQ Option**, pela mesma sessão autenticada.

| Mercado | Ativos | Velas |
|---|---|---|
| Forex | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, EURJPY, GBPJPY, NZDUSD | IQ |
| Cripto | BTCUSD, ETHUSD | IQ |
| OTC | 13 pares (EURUSD-OTC, GBPUSD-OTC, XAUUSD-OTC, ...) | IQ |

O OTC **não é mais simulado**. Antes os ativos `_OTC` usavam preços
gerados por nós (`app/feeds/otc_sim.py`, removido): serviam para estudar o
motor, mas eram inúteis para operar, porque o preço não era o da
corretora. Agora cada `SYMBOL_OTC` aponta para o ativo real da IQ
(`canonical` = `"EURUSD-OTC"`, com hífen), e tanto a análise quanto o
resultado de cada sinal saem do fechamento real da vela.

Consequência prática: tudo que aparece no dashboard é auditável contra a
plataforma da corretora.

### Ativar a IQ Option

```bash
set IQ_EMAIL=seu@email.com && set IQ_PASSWORD=suasenha && python run.py
```

Sem credenciais, ou se a conexão falhar, o dashboard fica sem fonte e
mostra o erro em `/api/health`. Não há mais feed alternativo.

## 8. API

Documentação interativa em `http://127.0.0.1:8000/docs`.

| Método | Rota | O que retorna |
|---|---|---|
| GET | `/api/health` | status e feeds |
| GET | `/api/assets` | ativos, preços, avaliação |
| GET | `/api/signals` | sinais recentes |
| GET | `/api/stats` | track record |
| POST | `/api/backtest` | replay da estratégia |
| WS | `/ws` | feed ao vivo |

## 9. Aviso honesto

O que este sistema **não** faz: prever o mercado com 93% de acerto. Isso não
existe, e qualquer site que prometa isso está vendendo confiança, não
estatística. O que ele faz: registrar cada sinal antes do resultado,
liquidar contra o preço real da fonte, e mostrar a taxa verdadeira —
inclusive quando ela é ruim.
