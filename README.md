# Previsione del carico di lavoro e pianificazione degli ispettori con NYC 311

Il sistema prevede quante richieste di servizio riceverà un dipartimento della città di New York **con due giorni di anticipo**. Traduce la previsione in un **carico di lavoro stimato** e in un **numero di ispettori da assegnare**. Genera anche **avvisi** quando il volume delle richieste è anomalo o i dati mostrano possibili problemi.

Il progetto usa i dati reali di NYC 311 del 2023 e del 2024 e si concentra soprattutto sull’HPD, il dipartimento per la tutela e lo sviluppo dell’edilizia abitativa. Per aggiungere un dipartimento basta un nuovo file di configurazione.

[App screenshot](docs/app.png)

## Cosa vede chi pianifica il personale

- Il numero di richieste attese e il carico di lavoro stimato per dopodomani.
- Il numero di ispettori da assegnare, con un margine di sicurezza calcolato in base al **livello di servizio** scelto. Per esempio, con un livello del 90%, l’obiettivo è avere abbastanza ispettori per coprire il carico effettivo nel 90% delle giornate.
- Avvisi per volumi insoliti e possibili problemi di qualità dei dati.
- Tre modi di distribuire gli interventi della giornata tra gli ispettori, confrontati in base all’equilibrio dei carichi e alla priorità data agli interventi urgenti.

## Risultati

La valutazione copre tutti i mesi del 2024. Per ogni mese, il modello è stato riaddestrato usando solo i dati dei mesi precedenti. Le giornate con interruzioni note nella registrazione dei dati sono state gestite come descritto nella sezione sulla qualità dei dati. L’errore è misurato con il **WAPE**, cioè la somma degli errori assoluti divisa per la somma dei valori osservati. Più basso è il WAPE, più accurata è la previsione.

| Errore sul numero di richieste (WAPE) | DOT | DSNY | HPD |
|---|---:|---:|---:|
| Baseline: media dello stesso giorno della settimana nelle quattro settimane precedenti | 13,9% | 12,8% | 25,8% |
| **Modello finale: regressione di Poisson** | **10,6%** | **10,6%** | **17,2%** |
| Riduzione relativa dell’errore rispetto alla baseline | 24% | 17% | 33% |

Per l’HPD:

- **Carico di lavoro.** Il WAPE scende al **12,4%** quando le richieste vengono convertite in unità di lavoro.
- **Bias.** L’errore medio con segno è pari a **+1,3%**, un valore vicino allo zero.
- **Margine di sicurezza.** Un margine fisso del **10%** sarebbe bastato nel **70%** delle giornate. Per raggiungere una copertura del **90%** è servito un margine del **24%**. Per arrivare al **95%** è servito un margine del **49%**. Con un organico dimensionato sulla sola previsione puntuale, la capacità sarebbe risultata insufficiente in circa metà delle giornate. L’app calibra quindi il margine sugli errori storici.
- **Avvisi.** Nel periodo di valutazione, il sistema ha segnalato **15** giornate anomale per l’HPD, **16** per il DOT e **4** per il DSNY.

## Come avviare il progetto

```bash
pip install -r requirements.txt
python scripts/download_311.py                 # Scarica i dati (richiede qualche minuto)
python scripts/load_to_sqlite.py               # Crea il database data/311.db
streamlit run app.py                          # Avvia l’interfaccia web
python -m engine.run --config configs/hpd.yaml --date 2024-12-18
python -m pytest -q                            # Esegue i test
```

Per riprodurre i risultati del README:

```bash
python -m scripts.compare_models    # Confronta baseline e modelli
python -m scripts.check_bias        # Calcola bias e margini di sicurezza
python -m scripts.compare_groups    # Confronta 2 gruppi con 7 gruppi
```

## Come funziona

