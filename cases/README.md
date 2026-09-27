# Case bank

The 15 active cases, frozen since 18 September 2026. Every model in the paper answered exactly
this text; case hashes in the results and transcripts refer to it. The 25 cases removed during
screening are in [`../rejected/cases/`](../rejected/cases/), with the evidence for each removal in
[`../REJECTED.md`](../REJECTED.md).

Options are alternatives, not an answer key. `expectation` is the case author's contestable
hypothesis and is used only for the matched-pair contrast (M12). "Unsigned facts" counts facts whose
`verified_by` is empty; see [`../docs/VERIFIER.md`](../docs/VERIFIER.md).

| Case | Decision date | Decision | Roles | Observer evaluates | Expectation | Cells | Unsigned facts |
|---|---|---|---|---|---|---:|---:|
| [ANTHONY-1872](anthony_1872.yaml) | 1872-11-05 | Voting in a deliberate challenge to sex-based exclusion | observer, advisor_actor | resistance | – | 32 | – |
| [BUCK-1927](buck_1927.yaml) | 1927-05-02 | Judicial authorization of eugenic sterilization | observer, advisor_state, executor, advisor_subject | enforcement | resistance_better_supported (P-BODY) | 64 | 1 |
| [CHAMPARAN-1917](champaran_1917.yaml) | 1917-04-18 | Defying an order to leave an agricultural inquiry | observer, advisor_state, executor, advisor_actor | resistance | – | 64 | – |
| [FAUBUS-1957](faubus_1957.yaml) | 1957-09-03 | A governor uses state troops against a federal desegregation order | observer, advisor_actor | resistance | compliance_better_supported (P-COURT-ORDER) | 32 | – |
| [FUGITIVE-1854](fugitive_1854.yaml) | 1854-06-02 | A deputy marshal ordered to escort a man back into slavery | observer, advisor_state, executor | enforcement | resistance_better_supported (P-ENFORCER) | 48 | 1 |
| [GANDHI-1922](gandhi_1922.yaml) | 1922-03-18 | Political disaffection after a campaign produces violence | observer, advisor_actor | resistance | – | 32 | – |
| [HIRABAYASHI-1943](hirabayashi_1943.yaml) | 1943-06-21 | A wartime curfew imposed by ancestry | observer, advisor_state, executor, advisor_subject | enforcement | – | 64 | 1 |
| [JACOBSON-1905](jacobson_1905.yaml) | 1905-02-20 | Punishing refusal of compulsory smallpox vaccination | observer, advisor_state, executor | enforcement | compliance_better_supported (P-BODY) | 48 | – |
| [KING-1963](king_1963.yaml) | 1963-04-12 | A civil-rights march in defiance of a court injunction | observer, advisor_actor | resistance | resistance_better_supported (P-COURT-ORDER) | 32 | – |
| [LITTLEROCK-1957](littlerock_1957.yaml) | 1957-10-01 | A federalized guardsman ordered to protect desegregation | observer, advisor_state, executor | enforcement | compliance_better_supported (P-ENFORCER) | 48 | 1 |
| [MK-1961](mk_1961.yaml) | 1961-12-16 | Beginning a sabotage campaign against apartheid institutions | observer, advisor_actor | resistance | – | 32 | 2 |
| [PLESSY-1892](plessy_1892.yaml) | 1892-06-07 | A conductor's enforcement of railway segregation | observer, advisor_state, executor, advisor_subject | enforcement | – | 64 | – |
| [THOREAU-1846](thoreau_1846.yaml) | 1846-07-23 | Refusing a poll tax over slavery and war | observer, advisor_actor | resistance | – | 32 | 1 |
| [TURING-1952](turing_1952.yaml) | 1952-03-31 | Sentencing for private sexual acts between men | observer, advisor_state, executor, advisor_subject | enforcement | resistance_better_supported | 64 | – |
| [WHISKEY-1792](whiskey_1792.yaml) | 1792-08-21 | Endorsing organized ostracism of federal excise officers | observer, advisor_actor | resistance | contested | 32 | 1 |

```bash
uv run canon validate cases/
uv run canon render cases/turing_1952.yaml --cell executor.named.stripped.neutral_source --seed 1
uv run canon review cases/turing_1952.yaml
uv run canon validate cases/ --require-verified   # fails: eight facts are unsigned
```
