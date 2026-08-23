import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import qmc

# 1. Define the number of samples (rows) you want in your dataset
n_samples = 1000

# 2. Initialize the Latin Hypercube Sampler for 8 independent variables
# (Feed Temp, Feed Press, Feed Comp, Stages, Feed Stage, Reflux, Bottoms Rate, Column Press)
sampler = qmc.LatinHypercube(d=8)
lhs_sample = sampler.random(n=n_samples)

# 3. Define the minimum and maximum physical bounds for each variable
# Format: [Min, Max]
bounds = {
    "Feed_Temp_K": [320.0, 360.0],          # Kelvin
    "Feed_Pressure_Pa": [101325, 150000],   # Pascals; adjusted below to be >= column pressure
    "Feed_Benzene_Frac": [0.3, 0.7],        # Mole fraction
    "Num_Stages": [15, 25],                 # Integer
    "Feed_Stage": [7, 14],                  # Integer
    "Reflux_Ratio": [1.2, 3.5],             # Ratio
    "Bottoms_Rate_mols": [40.0, 60.0],      # mol/s (assuming 100 mol/s total feed)
    "Column_Pressure_Pa": [101325, 120000]  # Pascals
}

# 4. Scale the 0-to-1 LHS samples to your actual physical bounds
dataset_inputs = {}
col_idx = 0

for var_name, (b_min, b_max) in bounds.items():
    # Scale continuous variables
    scaled_values = b_min + lhs_sample[:, col_idx] * (b_max - b_min)
    
    # If the variable needs to be a whole number (Stages), round it
    if "Stage" in var_name:
        scaled_values = np.round(scaled_values).astype(int)
        
    dataset_inputs[var_name] = scaled_values
    col_idx += 1

# A feed should not enter a column at a lower pressure than the column.
# Keep the requested bounds while enforcing Feed_Pressure >= Column_Pressure.
dataset_inputs["Feed_Pressure_Pa"] = np.maximum(
    dataset_inputs["Feed_Pressure_Pa"],
    dataset_inputs["Column_Pressure_Pa"]
)

# 5. Convert to a Pandas DataFrame and save to CSV
df_inputs = pd.DataFrame(dataset_inputs)
# Keep the same number of stages together so DWSIM rebuilds the column less often.
# Sorting rows does not change any sampled values or their recipe pairings.
df_inputs = df_inputs.sort_values("Num_Stages", kind="stable").reset_index(drop=True)
output_path = Path(__file__).resolve().parent / "LHS_Input_Recipes.csv"
df_inputs.to_csv(output_path, index=False)

print(f"Successfully generated {n_samples} unique combinations!")
print(df_inputs.head())