1. **Pulizia dei dati** (`engine/data.py`). Segnala le date incoerenti e le chiusure istantanee. Uniforma le etichette dei tipi di segnalazione scritte con maiuscole e minuscole diverse.
2. **Previsione** (`engine/forecast.py`). La regressione di Poisson usa il giorno della settimana, le festività e i volumi recenti. Per l’HPD, il modello prevede separatamente le richieste relative al riscaldamento e tutte le altre. La temperatura entra solo nel modello per il riscaldamento.
3. **Stima del carico** (`engine/workload.py`). Il peso di una richiesta è pari alla mediana dei tempi di risoluzione del suo gruppo divisa per la mediana complessiva. Il fabbisogno di ispettori si calcola moltiplicando il carico previsto per `(1 + margine)` e dividendo il risultato per la capacità giornaliera di un ispettore.
4. **Margine di sicurezza** (`engine/risk.py`). Il sistema usa il quantile degli errori di previsione degli ultimi 365 giorni corrispondente al livello di servizio scelto.
5. **Avvisi** (`engine/anomaly.py`). Uno z-score robusto, calcolato usando gli errori di previsione dei 60 giorni precedenti, individua volumi anomali. Un secondo controllo segnala i giorni con volumi molto inferiori a quelli tipici dello stesso giorno della settimana, un possibile indizio di dati incompleti.
6. **Assegnazione degli interventi** (`engine/allocate.py`). L’app confronta l’assegnazione a rotazione (*round robin*), un algoritmo *greedy* che dà priorità agli interventi urgenti e un metodo di ottimizzazione basato su OR-Tools CP-SAT.
7. **Configurazione dei dipartimenti** (`configs/`). Ogni file YAML specifica l’agenzia, i gruppi di segnalazioni, le date con dati incompleti, la capacità per ispettore e il livello di servizio.

```text
engine/      Moduli del motore e interfaccia a riga di comando
configs/     Un file YAML per ciascun dipartimento
scripts/     Download, caricamento dei dati e riproduzione dei risultati
notebooks/   Analisi esplorative ed esperimenti, inclusi quelli scartati
tests/       Test automatici
app.py       Interfaccia web
```

## Esperimenti e scelte progettuali

| Decisione | Alternative provate | Risultati | Scelta finale |
|---|---|---|---|
| Modello | Regressione di Poisson, regressione ridge, gradient boosting, random forest | WAPE per HPD / DOT / DSNY, in percentuale. Poisson 17,2 / 10,6 / 10,6. Ridge 16,7 / 10,7 / 10,7. Gradient boosting 22,4 / 13,6 / 13,1. Random forest 20,8 / 11,7 / 11,8. | **Poisson.** I due modelli lineari hanno superato i modelli ad alberi. Ridge ha registrato un errore circa il 3% più basso per l’HPD, mentre Poisson ha ottenuto risultati leggermente migliori per DOT e DSNY. Poisson è adatta a modellare conteggi e produce previsioni non negative. |
| Mese come variabile | Con e senza il mese | In `notebooks/01_explore.ipynb`, includere il mese ha peggiorato le previsioni. | Mese escluso. |
| Temperatura | Con e senza dati meteo | Nei test del notebook, la temperatura ha migliorato le previsioni delle richieste di riscaldamento dell’HPD. Per le altre agenzie non sono emersi miglioramenti. | Temperatura usata solo per il gruppo riscaldamento dell’HPD. |
| Riscaldamento e altre richieste | Un modello unico oppure due modelli distinti | Le richieste relative al riscaldamento sono numerose e si risolvono più rapidamente. Modellarle separatamente ha migliorato la stima del carico di lavoro. | Due gruppi per l’HPD. |
| Suddivisione del gruppo «altre richieste» | 2 gruppi complessivi oppure 7 | Con 2 e 7 gruppi, il WAPE sul carico è rispettivamente del 12,4% e del 12,3%. Nello stesso confronto, i margini per una copertura del 90% sono del 20,6% e del 20,1%. | Due gruppi. La soluzione con sette modelli richiede circa il triplo del tempo di calcolo. L’app stima il dettaglio delle «altre richieste» in base alle proporzioni osservate di recente. |
| Margine di sicurezza | Margine fisso del 10% | Il margine fisso copriva il carico effettivo nel 70% delle giornate. | Margine calibrato sugli errori storici in base al livello di servizio. |
| Assegnazione | Rotazione, greedy per urgenza, ottimizzazione | Con 300 interventi sintetici e 39 ispettori, il carico massimo per ispettore è stato rispettivamente di 11,6 / 8,6 / 7,3 unità. La differenza tra il carico massimo e quello minimo è stata di 8,0 / 2,3 / 0,6 unità. | Nel test, l’ottimizzazione ha distribuito il carico in modo più uniforme. Il metodo greedy ha dato precedenza agli interventi urgenti. |
| Valutazione | Un’unica suddivisione tra addestramento e test oppure riaddestramento mensile | Il riaddestramento mensile riproduce l’ordine cronologico con cui si accumulano i dati sulle richieste. | Valutazione con riaddestramento mensile sui dati dei mesi precedenti. |

## Problemi riscontrati nei dati

