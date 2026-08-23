# =====================================================================
# DWSIM IronPython Batch Automation Script
# Target: Script Manager (internal IronPython), Avalonia cross-platform build
# Purpose: Sweep LHS_Input_Recipes.csv rows through
#          Feed -> DCOL-1 -> DISTILLATE/BOTTOMS
#          and log results to Dataset.csv, without triggering
#          async task-cancellation errors.
#
# The script uses the open flowsheet's synchronous Solve() method so each
# recipe finishes before the next one starts.
# =====================================================================

import System
from System import Array
from System.IO import File, StreamWriter
INPUT_CSV  = r"D:\FOSSE\DWSIM\data_collection\LHS_Input_Recipes.csv"       # columns: Temperature,Pressure,z_Comp1,z_Comp2,...
OUTPUT_CSV = r"D:\FOSSE\DWSIM\notebook\data\Dataset.csv"
# ---------------------------------------------------------------------
# CONFIG - adjust paths/names to match your flowsheet
# ---------------------------------------------------------------------
FEED_NAME       = "Feed"
COLUMN_NAME     = "DCOL-1"
DISTILLATE_NAME = "DISTILLATE"
BOTTOMS_NAME    = "BOTTOMS"

# How many compounds your compositions have, in the same order as the
# columns you'll write to the CSV (must match flowsheet compound order).
N_COMPOUNDS = 2
LOG_EVERY = 5        # progress message frequency
FLUSH_EVERY = 1      # persist every row so a hard crash loses at most one row
MAINTENANCE_EVERY = 5  # periodic cleanup cadence to keep long runs stable
MAX_RECIPES = 1000   # requested dataset size
TOTAL_FEED_MOLAR_FLOW = 100.0  # mol/s; basis used for Bottoms_Rate_mols
RESUME_IF_OUTPUT_EXISTS = True  # append to existing output and skip completed rows
MAX_ERROR_TEXT_LEN = 500
MEMORY_GUARD_MB = 3500  # set >0 to stop gracefully before hard crash
SKIP_RUN_INDICES = [547]  # recipes that previously caused Solve() not to return

# ---------------------------------------------------------------------
# Resolve simulation objects once (not inside the loop)
# ---------------------------------------------------------------------
feed       = Flowsheet.GetFlowsheetSimulationObject(FEED_NAME)
column     = Flowsheet.GetFlowsheetSimulationObject(COLUMN_NAME)
distillate = Flowsheet.GetFlowsheetSimulationObject(DISTILLATE_NAME)
bottoms    = Flowsheet.GetFlowsheetSimulationObject(BOTTOMS_NAME)

if feed is None or column is None or distillate is None or bottoms is None:
    raise Exception("One or more flowsheet objects not found. Check names: "
                     + FEED_NAME + ", " + COLUMN_NAME + ", "
                     + DISTILLATE_NAME + ", " + BOTTOMS_NAME)


def to_net_array(values):
    """Convert a Python list of floats to a .NET double[] array."""
    return Array[System.Double]([float(v) for v in values])


def safe_get_stream_row(stream, prefix):
    """
    Pull a standard set of properties off a MaterialStream using the
    correct native getters (GetTemperature, GetMassEnthalpy, etc.),
    NOT GetPropertyValue()/GetEnthalpy() which don't exist on this build.
    Returns a dict of prefixed column -> value.
    """
    row = {}
    row[prefix + "_temperature_K"]                 = stream.GetTemperature()
    row[prefix + "_pressure_Pa"]                   = stream.GetPressure()
    row[prefix + "_mass_enthalpy"]                 = stream.GetMassEnthalpy()
    row[prefix + "_molar_flow_mol_s"]              = stream.GetMolarFlow()
    row[prefix + "_mass_flow_kg_s"]                = stream.GetMassFlow()
    row[prefix + "_volumetric_flow_m3_s"]          = stream.GetVolumetricFlow()

    comp = stream.GetOverallComposition()  # .NET array of mole fractions
    for i in range(N_COMPOUNDS):
        row[prefix + "_component_" + str(i + 1) + "_mole_fraction"] = (
            comp[i] if i < len(comp) else None
        )

    return row


def blank_row(prefix):
    """Zero/None-filled row for a stream when a run fails, so column
    structure stays consistent in the output CSV."""
    row = {}
    for key in ["_temperature_K", "_pressure_Pa", "_mass_enthalpy",
                "_molar_flow_mol_s", "_mass_flow_kg_s", "_volumetric_flow_m3_s"]:
        row[prefix + key] = None
    for i in range(N_COMPOUNDS):
        row[prefix + "_component_" + str(i + 1) + "_mole_fraction"] = None
    return row


def get_column_targets():
    """Return the report targets for a benzene/toluene binary column."""
    dist_comp = distillate.GetOverallComposition()
    bot_comp = bottoms.GetOverallComposition()
    return {
        "distillate_benzene_purity_mole_fraction": dist_comp[0],
        "bottoms_toluene_purity_mole_fraction": bot_comp[1],
        "condenser_duty_kW": column.CondenserDuty / 1000.0,
        "reboiler_duty_kW": column.ReboilerDuty / 1000.0
    }


