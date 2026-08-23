# DWSIM Distillation Surrogate Model

A DWSIM data-generation and machine-learning workflow for distillation-column surrogate modeling.

## Project Structure

```text
DWSIM/
├── notebook/
│   ├── EDA.ipynb
│   ├── ModelTraining.ipynb
│   └── data/
│       └── Dataset.csv              # canonical dataset
├── data_collection/                 # DWSIM data-generation workflow
│   ├── automation.py
│   ├── LHS.py
│   └── LHS_Input_Recipes.csv
├── src/
│   ├── components/
│   └── pipeline/
├── Data Visualisation/              # generated EDA figures
├── Evaluation/                      # model diagnostic figures
├── optional/                        # retained datasets and unused scripts
│   └── run_batch.py
├── DWSIM_Flowsheet_File.dwxmz
├── requirements.txt
└── requirement.txt                  # legacy dependency file
```

Open `notebook/EDA.ipynb` for exploration and `notebook/ModelTraining.ipynb` for model development. The canonical model dataset is `notebook/data/Dataset.csv`; retained alternative datasets are kept in `optional/`. Use `data_collection/LHS.py` and `data_collection/automation.py` to generate new DWSIM data.

## Setup

```powershell
pip install -r requirements.txt
```

DWSIM is required only when generating new simulation data.
