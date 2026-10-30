# AGENTS.md — docling-service

Serviço HTTP independente que converte documentos no JSON estruturado do Docling. O README não deve assumir um consumidor específico nem nuvem específica (AWS etc.); o projeto é reutilizável por qualquer aplicação.

## Stack

- Python 3.12, FastAPI, Docling 2.145.0, RapidOCR.
- Docker + Docker Compose; porta **8765** no host e no container.
- pytest + pytest-cov, ruff 0.17.0.
- Auth por API key com hash SHA-256 e rate limit por aplicação.

## Arquitetura

- `app/main.py` — rotas, validações de upload/MIME, timeout e resposta.
- `app/auth.py` — verificação da API key (`hmac.compare_digest`) e rate limit.
- `app/converter.py` — wrapper lazy do Docling.
- `app/config.py` — parsing de env, allowlists e limites.
- `app/schemas.py` — contrato Pydantic.
- `scripts/gerar_api_key.py` — gera a key em texto puro + hash SHA-256.
- `scripts/prefetch_models.py` — baixa/cacheia modelos de layout, tabela e OCR no build.
- `assets/prefetch.pdf` — fixture dummy usada no build; não é documento pessoal.

## Segredos e `.env`

- `.env` é local, está no `.gitignore` e nunca deve ser versionado.
- `.dockerignore` impede que `.env` entre na imagem.
- `.env.example` é o template versionado; nunca coloque valores reais nele.
- `DOCLING_API_KEYS` guarda `{"app": "<sha256hex>"}` ou `app:<hash>,app2:<hash>`. Cada hash deve ter 64 caracteres hexadecimais; strings arbitrárias são rejeitadas.
- A key em texto puro fica **somente** no app consumidor.
- Sem `DOCLING_API_KEYS`, o serviço falha fechado (`503`).
- Alterou o `.env`? Recrie o container: `docker compose up -d --force-recreate`.
- `docker compose restart` **não** relê o `env_file`; `docker compose up -d` sozinho não garante a recriação quando só o conteúdo do `.env` mudou.
- `docker-compose.override.yml` é local/ignorado e não deve ser versionado.

## Comandos

```bash
cp .env.example .env
python scripts/gerar_api_key.py

docker compose up -d --build          # primeira subida ou mudança de código/imagem
docker compose up -d --force-recreate # recarregar o .env
docker compose ps
docker compose logs -f
docker compose down

curl -s http://localhost:8765/health
curl -s http://localhost:8765/v1/info
curl -s -X POST http://localhost:8765/v1/convert \
  -H "X-API-Key: <key>" \
  -F "file=@documento.pdf"
```

## Testes e lint

Os testes dublam o Docling e não o instalam:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check app tests scripts
ruff format --check app tests scripts
pytest tests/ -q --cov=app --cov-report=term-missing
```

- Cobertura atual: 100% (`app/`).
- O CI roda `ruff` e `pytest` em `app`/`tests`.

## Regras do projeto

- Toda mudança de comportamento, contrato, variável de ambiente, endpoint ou estrutura exige atualização do `README.md` antes de encerrar.
- Mudanças em `app/` exigem teste correspondente; mantenha a cobertura em 100%.
- Não logar API key, conteúdo de documento ou dados pessoais.
- Não versionar PDFs de teste com dados pessoais; use arquivos sintéticos.
- Runtime roda como usuário non-root (`appuser`).
- O build padrão usa `DOCLING_PREFETCH=1`. Use `--build-arg DOCLING_PREFETCH=0` apenas quando quiser pular o download dos modelos (a imagem não ficará pronta para uso offline).
- Não fazer `git add/commit/push` sem confirmação explícita do usuário.
- Ao commitar, mostrar a saída do push.
