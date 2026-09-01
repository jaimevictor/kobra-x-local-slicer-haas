# Verificação física v2 (NÃO automatizada)

Não execute o start físico sem estar junto à Kobra X. Nenhuma destas verificações é simulada
pelos testes unitários.

1. Confirme que `anycubic_cloud` está conectado em LAN Mode no Home Assistant e escolha a
   impressora pelo fluxo de descoberta do add-on. Não mapeie entidades manualmente.
2. Consulte `GET /api/printer/integration`: `telemetry_from_ha` e `ace_from_ha` devem ser verdadeiros,
   enquanto `local_start_via_ha` deve continuar falso no baseline atual.
3. Verifique que `GET /api/printer/state` mostra o ACE correto e que nenhuma conexão MQTT/poller
   adicional do Print Manager aparece nos logs.
4. Faça slice do cubo de 20 mm e confirme que o snapshot de ACE salvo no job corresponde ao slot
   escolhido. Troque o spool antes do preflight e confirme que o job é bloqueado para nova confirmação.
5. Com mesa livre, envie o job. Observe um único upload HTTP local e exatamente uma publicação de
   start. Não clique novamente se o estado for `START_UNKNOWN`.
6. Confirme nas entidades HA o filename, `is_busy`, progresso, camadas e temperaturas. Só então o
   job deve alcançar `MONITORING`.
7. Teste pause, resume e cancel pelos endpoints do job; confirme no histórico do job a chamada
   `button.press` e a transição de estado posterior. HTTP 200 isoladamente não é confirmação física.
8. Reinicie o add-on durante uma impressão. Confirme que o job é reconstruído pelo estado HA sem
   uma nova publicação de start.

Se a etapa 5 ficar ambígua, mantenha `START_UNKNOWN`, não reenvie e investigue por telemetria do
Home Assistant e logs sem credenciais.
