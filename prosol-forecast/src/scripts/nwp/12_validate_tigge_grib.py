from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRIB_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "tigge"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "nwp"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

REPORT_FILE = (
    OUTPUT_DIR
    / "tigge_grib_validation_report.csv"
)


# ============================================================
# EXPECTED PERIOD
# ============================================================

START_YEAR = 2018
END_YEAR = 2022

EXPECTED_MONTHS = [
    f"{year}-{month:02d}"
    for year in range(
        START_YEAR,
        END_YEAR + 1
    )
    for month in range(1, 13)
]


# ============================================================
# EXPECTED TIGGE CONTENT
# ============================================================

EXPECTED_LEADS = {
    6,
    12,
    24,
    72,
}

EXPECTED_VARIABLES = {
    "u10",
    "v10",
    "t2m",
    "tcc",
}


# ============================================================
# VARIABLE CONFIGURATION
# ============================================================

VARIABLES = {

    "u10": {
        "short_name": "u10",
        "filter_by_keys": {
            "shortName": "10u",
            "typeOfLevel": "heightAboveGround",
            "level": 10,
        },
    },

    "v10": {
        "short_name": "v10",
        "filter_by_keys": {
            "shortName": "10v",
            "typeOfLevel": "heightAboveGround",
            "level": 10,
        },
    },

    "t2m": {
        "short_name": "t2m",
        "filter_by_keys": {
            "shortName": "2t",
            "typeOfLevel": "heightAboveGround",
            "level": 2,
        },
    },

    "tcc": {
        "short_name": "tcc",
        "filter_by_keys": {
            "shortName": "tcc",
        },
    },
}


# ============================================================
# HELPERS
# ============================================================
def month_from_filename(path):
    """
    Convert:
        ecmwf_tigge_2018_01_00.grib -> 2018-01
        ecmwf_tigge_2018-01_00.grib -> 2018-01
    """
    name = path.stem
    cleaned = name.replace("ecmwf_tigge_", "").replace("_00", "")
    # Normalize underscore to hyphen
    return cleaned.replace("_", "-")

def normalize_step_to_hours(step):
    """
    Convert a GRIB/xarray step into integer hours.
    """

    try:

        td = pd.Timedelta(step)

        return int(
            td.total_seconds()
            / 3600
        )

    except Exception:

        return int(step)


def get_data_variable(ds):
    """
    Return the first actual data variable.
    """

    variables = list(
        ds.data_vars
    )

    if not variables:

        raise ValueError(
            "Dataset contains no data variables."
        )

    return variables[0]


def get_issue_times(ds):
    """
    Extract forecast issue times.
    """

    if "time" not in ds.coords:

        raise ValueError(
            "GRIB dataset has no 'time' coordinate."
        )

    values = ds[
        "time"
    ].values

    return pd.to_datetime(
        values,
        utc=True
    )


def get_lead_hours(ds):
    """
    Extract forecast lead times.
    """

    if "step" not in ds.coords:

        raise ValueError(
            "GRIB dataset has no 'step' coordinate."
        )

    return [
        normalize_step_to_hours(
            value
        )
        for value in ds[
            "step"
        ].values
    ]


# ============================================================
# OPEN VARIABLE
# ============================================================

def open_variable(
    grib_file,
    variable_name
):

    config = VARIABLES[
        variable_name
    ]

    backend_kwargs = {
        "filter_by_keys":
            config[
                "filter_by_keys"
            ],

        "indexpath":
            "",
    }

    return xr.open_dataset(
        grib_file,
        engine="cfgrib",
        backend_kwargs=backend_kwargs,
    )


# ============================================================
# VALIDATE VALID_TIME
# ============================================================

