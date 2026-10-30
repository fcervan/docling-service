# Docling Service

[![CI](https://github.com/fcervan/docling-service/actions/workflows/ci.yml/badge.svg)](https://github.com/fcervan/docling-service/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docling](https://img.shields.io/badge/Docling-2.145.0-orange.svg)](https://github.com/docling-project/docling)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white)](Dockerfile)
[![Tests](https://img.shields.io/badge/tests-34%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/fcervan/docling-service/main?label=last%20commit)](https://github.com/fcervan/docling-service/commits/main)

Serviço HTTP independente que recebe **um documento** e devolve o **texto estruturado** no formato JSON do Docling, pronto para RAG, indexação ou uso por qualquer aplicação.

A imagem é autocontida e roda em qualquer host com Docker. A autenticação é feita por API key, com limites de tamanho, tipo de arquivo, timeout e rate limit. PDFs digitalizados são processados com OCR (RapidOCR), com os modelos já cacheados na imagem.

> **Segurança:** este repositório não contém chaves, tokens, usuários ou senhas. O `.env` é ignorado pelo Git e o serviço guarda apenas o **hash SHA-256** das API keys. Em produção, defina `DOCLING_DOCS_ENABLED=0`.

## Contrato

`POST /v1/convert` — `multipart/form-data`, um arquivo por requisição.

Headers:

```
X-API-Key: <sua-api-key>
```

Resposta `200`:

```json
{
  "schema_version": "1",
  "docling_version": "2.145.0",
  "filename": "manual.pdf",
  "tabelas": 3,
  "markdown": "# Manual\n\n...",
  "document": { "...export_to_dict() do Docling..." }
}
```

- `document`: estrutura completa do Docling (`texts`, `tables`, `body`, `prov`, etc.).
- `markdown`: versão plana, útil para apps que não querem conhecer o JSON interno.
- `tabelas`: quantidade de tabelas detectadas.

Erros: `400` arquivo inválido/vazio, `401` sem key ou key inválida, `413` acima do limite, `415` extensão/MIME não permitido, `422` falha de conversão, `429` rate limit, `503` auth não configurada, `504` timeout.

## Endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `GET` | `/health` | não | Liveness para health check |
| `GET` | `/v1/info` | não | Versões, formatos e limites (sem segredos) |
| `POST` | `/v1/convert` | `X-API-Key` | Converte um documento |
| `GET` | `/docs` | não | OpenAPI interativo |

Formatos aceitos: **PDF, DOCX, PPTX, XLSX, CSV, HTML, HTM, XML, TXT, MD**.

## Rodando localmente

```bash
cp .env.example .env
python scripts/gerar_api_key.py
```

O script imprime:

- `DOCLING_API_KEY=...` → vai **somente** no app consumidor;
- `DOCLING_API_KEYS={"app":"<sha256>"}` → vai no `.env` do serviço.

Preencha o `.env` do serviço com a linha `DOCLING_API_KEYS` e suba com Compose:

```bash
docker compose up -d --build
docker compose logs -f
```

Teste:

```bash
curl -X POST http://localhost:8765/v1/convert \
  -H "X-API-Key: <sua-api-key>" \
  -F "file=@manual.pdf"
```

Para desenvolvimento sem Docker:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765
```

## Configuração via `.env`

O `docker-compose.yml` usa `env_file: .env`, então o container lê as variáveis **no momento em que é criado**. O `.env` é local e está no `.gitignore`; o `.dockerignore` também impede que ele seja copiado para a imagem. Nunca versione esse arquivo.

Fluxo inicial:

```bash
cp .env.example .env
python scripts/gerar_api_key.py
```

O script gera dois valores:

- `DOCLING_API_KEY=...` → fica **somente** no `.env` do app consumidor.
- `DOCLING_API_KEYS={"app":"<sha256>"}` → vai no `.env` **deste serviço**.

Exemplo de `.env` com duas aplicações:

```dotenv
DOCLING_API_KEYS={"app-a":"<sha256-da-key-a>","app-b":"<sha256-da-key-b>"}
DOCLING_MAX_UPLOAD_MB=50
DOCLING_CONVERT_TIMEOUT=300
DOCLING_RATE_LIMIT_PER_MINUTE=60
DOCLING_MAX_WORKERS=2
DOCLING_SCHEMA_VERSION=1
DOCLING_DOCS_ENABLED=1
```

O valor de `DOCLING_API_KEYS` é um JSON em uma única linha. Cada hash precisa ter 64 caracteres hexadecimais; qualquer outro valor impede a inicialização do serviço.

### Recarregando o `.env`

Docker **não** altera as variáveis de um container já criado. Por isso:

- `docker compose restart` reinicia o processo com o ambiente antigo — **não recarrega** o `.env`.
- `docker compose up -d` nem sempre recria o container quando apenas o conteúdo do `env_file` mudou.
- `docker compose up -d --force-recreate` recria o container e garante a leitura do `.env` atualizado.

```bash
# depois de adicionar ou trocar uma key no .env
docker compose up -d --force-recreate
docker compose logs -f
```

O `--force-recreate` **não** reconstrói a imagem; ele apenas recria o container. Use `--build` quando mudar código, `Dockerfile`, `requirements*.txt` ou `scripts/prefetch_models.py`:

| Situação | Comando |
|---|---|
| Primeira subida ou mudança de código/imagem | `docker compose up -d --build` |
| Mudou apenas o `.env` | `docker compose up -d --force-recreate` |
| Quer só ver logs/status | `docker compose logs -f` / `docker compose ps` |
| Parar e remover o container | `docker compose down` |

Sem `DOCLING_API_KEYS` configurado, o serviço responde `503` (fail-closed).

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `DOCLING_API_KEYS` | vazio | JSON `{app: sha256hex}` ou `app:hash,app2:hash`. **Vazio = falha fechada (503).** |
| `DOCLING_MAX_UPLOAD_MB` | `50` | Tamanho máximo por arquivo |
| `DOCLING_CONVERT_TIMEOUT` | `300` | Timeout da conversão em segundos |
| `DOCLING_RATE_LIMIT_PER_MINUTE` | `60` | Requisições/min por app (`0` desliga) |
| `DOCLING_MAX_WORKERS` | `2` | Conversões paralelas por processo |
| `DOCLING_SCHEMA_VERSION` | `1` | Versão do contrato devolvida ao cliente |
| `DOCLING_DOCS_ENABLED` | `1` | Expõe `/docs` e `/openapi.json`; use `0` em produção |

## Segurança

- **Fail-closed**: sem `DOCLING_API_KEYS` configurado, `/v1/convert` responde `503`.
- **Somente hashes**: o serviço compara SHA-256 em tempo constante (`hmac.compare_digest`).
- **Uma key por aplicação**: revogação/rotação independentes (aplicadas ao recriar o container/redeploy), com rate limit por app.
- **Sem SSRF**: apenas upload; não há conversão por URL nem por caminho informado pelo cliente.
- **Allowlist**: extensão e MIME validados; tipos executáveis são rejeitados.
- **Tamanho e timeout**: limites configuráveis para evitar PDF bombs/arquivos gigantes.
- **Temp isolado**: cada conversão usa diretório temporário próprio, removido ao final.
- **Recursos limitados**: rode em container com CPU/memória limitadas; a descompressão interna de formatos Office é feita pelo Docling.
- **Erros genéricos**: detalhes internos/stack trace não vão para o cliente.
- **Container non-root**, healthcheck e modelos de layout/tabela/OCR baixados e cacheados no build via `scripts/prefetch_models.py` (sem egress em runtime).
- **Nunca loga** a API key nem o conteúdo do documento.

Nunca faça commit de `.env`, chaves em README, prints ou variáveis de CI. Em produção, injete as chaves por variável de ambiente ou pelo gerenciador de segredos da sua infraestrutura.

## Deploy

A imagem é autocontida e pode rodar em Docker, Docker Compose, Kubernetes ou qualquer orquestrador de containers:

```bash
docker compose up -d --build
```

Para usar a imagem em outro orquestrador, publique `docling-service:latest` e injete `DOCLING_API_KEYS` por variável de ambiente/secret.

Recomendações:

- Exponha o serviço atrás de um proxy reverso com **HTTPS**.
- Injete `DOCLING_API_KEYS` via secret manager ou variável de ambiente do orquestrador.
- Mantenha `DOCLING_DOCS_ENABLED=0` em exposição pública.
- Configure limites de CPU/memória e use **1 worker** por instância (o Docling é pesado em memória).
- Se houver arquivos grandes ou picos, evolua para assíncrono (`POST /v1/jobs` + `GET /v1/jobs/{id}`) mantendo o `/v1/convert`.
- O timeout usa thread + `asyncio.wait_for`; a thread não é morta à força. Para cancelamento real, use processo separado/fila.

## Testes

Os testes não instalam nem executam o Docling (dublado por stubs):

```bash
pip install -r requirements-dev.txt
ruff check app tests && ruff format --check app tests
pytest tests/ -q --cov=app --cov-report=term-missing
```

## Estrutura

```
docling-service/
├── app/
│   ├── main.py       # FastAPI, validações, endpoint /v1/convert
│   ├── auth.py       # API key (SHA-256) + rate limit por app
│   ├── converter.py  # wrapper lazy do Docling
│   ├── config.py     # env, allowlists e limites
│   └── schemas.py    # contrato Pydantic
├── scripts/gerar_api_key.py
├── scripts/prefetch_models.py
├── assets/prefetch.pdf   # usado só no build para cachear modelos
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── LICENSE
└── .env.example
```

## Consumindo de outro app (Python)

```python
import httpx

with open("manual.pdf", "rb") as fh:
    resp = httpx.post(
        "https://docling.exemplo.interno/v1/convert",
        headers={"X-API-Key": settings.docling_api_key},
        files={"file": ("manual.pdf", fh, "application/pdf")},
        timeout=300,
    )
resp.raise_for_status()
dados = resp.json()
texto_md = dados["markdown"]
documento = dados["document"]
```

## Licença

Distribuído sob a licença MIT — veja [LICENSE](LICENSE).
