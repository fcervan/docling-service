# Docling Service

Serviço HTTP que recebe **um documento** e devolve o **texto estruturado** no formato JSON do Docling, pronto para RAG, indexação ou uso por qualquer aplicação.

Extraído do projeto `assistente-suporte` para ser reutilizado por vários apps, com autenticação por API key, limites de segurança e deploy independente (AWS).

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
| `GET` | `/health` | não | Liveness para ALB/ECS |
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

Preencha o `.env` do serviço com a linha `DOCLING_API_KEYS` e suba:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Teste:

```bash
curl -X POST http://localhost:8000/v1/convert \
  -H "X-API-Key: <sua-api-key>" \
  -F "file=@manual.pdf"
```

Ou via Docker:

```bash
docker build -t docling-service .
docker run --rm -p 8000:8000 --env-file .env docling-service
```

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
- **Uma key por aplicação**: revogação/rotação independentes (aplicadas no restart/redeploy), com rate limit por app.
- **Sem SSRF**: apenas upload; não há conversão por URL nem por caminho informado pelo cliente.
- **Allowlist**: extensão e MIME validados; tipos executáveis são rejeitados.
- **Tamanho e timeout**: limites configuráveis para evitar PDF bombs/arquivos gigantes.
- **Temp isolado**: cada conversão usa diretório temporário próprio, removido ao final.
- **Recursos limitados**: rode em container com CPU/memória limitadas; a descompressão interna de formatos Office é feita pelo Docling.
- **Erros genéricos**: detalhes internos/stack trace não vão para o cliente.
- **Container non-root**, healthcheck e modelos baixados/cacheados no build via `assets/prefetch.pdf` (sem egress em runtime).
- **Nunca loga** a API key nem o conteúdo do documento.

Nunca faça commit de `.env`, chaves em README, prints ou variáveis de CI. Em produção use **AWS Secrets Manager** ou **SSM Parameter Store**.

## Deploy na AWS

Sugestão para começar (síncrono):

1. **ECR**: build e push da imagem.
2. **Secrets Manager**: segredo com `DOCLING_API_KEYS` (JSON de hashes), injetado nas tasks (rotação = novo deploy, sem rebuild).
3. **ECS Fargate**: 4 vCPU / 8 GB, 1 task, autoscaling por CPU, health check `/health`.
4. **ALB interno** + TLS (ACM) + AWS WAF; subnets privadas.
5. **CloudWatch Logs** e alarmes de 5xx/latência.
6. **Idle timeout do ALB** ≥ `DOCLING_CONVERT_TIMEOUT` (ex.: 300s).

Notas:

- **Evite API Gateway** no caminho síncrono: o limite de 29s é menor que conversões grandes.
- Se arquivos grandes/picos passarem a incomodar, evolua para assíncrono (SQS + `POST /v1/jobs` + `GET /v1/jobs/{id}`) mantendo o `/v1/convert`.
- O timeout usa thread + `asyncio.wait_for`; a thread não é morta à força. Para cancelamento real, use processo separado/fila.
- Rode **1 worker** por task: o Docling é pesado em memória.

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
├── assets/prefetch.pdf   # usado só no build para cachear modelos
├── tests/
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
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

No `assistente-suporte`, o módulo `api/src/ingest_docling.py` é esse cliente HTTP — ele persiste `markdown` e `document` em `data/processed` para manter `reingest_v2` e o chunking atuais funcionando.
