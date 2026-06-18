# Iowa LCFS CI vs Operating Permit Equipment

Source JSON: `C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json`

Scores are active/latest facility scores collapsed by program and pathway class. Lower CI is better. This is exploratory: small samples and correlated technology choices mean the results should be treated as relationship flags, not causal proof.

Facility-score rows: 80

## Strongest Average Differences

| Program | Class | Flag | N true | N false | Avg CI true | Avg CI false | True - false | Direction |
|---|---|---|---:|---:|---:|---:|---:|---|
| WA | fiber/cellulosic | chp | 2 | 2 | 27.08 | 23.98 | +3.09 | higher CI associated with flag |
| OR | fiber/cellulosic | chp | 2 | 2 | 26.08 | 29.87 | -3.79 | lower CI associated with flag |
| OR | corn starch | chp | 2 | 3 | 54.27 | 55.05 | -0.78 | lower CI associated with flag |
| OR | corn starch | edeniq | 2 | 3 | 54.59 | 54.84 | -0.26 | lower CI associated with flag |
| CFA | corn starch | high_protein | 2 | 8 | 42.00 | 39.25 | +2.75 | higher CI associated with flag |
| CFA | corn starch | fluid_quip | 2 | 8 | 42.00 | 39.25 | +2.75 | higher CI associated with flag |
| CFA | corn starch | fiber_to_ethanol | 7 | 3 | 40.29 | 38.67 | +1.62 | higher CI associated with flag |
| CFA | corn starch | waste_heat_recovery | 8 | 2 | 39.88 | 39.50 | +0.38 | higher CI associated with flag |
| CA | fiber/cellulosic | corn_oil_extraction | 23 | 2 | 26.25 | 23.21 | +3.04 | higher CI associated with flag |
| CA | fiber/cellulosic | white_fox_membrane | 3 | 22 | 24.47 | 26.22 | -1.75 | lower CI associated with flag |
| CA | fiber/cellulosic | high_protein | 2 | 23 | 27.16 | 25.91 | +1.24 | higher CI associated with flag |
| CA | fiber/cellulosic | fluid_quip | 2 | 23 | 27.16 | 25.91 | +1.24 | higher CI associated with flag |
| CA | fiber/cellulosic | edeniq | 9 | 16 | 25.39 | 26.36 | -0.97 | lower CI associated with flag |
| CA | fiber/cellulosic | chp | 5 | 20 | 26.48 | 25.89 | +0.59 | higher CI associated with flag |
| CA | fiber/cellulosic | molecular_sieve_only | 3 | 22 | 25.64 | 26.06 | -0.42 | lower CI associated with flag |
| CA | fiber/cellulosic | waste_heat_recovery | 13 | 12 | 25.81 | 26.22 | -0.41 | lower CI associated with flag |
| CA | corn starch | corn_oil_extraction | 25 | 2 | 67.76 | 63.95 | +3.81 | higher CI associated with flag |
| CA | corn starch | chp | 5 | 22 | 66.08 | 67.79 | -1.71 | lower CI associated with flag |
| CA | corn starch | waste_heat_recovery | 13 | 14 | 67.97 | 67.02 | +0.95 | higher CI associated with flag |
| CA | corn starch | fiber_to_ethanol | 25 | 2 | 67.42 | 68.15 | -0.73 | lower CI associated with flag |
| CA | corn starch | high_protein | 2 | 25 | 67.02 | 67.51 | -0.50 | lower CI associated with flag |
| CA | corn starch | fluid_quip | 2 | 25 | 67.02 | 67.51 | -0.50 | lower CI associated with flag |
| CA | corn starch | edeniq | 9 | 18 | 67.38 | 67.52 | -0.14 | lower CI associated with flag |
| CA | corn starch | white_fox_membrane | 3 | 24 | 67.40 | 67.48 | -0.08 | lower CI associated with flag |
| CA | corn starch | molecular_sieve_only | 3 | 24 | 67.46 | 67.48 | -0.02 | lower CI associated with flag |

## Notes

- `true - false` below zero means the flagged equipment group has lower average CI.
- CA/OR fiber pathways are naturally lower than starch pathways, so compare within `pathway_class`, not across classes.
- `white_fox_membrane` is treated as an energy-efficiency dehydration technology that can reduce molecular-sieve/steam load.
- Dryer and technology flags often come from the technology layer merged into `operating_permit`, not solely from permit text.
- Numeric MMBtu/hr and BTU/gal fields are permit/nameplate screening metrics, not verified annual fuel use.
- Many Iowa permits are still missing clean numeric thermal, DDGS, and storage inputs.

## Numeric Energy Metric Correlations

| Program | Class | Metric | N | Correlation to CI |
|---|---|---|---:|---:|
| CA | fiber/cellulosic | boiler_mmbtu_hr | 4 | -0.87 |
| CA | fiber/cellulosic | total_thermal_mmbtu_hr_per_mgy | 5 | -0.85 |
| CA | fiber/cellulosic | estimated_btu_per_gal_from_heat_input | 5 | -0.85 |
| CA | fiber/cellulosic | total_thermal_mmbtu_hr | 5 | -0.76 |
| CA | corn starch | waste_heat_boiler_mmbtu_hr | 4 | +0.66 |
| CFA | corn starch | waste_heat_boiler_mmbtu_hr | 3 | +0.61 |
| CA | corn starch | boiler_mmbtu_hr | 4 | +0.60 |
| CA | fiber/cellulosic | waste_heat_boiler_mmbtu_hr | 4 | -0.40 |
| CA | corn starch | estimated_btu_per_gal_from_heat_input | 5 | +0.36 |
| CA | corn starch | total_thermal_mmbtu_hr_per_mgy | 5 | +0.36 |
| CA | corn starch | total_thermal_mmbtu_hr | 5 | +0.20 |
