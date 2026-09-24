from pathlib import Path

import cfgrib


PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRIB_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge_test"
    / "ecmwf_tigge_tunisia_2023-06-01_00.grib"
)


datasets = cfgrib.open_datasets(
    str(GRIB_FILE),
    backend_kwargs={"indexpath": ""},
)


for i, ds in enumerate(datasets):

    print("\n" + "=" * 70)
    print(f"DATASET {i}")
    print("=" * 70)

    print("Variables:", list(ds.data_vars))

    metadata_keys = [
        "GRIB_gridType",
        "GRIB_Nx",
        "GRIB_Ny",
        "GRIB_iDirectionIncrementInDegrees",
        "GRIB_jDirectionIncrementInDegrees",
        "GRIB_latitudeOfFirstGridPointInDegrees",
        "GRIB_longitudeOfFirstGridPointInDegrees",
        "GRIB_latitudeOfLastGridPointInDegrees",
        "GRIB_longitudeOfLastGridPointInDegrees",
        "GRIB_dataDate",
        "GRIB_dataTime",
        "GRIB_typeOfLevel",
        "GRIB_stepType",
    ]

    for key in metadata_keys:
        print(f"{key}: {ds.attrs.get(key)}")

    print("\nLatitude:")
    print(
        ds.latitude.min().item(),
        "→",
        ds.latitude.max().item(),
    )

    print("\nLongitude:")
    print(
        ds.longitude.min().item(),
        "→",
        ds.longitude.max().item(),
    )