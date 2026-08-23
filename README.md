![Binary Distillation](DistillationColumns.png)
# Binary Distillation Surrogate Modelling: BENZENE-TOLUENE SYSTEM

Machine-learning surrogate models for a benzene-toluene binary distillation column simulated in [DWSIM](https://dwsim.org/).

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![DWSIM](https://img.shields.io/badge/DWSIM-process%20simulator-2E7D32?style=for-the-badge)](https://dwsim.org/)
[![scikit--learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-regression-EC4E20?style=for-the-badge&logo=xgboost&logoColor=white)](https://xgboost.readthedocs.io/)

## Overview

Rigorous distillation simulations solve coupled material, equilibrium, summation, and enthalpy equations. These calculations can be expensive when a process engineer needs to evaluate many operating conditions during design optimization, sensitivity analysis, or process-control studies.

This project uses DWSIM to generate a simulation dataset and trains regression models that approximate the column response. Once trained, a surrogate can estimate product quality and energy requirements much faster than repeatedly solving the full flowsheet.

The project was completed as a screening task for the **FOSSEE Semester Long Internship at IIT Bombay**.

## Project Goals

- Generate a representative dataset from a rigorous DWSIM flowsheet.
- Study the effect of column and feed conditions on separation performance.
- Compare linear, polynomial, ensemble, kernel, and boosting regressors.
- Predict product purities and column energy duties from operating inputs.
- Test both interpolation within the training domain and generalization to an unseen operating region.
- Check predictions against basic chemical-engineering expectations, not only statistical scores.

## Process Description

The simulated system is a binary mixture of **benzene and toluene**:

- **Benzene** is the light key and is enriched in the distillate.
- **Toluene** is the heavy key and is enriched in the bottoms product.
- The flowsheet contains a feed stream, a distillation column, a distillate stream, and a bottoms stream.
- Column settings such as the number of stages, feed stage, reflux ratio, and pressure are varied between runs.
- The flowsheet is solved synchronously in DWSIM so that each recipe is completed before the next recipe is applied.

The DWSIM flowsheet is stored in `DWSIM_Flowsheet_File.dwxmz`. The exact thermodynamic package and flowsheet configuration should be verified in the DWSIM file before reproducing the simulations.

## Dataset Generation

### Latin Hypercube Sampling

`data_collection/LHS.py` creates 1,000 input recipes using Latin Hypercube Sampling. LHS divides each variable's range into representative intervals and samples across the combined space, giving better coverage than an equivalent number of purely random samples.

The generated recipes are written to `data_collection/LHS_Input_Recipes.csv`.

### Input Variables

| Variable | Description | Sampling range or type |
| --- | --- | --- |
| `Feed_Temp_K` | Feed temperature | 320-360 K |
| `Feed_Pressure_Pa` | Feed pressure | 101,325-150,000 Pa |
| `Feed_Benzene_Frac` | Benzene mole fraction in the feed | 0.30-0.70 |
| `Num_Stages` | Number of theoretical stages | 15-25, integer |
| `Feed_Stage` | Feed tray location | 7-14, integer |
| `Reflux_Ratio` | Reflux-to-distillate ratio | 1.2-3.5 |
| `Bottoms_Rate_mols` | Bottoms molar flow rate | 40-60 mol/s |
| `Column_Pressure_Pa` | Column operating pressure | 101,325-120,000 Pa |

The recipe generator also enforces `Feed_Pressure_Pa >= Column_Pressure_Pa`, which prevents a feed from entering the column at a lower pressure than the column operating pressure.

### DWSIM Automation

`data_collection/automation.py` reads the recipe file and applies each row to the open DWSIM flowsheet. For every recipe, the script:

1. Sets feed temperature, pressure, flow rate, and composition.
2. Updates the column stage count and feed-stage location.
3. Sets the reflux ratio and bottoms product flow specification.
4. Applies the column pressure to the stages.
5. Solves the flowsheet synchronously.
6. Records product-stream properties, purity targets, and energy duties.

The script supports resumable execution. It flushes output frequently, skips completed rows when an output file already exists, periodically performs .NET garbage collection, and stops before a configured memory limit is exceeded.

Before running the automation script, review the paths and object names in its configuration section. The default names are `Feed`, `DCOL-1`, `DISTILLATE`, and `BOTTOMS`.

## Prediction Targets

The principal surrogate-model targets are:

| Target | Meaning | Unit |
| --- | --- | --- |
| `distillate_benzene_purity_mole_fraction` | Benzene mole fraction in the distillate | Mole fraction |
| `bottoms_toluene_purity_mole_fraction` | Toluene mole fraction in the bottoms | Mole fraction |
| `condenser_duty_kW` | Heat removed by the condenser | kW |
| `reboiler_duty_kW` | Heat supplied to the reboiler | kW |

The generated output also contains feed vapor fraction and detailed temperature, pressure, flow, enthalpy, and composition values for the distillate and bottoms streams. Failed or skipped runs are retained with a status and error message so that the output remains auditable.

## Data Preparation

The analysis workflow includes the following preparation steps:

- Remove or identify invalid simulation rows.
- Enforce physical bounds for composition variables.
- Preserve the DWSIM duty sign convention consistently during analysis.
- Separate simulator metadata such as run status and error text from modelling features.
- Scale numerical features where required, especially for distance- and margin-based models such as SVR.
- Split inputs and targets explicitly so the same target definition is used across model comparisons.

The repository includes both `data/Dataset.csv` and `data/dataset_cleaned.csv`. The cleaned file is intended for analysis after invalid or incomplete records have been handled. Inspect the notebook cells before training if a newly generated dataset is substituted.

## Models

The notebooks compare several regression approaches:

- **Linear Regression**: interpretable baseline.
- **Polynomial Regression**: captures smooth nonlinear relationships through polynomial features.
- **Random Forest Regressor**: ensemble of decision trees for nonlinear interpolation.
- **AdaBoost**: sequentially improves weak learners by focusing on difficult observations.
- **Support Vector Regression (SVR)**: models nonlinear relationships after feature scaling.
- **XGBoost Regressor**: gradient-boosted trees with strong performance on structured tabular data.

The four-output problem is handled with separate regressors through scikit-learn's multi-output utilities where required. Hyperparameter search is performed with `RandomizedSearchCV` in the training workflow.

## Validation Strategy

The project evaluates more than random interpolation performance. A block of reflux-ratio values is held out to test whether a model can follow the underlying thermodynamic trend in an unseen region.

- **Training data**: excludes the selected reflux-ratio block.
- **Validation data**: used for model comparison and tuning.
- **Block test data**: evaluates the model on the unseen reflux-ratio interval, approximately 2.5-3.5 in the reported experiment.

This distinction matters because tree models can perform extremely well on points surrounded by training data while producing flat or limited predictions outside the regions represented by their leaves. Smooth models may generalize better across a continuous operating trend, although they can be less robust on complicated local behavior.

## Reported Results

The existing analysis reports the following approximate comparison. Exact values can change when the dataset, random seed, preprocessing, or search configuration changes.

| Model | Val R² | Val RMSE | Test (Block) R² | Test RMSE | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Polynomial Regression** | 0.9867 | 0.0207 | 0.9419 | 0.0418 | Best mathematical extrapolator; maintains continuous curves into unseen data. |
| **XGBoost** | 0.9838 | 0.0700 | 0.3336 | 0.7213 | Best overall interpolator; fails at extrapolation due to discrete tree boundaries. |
| **Random Forest** | 0.9648 | 0.1140 | 0.2444 | 0.7673 | Robust interpolator, but suffers the same extrapolation drop as XGBoost. |
| **AdaBoost** | 0.9362 | 0.1442 | 0.1659 | 0.7927 | Decent interpolation, but poorest extrapolation performance. |
| **SVR** | 0.8904 | 0.0772 | 0.8562 | 0.1735 | Stable and consistent performance across both seen and unseen regions. |


> **Best Model for Interpolation (Digital Twin): XGBoost Regressor**  
> - Highest R² scores (~0.984) for standard validation sets  
> - Lowest RMSE when operating within known, trained boundaries  
> - **99%+ reduction in computation time** compared to full DWSIM simulations  
>
> **Best Model for Extrapolation (Design Exploration): Polynomial Regression**  
> - Highest R² scores (~0.942) on the completely unseen Block Test set  
> - Successfully maintained continuous thermodynamic curves where tree-based models failed  
> - Safest choice for exploring edge-cases and new operating regimes

The analysis also includes monotonicity and high-purity checks. In particular, distillate purity should generally improve as reflux ratio increases within a physically meaningful operating range. These checks are important because a model can achieve a good average score while still producing implausible local predictions.

## Reproduction Workflow

### 1. Install Python dependencies

Create and activate a virtual environment, then install the packages listed in `requirements.txt`:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Generate input recipes

Run:

```powershell
python data_collection\\LHS.py
```

This regenerates `data_collection/LHS_Input_Recipes.csv`.

### 3. Generate or refresh DWSIM results

Open `DWSIM_Flowsheet_File.dwxmz` in DWSIM, confirm the object names and file paths in `data_collection/automation.py`, and run the automation script from DWSIM's supported scripting environment. DWSIM is required for this step only; it is not required to inspect the existing CSV files or execute the notebooks against an existing dataset.

### 4. Explore and train

Launch Jupyter from the repository root:

```powershell
jupyter notebook
```

Open the notebooks in this order:

1. `notebook/EDA.ipynb` for distributions, relationships, and data-quality checks.
2. `notebook/ModelTraining.ipynb` for preprocessing, model fitting, tuning, evaluation, and comparison.

## Repository Structure

```text
Binary-Distillation-Surrogate-Modelling/
|-- data/
|   |-- Dataset.csv                 # Raw/generated DWSIM output
|   `-- dataset_cleaned.csv         # Cleaned modelling dataset
|-- data_collection/
|   |-- LHS.py                      # Latin Hypercube recipe generation
|   |-- LHS_Input_Recipes.csv       # Sampled simulation inputs
|   `-- automation.py               # DWSIM batch automation script
|-- notebook/
|   |-- EDA.ipynb                   # Exploratory data analysis
|   `-- ModelTraining.ipynb         # Model training and evaluation
|-- DWSIM_Flowsheet_File.dwxmz      # DWSIM process flowsheet
|-- README.md
`-- requirements.txt
```

## Limitations and Responsible Use

- A surrogate is reliable only within the physical and statistical domain represented by its training data.
- Predictions should be checked against rigorous DWSIM simulations before engineering decisions are made.
- Changing the flowsheet, thermodynamic model, component set, units, or operating ranges requires new data generation and retraining.
- Reported metrics depend on the dataset split and random state; they are not universal guarantees of model performance.
- The automation script contains machine-specific paths that must be updated for another workstation.

## Acknowledgements

This project uses the open-source [DWSIM](https://dwsim.org/) process simulator and Python's scientific-computing and machine-learning ecosystem. It was developed in the context of the FOSSEE Semester Long Internship, IIT Bombay.

## Author

**Prabhat Lodhi**

Project repository: [Prabhatl0dhi/Binary-Distillation-Surrogate-Modelling](https://github.com/Prabhatl0dhi/Binary-Distillation-Surrogate-Modelling)
