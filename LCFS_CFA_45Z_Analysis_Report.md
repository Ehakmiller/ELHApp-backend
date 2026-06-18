# LCFS / Canadian Federal CI / Estimated 45Z Comparison

Rows in full JSON: 202
Rows with numeric Canadian Federal CI used in statistics: 19

## Core Results

- Average LCFS-CFA gap: 29.47 g/MJ.
- Average 45Z-CFA gap: 8.53 g/MJ.
- Median 45Z-CFA gap: 8.40 g/MJ.
- Standard deviation of 45Z-CFA gap: 2.31 g/MJ.
- Share of numeric plants where CFA is lower than estimated 45Z: 100.0%.
- Correlation, LCFS CI vs CFA: 0.68.
- Correlation, estimated 45Z CI vs CFA: 0.67.

## Variables Explaining 45Z-CFA Gap

- In-sample linear model R2: 0.94. Random forest R2: 0.75. These are descriptive only because the numeric CFA sample is small.
- Top feature-importance signals:
  - Ethanol Capacity MGY: 0.325
  - LCFS CI: 0.280
  - Thermal BTU/gal: 0.130
  - CCS Status_None: 0.047
  - CCS Status_Summit/SCS: 0.046
  - Freight CI Adjustment: 0.046
  - Distance to Hub: 0.045
  - Default Hub Railroad_BNSF: 0.013

## Conclusions

1. Is CFA systematically lower than estimated 45Z? Yes. The average 45Z-CFA gap is 8.53 g/MJ and CFA is lower in 100.0% of numeric matched plants.
2. Average methodology gap: using the LCFS-derived 45Z method, the average gap is 8.53 g/MJ. The LCFS-CFA gap before 45Z adjustments averages 29.47 g/MJ.
3. Best explanatory variables: the strongest descriptive signals are listed above. Because the estimated 45Z score is mechanically built from LCFS CI, freight, ILUC, and grid adjustment, LCFS CI and freight/grid geography tend to dominate the measured gap.
4. Plant-performance vs methodology: the evidence is more consistent with a methodology difference than a broad plant-performance issue. The 45Z estimate mechanically subtracts a fixed ILUC value and freight normalization from LCFS, while CFA is an independent federal score. Variation around the average gap appears tied to geography, grid/freight treatment, and source CI methodology rather than one consistent owner or state performance problem.

## Files

- Workbook: `C:\Users\ehakm\Documents\ELHApp-backend\LCFS_CFA_45Z_Comparison.xlsx`
- Source JSON: `C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json`