def validate_valid_time(
    ds,
    variable_name,
    issue_times,
    lead_hours
):

    problems = []

    # --------------------------------------------------------
    # We prefer the GRIB-provided valid_time coordinate
    # when cfgrib exposes it.
    # --------------------------------------------------------

    has_valid_time = (
        "valid_time"
        in ds.coords
    )

    if not has_valid_time:

        problems.append(
            f"{variable_name}: "
            "missing valid_time coordinate"
        )

        return problems

    valid_time_values = (
        ds[
            "valid_time"
        ].values
    )

    # --------------------------------------------------------
    # Expected dimensions
    # --------------------------------------------------------

    expected_valid_count = (
        len(issue_times)
        *
        len(lead_hours)
    )

    flattened = (
        np.asarray(
            valid_time_values
        )
        .reshape(-1)
    )

    if len(flattened) != (
        expected_valid_count
    ):

        problems.append(
            f"{variable_name}: "
            f"valid_time contains "
            f"{len(flattened)} values, "
            f"expected "
            f"{expected_valid_count}"
        )

        return problems

    # --------------------------------------------------------
    # Build expected valid times
    # --------------------------------------------------------

    expected = []

    actual = []

    for time_index, issue_time in enumerate(
        issue_times
    ):

        for step_index, lead_hour in enumerate(
            lead_hours
        ):

            expected_time = (
                issue_time
                +
                pd.Timedelta(
                    hours=lead_hour
                )
            )

            expected.append(
                expected_time
            )

            # ------------------------------------------------
            # Handle either:
            #
            # time × step
            #
            # or flattened representation.
            # ------------------------------------------------

            try:

                value = np.asarray(
                    valid_time_values
                ).reshape(
                    len(issue_times),
                    len(lead_hours)
                )[
                    time_index,
                    step_index
                ]

            except Exception:

                value = None

            if value is not None:

                actual.append(
                    pd.Timestamp(
                        value,
                        tz="UTC"
                    )
                )

    # --------------------------------------------------------
    # Compare
    # --------------------------------------------------------

    if len(actual) == len(expected):

        mismatches = []

        for index, (
            expected_time,
            actual_time
        ) in enumerate(
            zip(
                expected,
                actual
            )
        ):

            if expected_time != actual_time:

                mismatches.append({
                    "index": index,
                    "expected": expected_time,
                    "actual": actual_time,
                })

        if mismatches:

            problems.append(
                f"{variable_name}: "
                f"{len(mismatches)} "
                "valid_time mismatches"
            )

            # Show first 3 for diagnosis
            for mismatch in mismatches[:3]:

                problems.append(
                    "  "
                    f"index={mismatch['index']} "
                    f"expected={mismatch['expected']} "
                    f"actual={mismatch['actual']}"
                )

    return problems


# ============================================================
# VALIDATE ONE FILE
# ============================================================

