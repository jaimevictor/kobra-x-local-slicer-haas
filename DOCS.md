# Operação local

O add-on usa Ingress e expõe somente Nginx na porta interna 8099; FastAPI escuta em loopback.
O armazenamento persistente fica em `/data/jobs/<uuid>` e os perfis resolved são somente leitura
em `/opt/kobra/profiles/resolved`.

## Verificação sem hardware

Use Python 3.12 ou superior, pois `anycubic-cloud-api==0.4.26` exige essa versão.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r kobra_x_local_slicer/requirements-dev.txt
pytest -q -m 'not hardware'
python -m compileall -q kobra_x_local_slicer/app
```

`scripts/build_addon.sh` requer Docker local. O CI executa build amd64, verifica a AppImage
pela soma SHA-256, extrai a AppImage sem FUSE e faz o smoke test HTTP da imagem.

## Limite físico

O endpoint de início físico exige simultaneamente `KOBRA_HARDWARE_TEST=1` e
`KOBRA_ALLOW_PHYSICAL_PRINT=1`. Essas variáveis não são habilitadas pelo build, pelo frontend
nem pelos testes automáticos.
