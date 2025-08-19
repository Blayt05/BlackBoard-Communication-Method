import threading
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import math
from enum import Enum

class TaskStatus(Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class RobotStatus(Enum):
    IDLE = "idle"
    MOVING = "moving"
    PICKING = "picking"
    COLLISION_AVOIDANCE = "collision_avoidance"

@dataclass
class RobotInfo:
    id: int
    x: float
    y: float
    velocity: float
    status: RobotStatus
    current_task: Optional[int] = None
    path: List[Tuple[float, float]] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.now)

@dataclass
class BoxInfo:
    id: int
    x: float
    y: float
    picked: bool
    assigned_to: Optional[int] = None
    priority: int = 0

@dataclass
class CollisionZone:
    x: float
    y: float
    radius: float
    robot_id: int
    timestamp: datetime

class Blackboard:
    def __init__(self):
        self.lock = threading.RLock()
        self.robots: Dict[int, RobotInfo] = {}
        self.boxes: Dict[int, BoxInfo] = {}
        self.collision_zones: List[CollisionZone] = []
        self.task_assignments: Dict[int, int] = {}
        self.completed_tasks: List[int] = []
        self.message_log: List[Dict[str, Any]] = []
        
    def register_robot(self, robot_id: int, x: float, y: float, velocity: float):
        with self.lock:
            self.robots[robot_id] = RobotInfo(
                id=robot_id,
                x=x,
                y=y,
                velocity=velocity,
                status=RobotStatus.IDLE
            )
            self._log_message("REGISTER", f"Robot {robot_id} registered at ({x:.2f}, {y:.2f})")
    
    def register_box(self, box_id: int, x: float, y: float, priority: int = 0):
        with self.lock:
            self.boxes[box_id] = BoxInfo(
                id=box_id,
                x=x,
                y=y,
                picked=False,
                priority=priority
            )
            self._log_message("REGISTER", f"Box {box_id} registered at ({x:.2f}, {y:.2f})")
    
    def update_robot_position(self, robot_id: int, x: float, y: float):
        with self.lock:
            if robot_id in self.robots:
                self.robots[robot_id].x = x
                self.robots[robot_id].y = y
                self.robots[robot_id].last_update = datetime.now()
                self._check_collision_zones(robot_id)
    
    def update_robot_status(self, robot_id: int, status: RobotStatus):
        with self.lock:
            if robot_id in self.robots:
                self.robots[robot_id].status = status
                self._log_message("STATUS", f"Robot {robot_id} status changed to {status.value}")
    
    def assign_task(self, robot_id: int, box_id: int):
        with self.lock:
            if robot_id in self.robots and box_id in self.boxes:
                if not self.boxes[box_id].picked and self.boxes[box_id].assigned_to is None:
                    self.robots[robot_id].current_task = box_id
                    self.boxes[box_id].assigned_to = robot_id
                    self.task_assignments[robot_id] = box_id
                    self._log_message("ASSIGN", f"Box {box_id} assigned to Robot {robot_id}")
                    return True
            return False
    
    def complete_task(self, robot_id: int, box_id: int):
        with self.lock:
            if robot_id in self.robots and box_id in self.boxes:
                self.boxes[box_id].picked = True
                self.robots[robot_id].current_task = None
                self.robots[robot_id].status = RobotStatus.IDLE
                self.completed_tasks.append(box_id)
                if robot_id in self.task_assignments:
                    del self.task_assignments[robot_id]
                self._log_message("COMPLETE", f"Robot {robot_id} completed task for Box {box_id}")
    
    def get_available_boxes(self) -> List[BoxInfo]:
        with self.lock:
            return [box for box in self.boxes.values() 
                   if not box.picked and box.assigned_to is None]
    
    def get_nearest_available_box(self, robot_id: int) -> Optional[BoxInfo]:
        with self.lock:
            if robot_id not in self.robots:
                return None
            
            robot = self.robots[robot_id]
            available_boxes = self.get_available_boxes()
            
            if not available_boxes:
                return None
            
            nearest_box = min(available_boxes,
                            key=lambda box: self._calculate_distance(
                                robot.x, robot.y, box.x, box.y
                            ))
            return nearest_box
    
    def reserve_collision_zone(self, robot_id: int, x: float, y: float, radius: float = 2.0):
        with self.lock:
            zone = CollisionZone(x=x, y=y, radius=radius, 
                                robot_id=robot_id, timestamp=datetime.now())
            self.collision_zones.append(zone)
            self._clean_old_collision_zones()
    
    def check_collision_risk(self, robot_id: int, target_x: float, target_y: float) -> bool:
        with self.lock:
            for zone in self.collision_zones:
                if zone.robot_id != robot_id:
                    dist = self._calculate_distance(target_x, target_y, zone.x, zone.y)
                    if dist < zone.radius:
                        return True
            
            for other_id, other_robot in self.robots.items():
                if other_id != robot_id:
                    dist = self._calculate_distance(target_x, target_y, 
                                                   other_robot.x, other_robot.y)
                    if dist < 2.0:
                        return True
            return False
    
    def get_safe_path(self, robot_id: int, target_x: float, target_y: float) -> List[Tuple[float, float]]:
        with self.lock:
            if robot_id not in self.robots:
                return []
            
            robot = self.robots[robot_id]
            path = []
            
            if not self.check_collision_risk(robot_id, target_x, target_y):
                path = [(target_x, target_y)]
            else:
                intermediate_points = self._calculate_avoidance_path(
                    robot.x, robot.y, target_x, target_y, robot_id
                )
                path = intermediate_points
            
            self.robots[robot_id].path = path
            return path
    
    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    
    def _calculate_avoidance_path(self, start_x: float, start_y: float, 
                                  end_x: float, end_y: float, robot_id: int) -> List[Tuple[float, float]]:
        path = []
        steps = 10
        for i in range(1, steps + 1):
            t = i / steps
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            
            if self.check_collision_risk(robot_id, x, y):
                offset = 3.0
                x += offset * (1 if i % 2 == 0 else -1)
                y += offset * (1 if i % 2 == 0 else -1)
            
            path.append((x, y))
        
        return path
    
    def _check_collision_zones(self, robot_id: int):
        if robot_id in self.robots:
            robot = self.robots[robot_id]
            for zone in self.collision_zones:
                if zone.robot_id != robot_id:
                    dist = self._calculate_distance(robot.x, robot.y, zone.x, zone.y)
                    if dist < zone.radius * 1.5:
                        self.robots[robot_id].status = RobotStatus.COLLISION_AVOIDANCE
                        self._log_message("WARNING", 
                                        f"Robot {robot_id} entering collision zone of Robot {zone.robot_id}")
    
    def _clean_old_collision_zones(self):
        current_time = datetime.now()
        self.collision_zones = [
            zone for zone in self.collision_zones
            if (current_time - zone.timestamp).seconds < 5
        ]
    
    def _log_message(self, msg_type: str, message: str):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": msg_type,
            "message": message
        }
        self.message_log.append(log_entry)
        if len(self.message_log) > 100:
            self.message_log = self.message_log[-100:]
    
    def get_system_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "robots": {rid: {
                    "id": r.id,
                    "position": (r.x, r.y),
                    "status": r.status.value,
                    "current_task": r.current_task,
                    "last_update": r.last_update.isoformat()
                } for rid, r in self.robots.items()},
                "boxes": {bid: {
                    "id": b.id,
                    "position": (b.x, b.y),
                    "picked": b.picked,
                    "assigned_to": b.assigned_to,
                    "priority": b.priority
                } for bid, b in self.boxes.items()},
                "active_assignments": self.task_assignments,
                "completed_tasks": self.completed_tasks,
                "collision_zones": len(self.collision_zones)
            }