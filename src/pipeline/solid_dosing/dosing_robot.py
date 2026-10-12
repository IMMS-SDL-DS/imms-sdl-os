import sys
import os
import time
import xml.etree.ElementTree as ET

from rtde_control import RTDEControlInterface

from .libs.mt_xpr_webservice import Robot, XprBalance
from .libs.robotiq_preamble import ROBOTIQ_PREAMBLE
from .config import GRIPPER_SPEED  # Imported from config.py

WAYPOINTS_XML = "vial_waypoints.xml"

# Speed & Acceleration Parameters
SPEED_JOINT  = 1.0   # rad/s
ACCEL_JOINT  = 1.4   # rad/s^2

SPEED_LINEAR = 0.12  # m/s
ACCEL_LINEAR = 0.4   # m/s^2

SPEED_INSERT = 0.04  # m/s (Slow velocity inside balance chamber)
ACCEL_INSERT = 0.2   # m/s^2


class DosingRobotController(Robot):
    """
    UR3e robot arm and Robotiq gripper controller.
    Executes waypoint sequences from XML and manages balance door state transitions.
    """
    def __init__(self, robot_ip: str, balance_instance: XprBalance = None, waypoints_file: str = WAYPOINTS_XML, door_settle_s: float = 2.0):
        self.robot_ip = robot_ip
        self.bal = balance_instance
        self.waypoints_file = waypoints_file
        self.door_settle_s = door_settle_s

    def _safe_open_doors(self) -> None:
        """Opens draft shields and waits for air pressure to equalize."""
        if self.bal:
            print("\n[Door Control] Opening all draft shields for robot access...")
            self.bal.open_all_doors()
            time.sleep(self.door_settle_s)

    def _safe_close_doors(self) -> None:
        """Closes draft shields to ensure stable weighing conditions."""
        if self.bal:
            print("[Door Control] Closing all draft shields tightly...")
            self.bal.close_all_doors()
            time.sleep(self.door_settle_s)

    def _load_sequence_from_xml(self, sequence_name: str):
        """Parses moves and gripper commands from XML under <sequence name='...'>."""
        try:
            tree = ET.parse(self.waypoints_file)
            root = tree.getroot()
            sequence_node = root.find(f"./sequence[@name='{sequence_name}']")
            
            if sequence_node is None:
                print(f"[XML Parse Error] Sequence '{sequence_name}' not found in {self.waypoints_file}.")
                return []

            commands = []
            for step in sequence_node:
                if step.tag == "move":
                    commands.append({
                        "type": "move",
                        "move_type": step.get("type"),
                        "pose": [
                            float(step.get("x")), float(step.get("y")), float(step.get("z")),
                            float(step.get("rx")), float(step.get("ry")), float(step.get("rz"))
                        ]
                    })
                elif step.tag == "gripper":
                    commands.append({
                        "type": "gripper",
                        "action": step.get("action"),
                        "power": float(step.get("power", 10.0))
                    })
            return commands
        except Exception as e:
            print(f"[XML Parse Error] Could not read path profile {self.waypoints_file}: {e}")
            return []

    def _gripper_call(self, rtde_c: RTDEControlInterface, name: str, script_function: str) -> bool:
        full_script = ROBOTIQ_PREAMBLE + "\n" + script_function + "\n"
        return rtde_c.sendCustomScriptFunction("ROBOTIQ_" + name, full_script)

    def _gripper_activate(self, rtde_c: RTDEControlInterface) -> None:
        self._gripper_call(rtde_c, "ACTIVATE", "rq_activate_and_wait()")

    def _gripper_control(self, rtde_c: RTDEControlInterface, close: bool, xml_power: float) -> None:
        # Calculate force from XML power (0-10 scale mapped to 0-255 raw register value)
        target_force = int((xml_power / 10.0) * 255)
        target_force = max(0, min(255, target_force))
        
        # Use GRIPPER_SPEED from config.py (0 = ~22 mm/s)
        target_speed = GRIPPER_SPEED

        if close:
            script = f"rq_set_force({target_force})\nrq_set_speed({target_speed})\nrq_close_and_wait()"
            self._gripper_call(rtde_c, "CLOSE", script)
        else:
            script = f"rq_set_force({target_force})\nrq_set_speed({target_speed})\nrq_open_and_wait()"
            self._gripper_call(rtde_c, "OPEN", script)
            
        time.sleep(1.5)

    def _execute_sequence(self, sequence_name: str, descriptive_task_label: str) -> None:
        commands = self._load_sequence_from_xml(sequence_name)
        
        if not commands:
            print(f"[Warning] Sequence execution skipped: {self.waypoints_file} is empty or missing sequence '{sequence_name}'.")
            return

        print(f"Connecting to UR3e robot arm network at {self.robot_ip}...")
        try:
            rtde_c = RTDEControlInterface(self.robot_ip)
            print("UR3e Connection Established Successfully.")
            self._gripper_activate(rtde_c)
        except Exception as e:
            print(f"[Critical Error] Failed to secure connection channels to UR3e:\n{e}")
            return

        try:
            print(f"\n--- Starting Automated UR3e Action Sequence: {descriptive_task_label} ---")
            
            for cmd in commands:
                if cmd["type"] == "move":
                    move_type = cmd["move_type"]
                    pose = cmd["pose"]

                    is_inside_balance = (pose[2] <= 0.28)
                    current_l_speed = SPEED_INSERT if is_inside_balance else SPEED_LINEAR
                    current_l_accel = ACCEL_INSERT if is_inside_balance else ACCEL_LINEAR

                    if move_type == "joint":
                        print(f" -> [Trajectory] MoveJ_IK to pose: {pose}")
                        rtde_c.moveJ_IK(pose, SPEED_JOINT, ACCEL_JOINT)
                    elif move_type == "linear":
                        print(f" -> [Trajectory] MoveL to pose: {pose} (speed: {current_l_speed} m/s)")
                        rtde_c.moveL(pose, current_l_speed, current_l_accel)

                elif cmd["type"] == "gripper":
                    action = cmd["action"]
                    power = cmd["power"]
                    is_closing = (action == "close")
                    print(f" -> [Gripper Action] {'Closing' if is_closing else 'Opening'} gripper (Power level: {power})...")
                    self._gripper_control(rtde_c, close=is_closing, xml_power=power)

            print(f"--- Action Sequence Complete: {descriptive_task_label} Finished ---\n")
            time.sleep(1.0)
            
        finally:
            try:
                rtde_c.stopScript()
                rtde_c.disconnect()
                print("UR3e connection closed safely.")
            except Exception:
                pass

    def place_vial(self, vial_name: str) -> None:
        """Called automatically by run_dosing_jobs when balance requests PlaceVial."""
        print(f"\n[Robot Action Protocol] Executing place_vial for '{vial_name}'...")
        self._safe_open_doors()
        self._execute_sequence("place", f"Place Vial ({vial_name})")
        self._safe_close_doors()

    def remove_vial(self, vial_name: str) -> None:
        """Called automatically by run_dosing_jobs when balance requests RemoveVial."""
        print(f"\n[Robot Action Protocol] Executing remove_vial for '{vial_name}'...")
        self._safe_open_doors()
        self._execute_sequence("remove", f"Remove Vial ({vial_name})")
        self._safe_close_doors()

    def place_dosing_head(self, head_name: str) -> None: pass
    def remove_dosing_head(self, head_name: str) -> None: pass