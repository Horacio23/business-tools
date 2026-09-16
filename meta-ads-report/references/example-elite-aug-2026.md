# Example: Elite Medspa Miami, August 2026

The first report this skill was built from (account `1057694063608120`, 1–31 Aug 2026).
It's here to calibrate depth, tone and how numbers turn into findings. **Don't copy any of it
into another client's deck.**

## Raw picture
- 4 campaigns, all `OUTCOME_LEADS` optimized for chat (`messaging_conversation_started_7d`),
  budgets $15/$15/$10/$10 per day. 10 ads with spend. Delivery started the week of Aug 8;
  July had no spend (the previous-month pull returned only id/name).
- Account: $921.93 spend · 25,372 impressions · 10,051 reach · freq 2.52 · CPM $36.34 ·
  661 clicks (all) · 198 link clicks · CTR 2.61% · CPC $1.39 · 4 leads.
- Results summed from campaigns: 23 + 22 + 22 + 35 = **102 conversations → $9.04 each**.

| Campaign | $/day | Spend | Conv. | Cost/conv | CTR | CPC | CPM | Freq | Leads |
|---|---|---|---|---|---|---|---|---|---|
| Láser | 10 | 180.45 | 35 | **5.16** | 2.76% | **0.91** | **25.14** | 1.72 | 3 |
| Cejas | 10 | 176.80 | 22 | 8.04 | **3.27%** | 1.33 | 43.44 | 1.96 | 0 |
| Botox | 15 | 268.78 | 23 | 11.69 | *1.97%* | *2.15* | 42.44 | 2.60 | 0 |
| Pérdida de Peso | 15 | 295.90 | 22 | *13.45* | 2.63% | 1.44 | 37.97 | 2.45 | 1 |

Weekly: 1–7 $0 · 8–14 $32.10 · 15–21 $367.27 · 22–28 $325.27 · 29–31 $197.29 (3 days).
CTR by week 2.14% → 2.53% → 2.71% → 2.70%. Chart scale max $400.

Share of spend vs conversations: Láser 20%→34%, Cejas 19%→22%, Botox 29%→23%, Peso 32%→22%.

Meta diagnosis highlights: "Botox - Chat" (original, $238.80, CTR 1.80%) engagement below
average → "no genera interés"; "Pérdida de Peso - Chat" quality below average;
"Pérdida de Peso - Chat - 3" spent $30.62 with 0 results; "Botox - Chat - 2" $6.00/conv;
Láser ads absent from the ranking output. Anomaly signal: no overlap, fatigue or narrow audience.

## Summary headline + lede
"102 conversaciones en el *primer mes*". "Con una inversión de $921.93, las campañas
generaron 102 conversaciones por chat a un promedio de $9.04 cada una. Los anuncios
empezaron a salir la semana del 8 de agosto."

## Findings (4)
1. **$5.16 por conversación** · Láser es el ganador del mes ($10/day, 34% of conversations, lowest CPM, 3 of 4 leads).
2. **CTR 1.80%** · El anuncio original de Botox se queda atrás (variant 2 at $6.00).
3. **4 anuncios · $15 al día** · Pérdida de Peso está muy repartida (one ad with $30.62 and zero results).
4. **Frecuencia 2.52** · No hay problemas de entrega (the fix is creative, not setup).

## Recommendations (4, client with no appointment measurement)
1. Subir Láser de $10 a $15 por día, taking the $5 from Pérdida de Peso.
2. Pausar el anuncio original de Botox and let variant 2 take the budget.
3. Limpiar Pérdida de Peso: pause "Chat - 3" and the original, focus on "Copy".
4. Dejar correr Cejas y Cejas Lamidas.

A 5th rec, "Medir citas, no solo conversaciones", was **removed** at the user's request.
That's why the appointment question in Step 0 exists.

## Brand used
Text wordmark "Élite" (Playfair Display italic) + "· MED SPA ·" (tracked caps). Tokens:
deep #221913, primary #392B23, accent #8D6E5E, accent-lt #C9A68C, ground #F8F6F1,
sand #F1ECE1, muted #70635C. Campaign colors: Láser #B07A52, Cejas #7D8B74,
Botox #392B23, Peso #CDB9A5 (light → `lt` label class).
