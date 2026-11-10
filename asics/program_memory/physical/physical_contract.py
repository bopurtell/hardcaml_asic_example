"""Independent example assertions for the documented A/B physical bundle handoff."""
import json


def electrical_settings(corners):
    return {
        "RUN_POST_GRT_DESIGN_REPAIR": True,
        "GRT_DESIGN_REPAIR_RUN_GRT": True,
        "GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH": 200.0,
        "GRT_DESIGN_REPAIR_MAX_SLEW_PCT": 20,
        "GRT_DESIGN_REPAIR_MAX_CAP_PCT": 20,
        "RSZ_CORNERS": corners,
    }


def check_contract(contract, config, files):
    def require(condition, label):
        if not condition:
            raise AssertionError("physical contract: " + label)

    require(contract["schema_version"] == 2 and contract["execution"] == "fresh_full", "version/execution")
    macro, = contract["macros"]
    intent = macro["physical_intent"]
    require(intent["execution"] == "fresh_full", "physical intent execution")
    expected = {
        "schema_version": 1, "strategy": "cmos5l_m4_edge_access_v1",
        "plan_file": "physical/macro-plan.json", "pdn_tcl": "physical/pdn.tcl",
        "checking_profile": "cmos5l_real_gds_v1",
        "lvs_scope": "abstract_macro_boundary_with_schematic_cdl",
        "macros": [{"resource": macro["resource"], "instance": macro["instance"], "module": macro["module"],
                    "location_um": intent["location_um"], "orientation": intent["orientation"],
                    "halo_um": intent["halo_um"], "supplies": intent["power"]}],
    }
    require(contract["physical_plan"] == expected, "complete exact physical plan")
    require(json.loads(files[expected["plan_file"]]) == expected, "embedded/file plan agreement")
    require(bool(files[expected["pdn_tcl"]].strip()), "nonempty generated PDN program")
    for key, value in {
        "PDN_CFG": "dir::../physical/pdn.tcl", "PDN_CONNECT_MACROS_TO_GRID": True,
        "PDN_MULTILAYER": False, "PDN_VERTICAL_LAYER": "Metal4",
        "PDN_VWIDTH": 2.1, "PDN_VPITCH": 50.0, "PDN_VOFFSET": 10.0, "PDN_VSPACING": 2.0,
        "PDN_ENABLE_RAILS": True, "PDN_ENABLE_PINS": True, "PDN_ENABLE_GLOBAL_CONNECTIONS": True,
        "PDN_RAIL_LAYER": "Metal1", "PDN_RAIL_WIDTH": 0.44,
        "PDN_SKIPTRIM": False, "PDN_CORE_RING": False,
        "PDN_HORIZONTAL_HALO": 0.0, "PDN_VERTICAL_HALO": 0.0,
        "FP_MACRO_HORIZONTAL_HALO": 2.0, "FP_MACRO_VERTICAL_HALO": 2.0,
        "RUN_KLAYOUT_STREAMOUT": True, "PRIMARY_GDSII_STREAMOUT_TOOL": "klayout", "RUN_KLAYOUT_DRC": True,
        "KLAYOUT_DRC_RUNSET": "pdk_dir::libs.tech/klayout/tech/drc/ihp-sg13cmos5l.drc",
        "KLAYOUT_DRC_THREADS": 6, "KLAYOUT_XOR_THREADS": 6,
        "KLAYOUT_DRC_OPTIONS": {"no_feol": "false", "no_beol": "false", "no_offgrid": "false",
                                "no_angle": "false", "no_pin": "false", "no_forbidden": "false",
                                "no_recommended": "false", "precheck_drc": "false",
                                "log": "drc-klayout.log", "threads": 6},
        "EXTRA_SPICE_MODELS": ["pdk_dir::libs.ref/sg13cmos5l_sram/cdl/" + macro["module"] + ".cdl"],
        "RUN_MAGIC_DRC": True, "ERROR_ON_ILLEGAL_OVERLAPS": True,
        "MAGIC_MACRO_STD_CELL_SOURCE": "PDK", "MAGIC_EXT_ABSTRACT_CELLS": [macro["module"]],
        "MAGIC_DRC_USE_GDS": False,
    }.items():
        require(config.get(key) == value, "generated setting " + key)
    require(config["STA_CORNERS"] == ["nom_fast_1p32V_m40C", "nom_slow_1p08V_125C",
                                      "nom_typ_1p20V_25C"], "exact all-corner repair models")
    for key, value in electrical_settings(config["STA_CORNERS"]).items():
        require(config.get(key) == value, "generated electrical repair setting " + key)
    require(not any(key.startswith("GLB_RESIZER_") for key in config), "no deprecated electrical repair aliases")
    require(not any(key.startswith("FP_PDN_") for key in config), "no legacy PDN overrides")
    x, y = intent["location_um"]
    obstructions = config["ROUTING_OBSTRUCTIONS"]
    require(len(obstructions) == 1, "one macro routing obstruction")
    layer, *coordinates = obstructions[0].split()
    require(layer == "Metal4" and list(map(float, coordinates)) == [x, y, x + 236.8, y + 118.78],
            "exact Metal4 footprint only; preserve lower-layer signal access")
    instance = "^" + macro["instance"] + "$"  # specimen's canonical instance needs no regex escaping
    require(config["PDN_MACRO_CONNECTIONS"] == [
        instance + " VPWR VGND VDD! VSS!", instance + " VPWR VGND VDDARRAY! VSS!"],
        "both anchored instance supply hooks")