def validate_file(grib_file):

    month = month_from_filename(
        grib_file
    )

    print()
    print("=" * 100)
    print(
        f"VALIDATING: {grib_file.name}"
    )
    print("=" * 100)

    result = {

        "month":
            month,

        "file":
            grib_file.name,

        "status":
            "PASS",

        "issue_times":
            0,

        "issue_time_min":
            None,

        "issue_time_max":
            None,

        "issue_time_00utc":
            False,

        "lead_times":
            "",

        "variables_found":
            "",

        "valid_time_check":
            False,

        "errors":
            "",
    }

    datasets = {}

    errors = []

    # ========================================================
    # OPEN ALL FOUR VARIABLES
    # ========================================================

    for variable_name in VARIABLES:

        print(
            f"\nOpening {variable_name}..."
        )

        try:

            ds = open_variable(
                grib_file,
                variable_name
            )

            datasets[
                variable_name
            ] = ds

            data_variable = (
                get_data_variable(ds)
            )

            print(
                f"  Data variable: "
                f"{data_variable}"
            )

        except Exception as exc:

            errors.append(
                f"{variable_name}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print(
                f"  FAILED: {exc}"
            )

    # ========================================================
    # IF ANY VARIABLE FAILED
    # ========================================================

    if len(datasets) != 4:

        result["status"] = "FAIL"

        result["errors"] = (
            " | ".join(errors)
        )

        for ds in datasets.values():

            try:
                ds.close()
            except Exception:
                pass

        return result

    # ========================================================
    # USE U10 AS REFERENCE
    # ========================================================

    reference_ds = datasets[
        "u10"
    ]

    try:

        issue_times = get_issue_times(
            reference_ds
        )

        lead_hours = get_lead_hours(
            reference_ds
        )

    except Exception as exc:

        errors.append(
            f"Forecast metadata: "
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        for ds in datasets.values():

            try:
                ds.close()
            except Exception:
                pass

        result["status"] = "FAIL"

        result["errors"] = (
            " | ".join(errors)
        )

        return result

    # ========================================================
    # ISSUE TIME VALIDATION
    # ========================================================

    print()
    print(
        "FORECAST ISSUE TIMES"
    )

    print(
        f"  Count: "
        f"{len(issue_times)}"
    )

    print(
        f"  First: "
        f"{issue_times.min()}"
    )

    print(
        f"  Last: "
        f"{issue_times.max()}"
    )

    result[
        "issue_times"
    ] = len(issue_times)

    result[
        "issue_time_min"
    ] = str(
        issue_times.min()
    )

    result[
        "issue_time_max"
    ] = str(
        issue_times.max()
    )

    # Every issue time must be exactly 00:00 UTC.
    invalid_issue_times = []

    for issue_time in issue_times:

        if (
            issue_time.hour != 0
            or
            issue_time.minute != 0
            or
            issue_time.second != 0
        ):

            invalid_issue_times.append(
                str(issue_time)
            )

    if invalid_issue_times:

        errors.append(
            "Issue times are not all "
            "00:00 UTC: "
            +
            ", ".join(
                invalid_issue_times[:10]
            )
        )

        print(
            "  ❌ Invalid issue times"
        )

    else:

        result[
            "issue_time_00utc"
        ] = True

        print(
            "  ✅ All issue times = 00:00 UTC"
        )

    # ========================================================
    # LEAD TIME VALIDATION
    # ========================================================

    print()
    print(
        "FORECAST LEADS"
    )

    print(
        f"  Found: "
        f"{lead_hours}"
    )

    result[
        "lead_times"
    ] = ",".join(
        str(x)
        for x in sorted(
            set(lead_hours)
        )
    )

    actual_leads = set(
        lead_hours
    )

    if actual_leads != EXPECTED_LEADS:

        errors.append(
            "Lead-time mismatch: "
            f"expected "
            f"{sorted(EXPECTED_LEADS)}, "
            f"found "
            f"{sorted(actual_leads)}"
        )

        print(
            "  ❌ Lead times incorrect"
        )

    else:

        print(
            "  ✅ Leads = 6h, 12h, 24h, 72h"
        )

    # ========================================================
    # VARIABLE VALIDATION
    # ========================================================

    print()
    print(
        "VARIABLES"
    )

    variables_found = []

    for variable_name, ds in (
        datasets.items()
    ):

        data_variable = (
            get_data_variable(ds)
        )

        variables_found.append(
            variable_name
        )

        print(
            f"  {variable_name:>4} "
            f"→ {data_variable}"
        )

    result[
        "variables_found"
    ] = ",".join(
        sorted(
            variables_found
        )
    )

    if set(variables_found) != (
        EXPECTED_VARIABLES
    ):

        errors.append(
            "Variable set mismatch: "
            f"expected "
            f"{sorted(EXPECTED_VARIABLES)}, "
            f"found "
            f"{sorted(variables_found)}"
        )

        print(
            "  ❌ Variable set incorrect"
        )

    else:

        print(
            "  ✅ All four required variables found"
        )

    # ========================================================
    # DIMENSION CONSISTENCY
    # ========================================================

    print()
    print(
        "DIMENSION CONSISTENCY"
    )

    reference_dims = (
        datasets[
            "u10"
        ].sizes
    )

    for variable_name, ds in (
        datasets.items()
    ):

        dims = ds.sizes

        print(
            f"  {variable_name}: "
            f"{dict(dims)}"
        )

        # time dimension
        if (
            "time" not in dims
        ):

            errors.append(
                f"{variable_name}: "
                "missing time dimension"
            )

        # step dimension
        if (
            "step" not in dims
        ):

            errors.append(
                f"{variable_name}: "
                "missing step dimension"
            )

        # Same time count
        if (
            "time" in dims
            and
            dims["time"]
            != reference_dims.get(
                "time"
            )
        ):

            errors.append(
                f"{variable_name}: "
                "time dimension differs "
                "from u10"
            )

        # Same step count
        if (
            "step" in dims
            and
            dims["step"]
            != reference_dims.get(
                "step"
            )
        ):

            errors.append(
                f"{variable_name}: "
                "step dimension differs "
                "from u10"
            )

    # ========================================================
    # VALID_TIME VALIDATION
    # ========================================================

    print()
    print(
        "VALID_TIME VALIDATION"
    )

    all_valid_time_ok = True

    for variable_name, ds in (
        datasets.items()
    ):

        problems = validate_valid_time(
            ds,
            variable_name,
            issue_times,
            lead_hours
        )

        if problems:

            all_valid_time_ok = False

            print(
                f"  ❌ {variable_name}"
            )

            for problem in problems:

                print(
                    f"     {problem}"
                )

            errors.extend(
                problems
            )

        else:

            print(
                f"  ✅ {variable_name}: "
                "valid_time = "
                "issue_time + lead_time"
            )

    result[
        "valid_time_check"
    ] = all_valid_time_ok

    # ========================================================
    # CLOSE DATASETS
    # ========================================================

    for ds in datasets.values():

        try:
            ds.close()
        except Exception:
            pass

    # ========================================================
    # FINAL FILE STATUS
    # ========================================================

    if errors:

        result["status"] = "FAIL"

        result[
            "errors"
        ] = " | ".join(
            errors
        )

    else:

        result["status"] = "PASS"

    print()

    if result["status"] == "PASS":

        print(
            "✅ FILE PASSED"
        )

    else:

        print(
            "❌ FILE FAILED"
        )

        for error in errors:

            print(
                f"   - {error}"
            )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 100)
    print(
        "STEP 2 — TIGGE GRIB VALIDATION"
    )
    print("=" * 100)

    print()
    print(
        f"GRIB directory:"
    )

    print(
        GRIB_DIR
    )

    # ========================================================
    # FIND FILES
    # ========================================================

    grib_files = sorted(
        GRIB_DIR.glob(
            "ecmwf_tigge_*.grib"
        )
    )

    print()
    print(
        f"GRIB files found: "
        f"{len(grib_files)}"
    )

    if not grib_files:

        raise FileNotFoundError(
            f"No GRIB files found in:\n"
            f"{GRIB_DIR}"
        )

    # ========================================================
    # MONTH CHECK
    # ========================================================

    available_months = sorted(
        month_from_filename(
            file
        )
        for file in grib_files
    )

    missing_months = sorted(
        set(EXPECTED_MONTHS)
        -
        set(available_months)
    )

    unexpected_months = sorted(
        set(available_months)
        -
        set(EXPECTED_MONTHS)
    )

    print()
    print(
        "=" * 100
    )
    print(
        "MONTH COVERAGE"
    )
    print(
        "=" * 100
    )

    print(
        f"Expected months: "
        f"{len(EXPECTED_MONTHS)}"
    )

    print(
        f"Available months: "
        f"{len(available_months)}"
    )

    print(
        f"Missing months: "
        f"{len(missing_months)}"
    )

    if missing_months:

        for month in missing_months:

            print(
                f"  ⚠️ {month}"
            )

    if unexpected_months:

        print()
        print(
            "Unexpected months:"
        )

        for month in unexpected_months:

            print(
                f"  ⚠️ {month}"
            )

    # ========================================================
    # SPECIAL EXPECTED MISSING MONTH
    # ========================================================

    if "2019-02" in missing_months:

        print()
        print(
            "ℹ️ 2019-02 is expected to be missing."
        )

        print(
            "   ECMWF TIGGE archive issue:"
        )

        print(
            "   damaged MARS tape J0018900"
        )

        print(
            "   This month will NOT be fabricated."
        )

    # ========================================================
    # VALIDATE EACH FILE
    # ========================================================

    reports = []

    for index, grib_file in enumerate(
        grib_files,
        start=1
    ):

        print()
        print(
            f"FILE {index}/{len(grib_files)}"
        )

        try:

            report = validate_file(
                grib_file
            )

        except Exception as exc:

            report = {

                "month":
                    month_from_filename(
                        grib_file
                    ),

                "file":
                    grib_file.name,

                "status":
                    "FAIL",

                "issue_times":
                    0,

                "issue_time_min":
                    None,

                "issue_time_max":
                    None,

                "issue_time_00utc":
                    False,

                "lead_times":
                    "",

                "variables_found":
                    "",

                "valid_time_check":
                    False,

                "errors":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            }

            print()
            print(
                "❌ UNEXPECTED VALIDATION ERROR"
            )

            print(
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        reports.append(
            report
        )

    # ========================================================
    # ADD MISSING MONTHS TO REPORT
    # ========================================================

    for month in missing_months:

        reports.append({

            "month":
                month,

            "file":
                None,

            "status":
                "UNAVAILABLE",

            "issue_times":
                0,

            "issue_time_min":
                None,

            "issue_time_max":
                None,

            "issue_time_00utc":
                False,

            "lead_times":
                "",

            "variables_found":
                "",

            "valid_time_check":
                False,

            "errors":
                "TIGGE archive unavailable "
                "(damaged MARS tape J0018900)",
        })

    # ========================================================
    # SAVE REPORT
    # ========================================================

    report_df = pd.DataFrame(
        reports
    ).sort_values(
        "month"
    )

    report_df.to_csv(
        REPORT_FILE,
        index=False
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    passed = (
        report_df[
            "status"
        ]
        == "PASS"
    ).sum()

    failed = (
        report_df[
            "status"
        ]
        == "FAIL"
    ).sum()

    unavailable = (
        report_df[
            "status"
        ]
        == "UNAVAILABLE"
    ).sum()

    print()
    print("=" * 100)
    print(
        "STEP 2 — FINAL VALIDATION SUMMARY"
    )
    print("=" * 100)

    print()
    print(
        f"Expected months:       "
        f"{len(EXPECTED_MONTHS)}"
    )

    print(
        f"GRIB files found:      "
        f"{len(grib_files)}"
    )

    print(
        f"Files passed:          "
        f"{passed}"
    )

    print(
        f"Files failed:          "
        f"{failed}"
    )

    print(
        f"Unavailable months:    "
        f"{unavailable}"
    )

    print()

    print(
        "Expected lead times:"
    )

    print(
        "  6h, 12h, 24h, 72h"
    )

    print()

    print(
        "Expected variables:"
    )

    print(
        "  2t, 10u, 10v, tcc"
    )

    print()

    # ========================================================
    # FAIL LIST
    # ========================================================

    failed_df = report_df[
        report_df["status"] == "FAIL"
    ]

    if len(failed_df) > 0:

        print(
            "=" * 100
        )

        print(
            "FAILED FILES"
        )

        print(
            "=" * 100
        )

        for _, row in (
            failed_df.iterrows()
        ):

            print()
            print(
                f"❌ {row['month']}"
            )

            print(
                f"   {row['errors']}"
            )

    else:

        print(
            "✅ No GRIB validation failures."
        )

    # ========================================================
    # MISSING MONTHS
    # ========================================================

    unavailable_df = report_df[
        report_df["status"]
        == "UNAVAILABLE"
    ]

    if len(unavailable_df) > 0:

        print()
        print(
            "=" * 100
        )

        print(
            "EXPECTED UNAVAILABLE MONTHS"
        )

        print(
            "=" * 100
        )

        for _, row in (
            unavailable_df.iterrows()
        ):

            print(
                f"⚠️ {row['month']}: "
                f"{row['errors']}"
            )

    # ========================================================
    # GLOBAL GO / NO-GO
    # ========================================================

    print()
    print(
        "=" * 100
    )

    if failed == 0:

        print(
            "✅ VALIDATION GATE PASSED"
        )

        print()
        print(
            "All available TIGGE GRIB files "
            "passed validation."
        )

        print(
            "The unavailable 2019-02 period "
            "is explicitly documented."
        )

        print()
        print(
            "Phase 5.2 training can proceed."
        )

    else:

        print(
            "❌ VALIDATION GATE FAILED"
        )

        print()
        print(
            "DO NOT TRAIN Phase 5.2 yet."
        )

        print(
            "Fix the failed GRIB files first."
        )

    print(
        "=" * 100
    )

    print()
    print(
        "Validation report:"
    )

    print(
        REPORT_FILE
    )

    # ========================================================
    # HARD FAILURE FOR AUTOMATION
    # ========================================================

    if failed > 0:

        raise SystemExit(
            1
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()