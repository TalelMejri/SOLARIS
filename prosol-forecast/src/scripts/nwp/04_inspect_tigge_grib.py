from pathlib import Path
import cfgrib


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRIB_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge_test"
    / "ecmwf_tigge_tunisia_2023-06-01_00.grib"
)


# ---------------------------------------------------------
# Open GRIB datasets
# ---------------------------------------------------------

print("=" * 70)
print("TIGGE GRIB INSPECTION")
print("=" * 70)

print(f"\nFile:")
print(GRIB_FILE)

if not GRIB_FILE.exists():
    raise FileNotFoundError(f"GRIB file not found: {GRIB_FILE}")

datasets = cfgrib.open_datasets(
    str(GRIB_FILE),
    backend_kwargs={
        "indexpath": "",
    },
)

print(f"\nNumber of GRIB datasets: {len(datasets)}")


# ---------------------------------------------------------
# Inspect every dataset
# ---------------------------------------------------------

for i, ds in enumerate(datasets):

    print("\n" + "=" * 70)
    print(f"DATASET {i}")
    print("=" * 70)

    print("\nDimensions:")
    print(ds.dims)

    print("\nCoordinates:")
    for name, coord in ds.coords.items():
        print(
            f"  {name}: "
            f"shape={coord.shape}, "
            f"dtype={coord.dtype}"
        )

        if coord.size <= 20:
            print(f"      values={coord.values}")

    print("\nVariables:")
    for name, variable in ds.data_vars.items():
        print(
            f"  {name}: "
            f"shape={variable.shape}, "
            f"dtype={variable.dtype}"
        )

    print("\nAttributes:")
    for key, value in ds.attrs.items():
        print(f"  {key}: {value}")


# ---------------------------------------------------------
# Close datasets
# ---------------------------------------------------------

for ds in datasets:
    ds.close()

print("\n" + "=" * 70)
print("INSPECTION COMPLETE")
print("=" * 70)