- I tipi di segnalazione scritti con maiuscole e minuscole diverse, come `Heat/Hot Water` e `HEAT/HOT WATER`, venivano conteggiati separatamente. Le etichette sono state uniformate in maiuscolo.
- Le richieste chiuse prima della loro apertura o nello stesso istante sono state escluse dal calcolo dei tempi di risoluzione.
- Per l’HPD, dall’11 al 15 aprile e dall’11 al 14 luglio 2024 sono state registrate zero richieste. Queste giornate sono state escluse dall’addestramento e dal calcolo degli avvisi. Per le variabili che usano i conteggi dei giorni precedenti, i valori mancanti sono stati sostituiti con la media dello stesso giorno della settimana di due e tre settimane prima.
- Il 16 e il 17 marzo 2024 si sono osservati volumi molto bassi. Il 19 marzo si è invece registrato un picco di **5.285 richieste**, a fronte di **2.691 previste**. La causa di questi scostamenti resta sconosciuta. Le giornate sono state mantenute nei dati e segnalate dal sistema.

## Limiti

- Le impostazioni del modello sono state scelte anche alla luce dei risultati del 2024. Gli errori riportati potrebbero quindi essere leggermente ottimistici. Una valutazione indipendente sui dati del 2025 permetterebbe di verificare le prestazioni.
- I **tempi di risoluzione sono un indicatore indiretto del carico** e comprendono anche i tempi di attesa. La capacità giornaliera per ispettore è un parametro da impostare in base all’operatività del dipartimento.
- Nei test, il modello usa la **temperatura osservata nel giorno da prevedere**. In produzione servirebbe un servizio di previsioni meteo che fornisca la temperatura attesa con due giorni di anticipo.
- Le previsioni sono meno accurate nei giorni successivi alle festività. Il modello, al momento, riconosce la festività stessa ma non il giorno successivo.
- Il dettaglio delle «altre richieste» per tipo di segnalazione è stimato in base alle proporzioni osservate di recente. La previsione del modello riguarda il totale del gruppo.
- **Modalità demo.** I dati arrivano al 31 dicembre 2024. L’app simula previsioni per date passate usando lo storico delle richieste disponibile due giorni prima. Per il meteo vale il limite descritto sopra.

## Fonti dei dati

- **NYC Open Data**, dataset *311 Service Requests* (`erm2-nwe9`). Richieste aperte tra il 1° gennaio 2023 e il 31 dicembre 2024 per HPD, DOT e DSNY, di cui circa 1,4 milioni per l’HPD.
- **Open-Meteo**, dati storici sulla temperatura.







# ENGLISH VERSION:

# Workload Forecasting and Staffing Engine (NYC 311)

Forecasts how many service requests a city agency will receive **two days ahead**, turns the forecast into a **workload and a number of inspectors**, and raises **alerts** when the volume or the data looks wrong. It is built on real NYC 311 data (2023–2024), mainly for the housing agency (HPD), and a new department only needs a new config file.

[App screenshot](docs/app.png) 

## What a manager gets
- Expected requests and workload for the day after tomorrow.
- The number of inspectors needed, with a safety margin the manager chooses as a **service level** ("enough inspectors on 90% of days").
- Alerts for unusual volume and for possible data problems.
- Three ways to split a day's tasks between inspectors, compared on fairness and urgency.

## Results
Tested on every day of 2024. Each month was predicted by a model trained **only on earlier data** (retrained month by month), so the future is never used. Error is WAPE (the average error as a percentage of the real counts; lower is better).

| Request count error (WAPE) | DOT | DSNY | HPD |
|---|---|---|---|
| Simple rule: average of the same weekday over the last 4 weeks | 13.9% | 12.8% | 25.8% |
| **Final model (Poisson regression)** | **10.6%** | **10.6%** | **17.2%** |
| Improvement over the rule | 24% | 17% | 33% |

Other results (HPD):
- **Workload error** (requests converted to effort): 12.4%.
- **Bias:** the average error is +1.3%, so the forecast is not systematically too high or too low.
- **Safety margin:** a fixed 10% margin would have been enough on only **70%** of days. A margin of **24%** covers 90% of days, and **49%** covers 95%. A forecast is an average, so a manager who staffs exactly to it is short on about half of the days. This is why the app learns the margin from past errors.
- **Alerts:** in the test period the alert system flagged 15 unusual days for HPD, 16 for DOT and 4 for DSNY.

## Run it
```
pip install -r requirements.txt
python scripts/download_311.py                 # download the data (a few minutes)
python scripts/load_to_sqlite.py               # build data/311.db
streamlit run app.py                           # web interface
python -m engine.run --config configs/hpd.yaml --date 2024-12-18    # command line
python -m pytest -q                            # tests
```

To reproduce the numbers in this README:
```
python -m scripts.compare_models    # baselines and model comparison
python -m scripts.check_bias        # bias and safety margin
python -m scripts.compare_groups    # 2 groups vs 7 groups
```

