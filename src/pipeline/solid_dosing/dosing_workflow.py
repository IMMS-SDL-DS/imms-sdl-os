# dosing_workflow.py

import time

from .libs.mt_xpr_webservice import XprBalance, DosingJob
from .config import BALANCE_HOST, BALANCE_PORT, BALANCE_PASSWORD, UR_HOST, LOWER_TOLERANCE, UPPER_TOLERANCE
from .dosing_robot import DosingRobotController
from .csv_logger import log_to_csv, CSV_FILE_NAME


class DosingWorkflowManager:
    def __init__(self, recipes: dict = None, dosing_method: str = "0415_AD", vial_name: str = "Vial1", door_settle_s: float = 2.0):
        self.recipes = recipes
        self.dosing_method = dosing_method
        self.vial_name = vial_name
        self.door_settle_s = door_settle_s
        
        self.bal = XprBalance(host=BALANCE_HOST, port=BALANCE_PORT, client_password=BALANCE_PASSWORD)
        self.robot = DosingRobotController(robot_ip=UR_HOST, balance_instance=self.bal, door_settle_s=door_settle_s)

    def select_substance(self) -> tuple:
        print("============================================================")
        print("RECIPE INDEX: " + ", ".join(self.recipes.keys()))
        user_substance = input("Input: Enter the name of the target substance: ").strip()
        print("============================================================")
        
        if user_substance not in self.recipes:
            print(f"Error: '{user_substance}' is not registered in recipes.")
            return None, None, None

        target_val, target_unit = self.recipes[user_substance]
        return user_substance, target_val, target_unit

    def run(self, substance_name, target_value, target_unit):
        # substance_name, target_value, target_unit = self.select_substance()
        if not substance_name:
            return

        print("Connection: Connecting to Mettler Toledo Web Service...")
        
        try:
            with self.bal.session():
                print("Session Status: Active session started.")
                print("Progress: Executing internal balance zeroing routine...")
                self.bal.zero()
                time.sleep(0.5)

                print(f"\nTask Status: Initializing task workflow profile '{self.dosing_method}'...")
                self.bal.start_task(self.dosing_method)
                time.sleep(0.5)
                
                print("Dosing Head Verification: Querying metadata from currently mounted dosing head...")
                try:
                    head_data = self.bal.read_dosing_head()
                    head_substance = head_data.get("substance")
                    print(f"RFID Verification: Head substance detected from hardware is '{head_substance}'")
                    
                    if not head_substance or head_substance.strip().lower() != substance_name.lower():
                        print("\nVerification Error: Match failure between user input and hardware.")
                        self.bal.cancel_current_task()
                        return
                        
                    print("Verification Status: Match confirmed. Substance alignment verified.")
                    print(f"Active Profile Target: {target_value} {target_unit} (Limits: {LOWER_TOLERANCE} / {UPPER_TOLERANCE})")
                    
                except Exception as e:
                    print(f"Error: Failed to read dosing head memory registers: {e}")
                    self.bal.cancel_current_task()
                    return

                print("Progress: Setting current payload configuration as Tare...")
                self.bal.tare()
                time.sleep(0.5)

                print("\n============================================================")
                print("Automation: Launching Automated Dosing State Machine Loop")
                print("============================================================")
                
                job_list = [DosingJob(
                    substance_name=substance_name,
                    vial_name=self.vial_name,
                    target_value=target_value,
                    target_unit=target_unit,
                    lower_tolerance=LOWER_TOLERANCE,
                    upper_tolerance=UPPER_TOLERANCE
                )]
                
                try:
                    results = self.bal.run_dosing_jobs(jobs=job_list, robot=self.robot)
                    
                    print("\nProgress: Physical material dispense sequence finished.")
                    print("Progress: Pulling stable weight values from SOAP response layers...")
                    
                    # Read final weight with doors closed
                    weight_sample = self.bal.get_weight(wait_for_stable=True)
                    final_weight_value = weight_sample.net_value
                    final_weight_unit = weight_sample.net_unit
                    
                    # Automatically retrieve vial from balance chamber
                    self.robot.remove_vial(self.vial_name)

                    print("\n============================================================")
                    print("UNIFIED DOSING BATCH FINAL REPORT")
                    print("============================================================")
                    for res in results:
                        status_str = "SUCCESS" if res.success else "FAILURE"
                        print(f"Target Vial: {res.vial_name}")
                        print(f"Dispensed Matter: {res.substance_name}")
                        print(f"Target Profile: {res.target_value} {res.target_unit}")
                        print(f"Validated Mass: {final_weight_value} {final_weight_unit}")
                        print(f"Cycle Duration: {res.duration_s} seconds")
                        print(f"Execution Status: {status_str}")
                        
                        log_to_csv(
                            vial=res.vial_name,
                            substance=res.substance_name,
                            target_val=res.target_value,
                            target_unit=res.target_unit,
                            actual_val=final_weight_value,
                            actual_unit=final_weight_unit,
                            duration=res.duration_s,
                            status=status_str,
                            error_msg=res.error,
                            filename=CSV_FILE_NAME
                        )
                    print("============================================================")
                    
                except Exception as e:
                    print(f"\nCritical Failure: Error caught during active state runtime: {e}")
                    self.bal.cancel_current_dosing_job_list()
                    self.bal.cancel_current_task()
                    
                    print("Recovery Action: Actuating doors to safe closed position...")
                    try:
                        self.bal.close_all_doors()
                    except Exception as recovery_err:
                        print(f"Door recovery failed: {recovery_err}")
                    return

                print(f"\nTask Status: Marking method profile task '{self.dosing_method}' as Complete...")
                self.bal.complete_current_task()

            print("\nSession Status: Dosing pipeline safely terminated. Workflow session closed.")

        except (ConnectionError, TimeoutError, OSError) as net_err:
            print("\n============================================================")
            print("CRITICAL ERROR: Network connection is out. Check network cable.")
            print(f"Diagnostic Detail: {net_err}")
            print("============================================================")
        except Exception as e:
            print(f"\nUnexpected Session Error: {e}")