def csv_value(value):
    if value is None:
        return ""
    text = str(value)
    if "," in text or '"' in text:
        return '"' + text.replace('"', '""') + '"'
    return text


def write_csv_row(writer, fieldnames, row):
    writer.WriteLine(",".join(csv_value(row.get(name, "")) for name in fieldnames))


def truncate_text(text, max_len):
    if text is None:
        return ""
    value = str(text)
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def count_existing_data_rows(csv_path):
    """Return the next run index after the last valid output record."""
    if not File.Exists(csv_path):
        return 0

    lines = File.ReadAllLines(csv_path)
    if len(lines) <= 1:
        return 0

    last_run_index = -1
    for line in lines[1:]:
        if line is None or line.strip() == "":
            continue
        fields = line.Split(",")
        try:
            run_index = int(fields[0])
            if run_index > last_run_index:
                last_run_index = run_index
        except Exception:
            continue
    return last_run_index + 1


def get_working_set_mb():
    return System.Environment.WorkingSet / (1024.0 * 1024.0)


def perform_periodic_maintenance(run_number):
    """Run lightweight cleanup to reduce memory pressure in long loops."""
    try:
        # Ask .NET to release objects no longer referenced by IronPython/.NET bridge.
        System.GC.Collect()
        System.GC.WaitForPendingFinalizers()
        System.GC.Collect()
        Flowsheet.WriteMessage(
            "Maintenance complete after run " + str(run_number)
            + ", working set ~" + str(round(get_working_set_mb(), 1)) + " MB"
        )
    except Exception as maint_ex:
        Flowsheet.WriteMessage(
            "Maintenance warning after run " + str(run_number) + ": " + str(maint_ex)
        )


# ---------------------------------------------------------------------
# Read input recipes
# ---------------------------------------------------------------------
input_lines = File.ReadAllLines(INPUT_CSV)
input_headers = [str(value) for value in input_lines[0].Split(",")]
available_rows = min(MAX_RECIPES, max(0, len(input_lines) - 1))
start_index = 0
output_exists = File.Exists(OUTPUT_CSV)

if RESUME_IF_OUTPUT_EXISTS:
    start_index = count_existing_data_rows(OUTPUT_CSV)
    if start_index > available_rows:
        start_index = available_rows

Flowsheet.WriteMessage(
    "Input rows available=" + str(available_rows)
    + ", resume start row=" + str(start_index)
)

if RESUME_IF_OUTPUT_EXISTS and start_index < available_rows:
    # A previous run may have stopped immediately after a solve, before its
    # normal maintenance interval. Clean up before applying the guard again.
    perform_periodic_maintenance(start_index)

# ---------------------------------------------------------------------
# Prepare output CSV - build header from a dry-run of the row structure
# ---------------------------------------------------------------------
sample_fieldnames = (
    ["run_index", "status", "error_message"]
    + input_headers
    + ["feed_vapor_fraction",
       "distillate_benzene_purity_mole_fraction",
       "bottoms_toluene_purity_mole_fraction",
    "condenser_duty_kW", "reboiler_duty_kW"]
    + list(safe_get_stream_row(distillate, "distillate").keys())
    + list(safe_get_stream_row(bottoms, "bottoms").keys())
)

if RESUME_IF_OUTPUT_EXISTS and output_exists and start_index > 0:
    out_file = StreamWriter(OUTPUT_CSV, True)
else:
    out_file = StreamWriter(OUTPUT_CSV, False)
    write_csv_row(out_file, sample_fieldnames,
                  dict((name, name) for name in sample_fieldnames))

# ---------------------------------------------------------------------
# Main batch loop
# ---------------------------------------------------------------------
n_success = 0
n_failed = 0

