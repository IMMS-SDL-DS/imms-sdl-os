"""
src/pipeline/dispense_command.py 테스트
"""

from src.pipeline.dispense_command import run_dispense_command


def test_dispense_success_within_tolerance():
    def fake_driver(reagent, target_mass_mg, tolerance_mg, vessel):
        return {"actual_mass_mg": target_mass_mg, "success": True}

    task = run_dispense_command(
        "ZrOCl2", 97, "Vial_10mL", robot_driver=fake_driver, save_to_db=False
    )
    assert task.status == "success"
    assert task.actual_values["actual_mass_mg"] == 97
    assert len(task.output_refs) == 1


def test_dispense_failure_outside_tolerance():
    def fake_driver(reagent, target_mass_mg, tolerance_mg, vessel):
        return {"actual_mass_mg": target_mass_mg + 999, "success": False}

    task = run_dispense_command(
        "BTC", 21, "Vial_5mL", robot_driver=fake_driver, save_to_db=False
    )
    assert task.status == "failed"


def test_dispense_is_generalized_across_reagents():
    """특정 프로토콜에 종속되지 않고 어떤 소재든 동일한 함수로 처리되는지."""
    def fake_driver(reagent, target_mass_mg, tolerance_mg, vessel):
        return {"actual_mass_mg": target_mass_mg, "success": True}

    for reagent, mass, vessel in [("ZrOCl2", 97, "Vial_10mL"), ("BTC", 21, "Vial_5mL"), ("NaCl", 50, "Vial_5mL")]:
        task = run_dispense_command(reagent, mass, vessel, robot_driver=fake_driver, save_to_db=False)
        assert task.parameters["reagent"] == reagent
        assert task.status == "success"
