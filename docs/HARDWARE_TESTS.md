# Procedimento físico conservador

Nenhuma etapa deste documento é executada automaticamente pelo projeto.

1. Configure apenas o IP LAN da Kobra X e mapeie todas as entidades obrigatórias do Home Assistant.
2. Com `KOBRA_HARDWARE_TEST` ausente, abra o add-on e confira o estado LAN e o cross-check do Home Assistant.
3. Consulte ACE; confirme o `raw`, `parsed` e o slot normalizado escolhido, que deve ser PLA.
4. Envie `20mm_cube.stl`, confira preview, dimensões, perfis resolved e SHA-256 de G-code.
5. Confirme que o G-code contém `G9111`, não contém `M600`/`T1`, tem temperaturas dentro do PLA e cabe em 260 mm.
6. Só para validação de upload, habilite `KOBRA_HARDWARE_TEST=1`, mantenha `KOBRA_ALLOW_PHYSICAL_PRINT` ausente e execute o fluxo até a confirmação. O endpoint continuará recusando o start físico; registre a resposta do upload somente se um mecanismo de upload isolado for adicionado para o teste.
7. Verifique visualmente na impressora que o arquivo remoto correto existe e que a mesa está livre.
8. Em sessão separada, com supervisão junto à impressora, habilite também `KOBRA_ALLOW_PHYSICAL_PRINT=1`, refaça preflight e confirmação e então pressione Imprimir uma única vez. Não repita o clique se houver timeout: o estado deve ser `START_UNKNOWN` e a reconciliação apenas consulta a impressora.

Se a etapa 8 falhar ou ficar incerta, desligue as flags e investigue usando telemetria e logs sem tokens.