try:
    for idx in range(start_index, available_rows):

        ws_mb = round(get_working_set_mb(), 1)
        if MEMORY_GUARD_MB > 0.0 and ws_mb >= MEMORY_GUARD_MB:
            Flowsheet.WriteMessage(
                "Stopping before run " + str(idx)
                + " due to MEMORY_GUARD_MB=" + str(MEMORY_GUARD_MB)
                + ", current working set=" + str(ws_mb) + " MB"
            )
            break

        line = input_lines[idx + 1]
        if line.strip() == "":
            continue
        values = line.Split(",")
        recipe = dict((input_headers[i], str(values[i]))
                      for i in range(min(len(input_headers), len(values))))

        row_out = {"run_index": idx}
        row_out.update(recipe)
        stop_after_row = False

        if idx in SKIP_RUN_INDICES:
            row_out["status"] = "SKIPPED"
            row_out["error_message"] = "Skipped because the flowsheet solver did not return for this recipe"
            row_out["feed_vapor_fraction"] = None
            row_out["distillate_benzene_purity_mole_fraction"] = None
            row_out["bottoms_toluene_purity_mole_fraction"] = None
            row_out["condenser_duty_kW"] = None
            row_out["reboiler_duty_kW"] = None
            row_out.update(blank_row("distillate"))
            row_out.update(blank_row("bottoms"))
            write_csv_row(out_file, sample_fieldnames, row_out)
            out_file.Flush()
            Flowsheet.WriteMessage("Run " + str(idx) + " SKIPPED")
            continue

        try:
            # --- 1. Parse recipe values -------------------------------------------------
            feed_T = float(recipe["Feed_Temp_K"])
            feed_P = float(recipe["Feed_Pressure_Pa"])
            benzene_fraction = float(recipe["Feed_Benzene_Frac"])
            num_stages = int(recipe["Num_Stages"])
            feed_stage = int(recipe["Feed_Stage"])
            reflux_ratio = float(recipe["Reflux_Ratio"])
            bottoms_rate = float(recipe["Bottoms_Rate_mols"])
            column_pressure = float(recipe["Column_Pressure_Pa"])
            comp_values = [benzene_fraction, 1.0 - benzene_fraction]

            # --- 2. Push values into the Feed stream ------------------------------------
            feed.SetTemperature(feed_T)
            feed.SetPressure(feed_P)
            feed.SetMolarFlow(TOTAL_FEED_MOLAR_FLOW)
            feed.SetOverallComposition(to_net_array(comp_values))

            # --- 3. Push the recipe-specific column settings ---------------------------
            column.SetNumberOfStages(num_stages)
            column.SetStreamFeedStage(feed, feed_stage)
            column.SetCondenserSpec("Reflux Ratio", reflux_ratio, "", "")
            column.SetReboilerSpec("Product Molar Flow Rate", bottoms_rate, "mol/s", "")
            for stage in column.Stages:
                stage.P = column_pressure

            # --- 4. Solve the whole flowsheet synchronously ----------------------------
            Flowsheet.WriteMessage("Starting run " + str(idx) + "...")
            out_file.Flush()
            Flowsheet.Solve()

            ws_after_solve_mb = round(get_working_set_mb(), 1)
            if (MEMORY_GUARD_MB > 0.0
                    and ws_after_solve_mb >= MEMORY_GUARD_MB):
                Flowsheet.WriteMessage(
                    "Memory guard reached after run " + str(idx)
                    + "; row will be saved, then the batch will stop."
                )
                stop_after_row = True

            # --- 5. Extract results -------------------------------------------------------
            row_out["feed_vapor_fraction"] = feed.GetPhaseMolarFraction("Vapor")
            row_out.update(get_column_targets())
            row_out.update(safe_get_stream_row(distillate, "distillate"))
            row_out.update(safe_get_stream_row(bottoms, "bottoms"))

            row_out["status"] = "OK"
            row_out["error_message"] = ""
            n_success += 1

        except Exception as ex:
            # Never let one bad recipe kill the whole batch.
            row_out["status"] = "FAILED"
            row_out["error_message"] = truncate_text(ex, MAX_ERROR_TEXT_LEN)
            row_out["feed_vapor_fraction"] = None
            row_out["distillate_benzene_purity_mole_fraction"] = None
            row_out["bottoms_toluene_purity_mole_fraction"] = None
            row_out["condenser_duty_kW"] = None
            row_out["reboiler_duty_kW"] = None
            row_out.update(blank_row("distillate"))
            row_out.update(blank_row("bottoms"))
            n_failed += 1

            Flowsheet.WriteMessage("Run " + str(idx) + " FAILED: " + str(ex))

        write_csv_row(out_file, sample_fieldnames, row_out)
        if stop_after_row:
            out_file.Flush()
            break

        if (idx + 1) % FLUSH_EVERY == 0:
            out_file.Flush()

        if (idx + 1) % LOG_EVERY == 0:
            ws_mb = round(get_working_set_mb(), 1)
            Flowsheet.WriteMessage(
                "Progress: " + str(idx + 1) + "/" + str(available_rows)
                + " (ok=" + str(n_success) + ", failed=" + str(n_failed)
                + ", ws_mb=" + str(ws_mb) + ")"
            )

            if MEMORY_GUARD_MB > 0.0 and ws_mb >= MEMORY_GUARD_MB:
                Flowsheet.WriteMessage(
                    "Stopping early due to MEMORY_GUARD_MB=" + str(MEMORY_GUARD_MB)
                    + ", current working set=" + str(ws_mb) + " MB"
                )
                break

        if (idx + 1) % MAINTENANCE_EVERY == 0:
            out_file.Flush()
            perform_periodic_maintenance(idx + 1)

finally:
    out_file.Flush()
    out_file.Dispose()

Flowsheet.WriteMessage(
    "Batch complete. " + str(n_success) + " succeeded, "
    + str(n_failed) + " failed. Output written to " + OUTPUT_CSV
)