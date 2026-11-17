# ADHD drug map (DQ-015)

Code: `classify` in [`pipeline/common.py`](../pipeline/common.py) and
`classify_drugs` in [`pipeline/03_munge.py`](../pipeline/03_munge.py).
Rule tables: [`tables/adhd_ingredient_map_v0.1.csv`](tables/adhd_ingredient_map_v0.1.csv)
(50 ingredients) and [`tables/adhd_name_alias_v0.1.csv`](tables/adhd_name_alias_v0.1.csv)
(90 brand and generic names). Accepted 2026-10-27 (DQD-035).

Every DRUG row is matched to the map, and the result is stored once per distinct
(`prod_ai`, `drugname`) pair in the `drug_classes` table.

## Matching

1. **Ingredient first.** When `prod_ai` is filled, it is upper-cased and split into
   ingredients on `\`. Each ingredient must match the map exactly (no fuzzy
   matching). If none matches, the row is not an ADHD medicine, whatever its name.
2. **Name second.** When `prod_ai` is blank (it did not exist before 2014Q3), the
   drug name is upper-cased, dictionary codes such as `/00016601/` are removed, and
   names from the alias list must match as whole words (so `TENEX` never matches
   inside `SUSTENEX`). When one match contains another, the longer one wins. The
   short `DEXTR` counts only beside an amphetamine word (`AMPHET/DEXTR`).
3. **Brand overrides.** A few brands decide the row even when `prod_ai` is filled:
   `DESOXYN`, `INTUNIV`, `KAPVAY`, `ONYDA` and `DURACLON` (epidural clonidine,
   excluded).
4. **Most restrictive wins.** Each match has a disposition: `INCLUDE`,
   `CONDITIONAL` (counts only with an ADHD indication, see
   [ADHD indication](adhd_indication.md)) or `EXCLUDE`. With several matches the
   most restrictive applies.

Classes: `STIMULANT` (amphetamines, methylphenidate and their salts and prodrugs),
`NONSTIMULANT` (atomoxetine, viloxazine) and `ALPHA2` (guanfacine, clonidine).

## Decisions (accepted 2026-10-27)

| ID | Question | Decision |
|---|---|---|
| D1 | Rare salt codings (dextroamphetamine hydrochloride or phosphate, "methylphenidate acid") | Include them with their ingredient. |
| D2 | Methamphetamine mostly reports illicit use | Exclude by ingredient; count only the Desoxyn brand. |
| D3 | Pemoline (withdrawn from the US market in 2005) | Exclude. |
| D4 | "Amphetamines NOS" (prescription or illicit cannot be told apart) | Exclude. |
| D5 | Wake-promoting drugs (modafinil, armodafinil, solriamfetol, pitolisant), not approved for ADHD | Exclude, listed so the exclusion is visible. |
| D6 | Guanfacine and clonidine are also blood-pressure drugs | `CONDITIONAL`: count only with an ADHD indication on the same drug. The ADHD-labelled brands Intuniv, Kapvay and Onyda count by name. |
| D7 | Products that combine an ADHD ingredient with a non-ADHD one | Exclude. |
| D9 | Where alpha-2 agonists go in RQ1 | Counted as nonstimulants, with their own `alpha2` flag so they can be split out. |

Off-label ADHD treatments (for example bupropion) are not in the map.
(Decision D8 concerned drug slots in the full pipeline and does not apply here.)