## How it works
1. **Clean** (`engine/data.py`): flags impossible dates and instant closes, and merges complaint types written in different upper/lower case.
2. **Forecast** (`engine/forecast.py`): Poisson regression on the weekday, holidays, recent request levels and, for heating complaints, the temperature. Heating complaints and all others are forecast separately.
3. **Workload** (`engine/workload.py`): the effort of one request is the median resolution time of its group divided by the overall median. Inspectors needed = effort × (1 + margin) ÷ capacity per inspector.
4. **Risk** (`engine/risk.py`): the margin is the quantile of the forecast errors of the last 365 days, for the chosen service level.
5. **Alerts** (`engine/anomaly.py`): a robust z-score of the forecast error over the previous 60 days flags unusual volume. A separate check flags days far below a normal day of the same weekday, which usually means a data problem.
6. **Allocation** (`engine/allocate.py`): round robin, greedy by urgency, and optimal (OR-Tools CP-SAT).
7. **Departments:** each one is a file in `configs/` (agency, complaint groups, broken-data days, capacity, service level).

```
engine/      final code (data, forecast, workload, risk, anomaly, allocate, run)
configs/     one .yaml file per department
scripts/     data download and loading, plus scripts that reproduce the results
notebooks/   exploration, including ideas that were tried and rejected
tests/       automatic tests
app.py       web interface
```

## Decisions: what I tried and what I kept
| Decision | Tried | Evidence | Kept |
|---|---|---|---|
| Model | Poisson regression, ridge, gradient boosting, random forest | WAPE for HPD / DOT / DSNY: Poisson 17.2 / 10.6 / 10.6, Ridge 16.7 / 10.7 / 10.7, gradient boosting 22.4 / 13.6 / 13.1, random forest 20.8 / 11.7 / 11.8 | **Poisson.** The two linear models beat the tree models. Poisson ties with Ridge (Ridge is 3% better on HPD); I chose Poisson because it models counts and never predicts negative numbers |
| Month as a feature | with / without | tested in `notebooks/01_explore.ipynb`: it made the forecast worse | without |
| Weather | with / without | tested in the notebook: it helps HPD (heating complaints), not the other agencies | HPD heating group only |
| Heating vs other | one model for everything / two groups | tested in the notebook: heating requests are many but quick to resolve, so splitting gives a much better workload forecast | two groups |
| Splitting "other" into 6 more types | 2 groups vs 7 groups | workload error 12.4% vs 12.3%, margin for 90% of days 20.6% vs 20.1% | 2 groups: seven models are about 3× slower for no real gain. The app shows an *estimated* split of "other" by recent shares |
| Safety margin | fixed 10% | enough on only 70% of days | service level learned from past errors |
| Allocation | round robin, greedy, optimal | on 300 synthetic tasks and 39 inspectors: busiest inspector 11.6 / 8.6 / 7.3, load gap 8.0 / 2.3 / 0.6 | trade-off documented: optimal is the fairest, greedy starts urgent tasks sooner |
| Evaluation | single train/test split | rolling monthly retraining | rolling: no future data is ever used |

## Data issues found
- Complaint types in mixed case (`Heat/Hot Water` vs `HEAT/HOT WATER`) were counted separately: fixed by upper-casing.
- Requests closed before they were created, or at the very same instant: excluded from resolution-time statistics.
- HPD reporting gaps (zero requests) on 11–15 April and 11–14 July 2024: kept out of training and alerts, and filled in the lag features with the average of the same weekday 2 and 3 weeks earlier.
- 16–17 March 2024 (very low) and 19 March 2024 (a spike: 5,285 requests against a forecast of 2,691) are unexplained. They are kept in the data, and the alert system flags them.

## Limitations
- The model settings were chosen while looking at the 2024 results, so the errors above may be slightly optimistic. A test on 2025 data would confirm them.
- **Effort is a proxy** (resolution time), not real working hours. **Capacity per inspector is an assumption**; a real user would enter their own.
- The forecast uses the actual weather of the forecast day. A live system would need a weather forecast service.
- Days after holidays are forecast poorly, because there is no feature for them yet.
- The split of "other" by type is an estimate (recent shares), not a separate forecast.
- Demo mode: the data ends on 31 December 2024, so the app forecasts past days using only the data available two days earlier.

## Data
NYC Open Data, *311 Service Requests* (dataset `erm2-nwe9`), agencies HPD, DOT and DSNY, created between 2023-01-01 and 2024-12-31 (about 1.4 million HPD requests). Weather: Open-Meteo.