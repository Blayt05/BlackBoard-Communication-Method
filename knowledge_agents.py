import threading
import time
from typing import Optional, List, Tuple
from blackboard import Blackboard, RobotStatus, TaskStatus
import math

class KnowledgeAgent:
    def __init__(self, blackboard: Blackboard):
        self.blackboard = blackboard
        self.active = True
        self.thread = None
    
    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        self.active = False
        if self.thread:
            self.thread.join()
    
    def run(self):
        raise NotImplementedError("Subclasses must implement run method")

class SearchKnowledgeAgent(KnowledgeAgent):
    def __init__(self, blackboard: Blackboard, search_interval: float = 1.0):
        super().__init__(blackboard)
        self.search_interval = search_interval
    
    def run(self):
        while self.active:
            self._search_and_assign_tasks()
            time.sleep(self.search_interval)
    
    def _search_and_assign_tasks(self):
        idle_robots = self._find_idle_robots()
        
        for robot_id in idle_robots:
            nearest_box = self.blackboard.get_nearest_available_box(robot_id)
            
            if nearest_box:
                success = self.blackboard.assign_task(robot_id, nearest_box.id)
                if success:
                    self.blackboard.update_robot_status(robot_id, RobotStatus.MOVING)
                    print(f"KA-S: Assigned box {nearest_box.id} to robot {robot_id}")
    
    def _find_idle_robots(self) -> List[int]:
        idle_robots = []
        with self.blackboard.lock:
            for robot_id, robot_info in self.blackboard.robots.items():
                if robot_info.status == RobotStatus.IDLE and robot_info.current_task is None:
                    idle_robots.append(robot_id)
        return idle_robots
    
    def optimize_assignments(self):
        with self.blackboard.lock:
            robots = list(self.blackboard.robots.values())
            available_boxes = self.blackboard.get_available_boxes()
            
            if not robots or not available_boxes:
                return
            
            assignments = []
            for robot in robots:
                if robot.status == RobotStatus.IDLE:
                    best_box = None
                    best_score = float('inf')
                    
                    for box in available_boxes:
                        if box.assigned_to is None:
                            distance = math.sqrt((robot.x - box.x)**2 + (robot.y - box.y)**2)
                            score = distance - (box.priority * 10)
                            
                            if score < best_score:
                                best_score = score
                                best_box = box
                    
                    if best_box:
                        assignments.append((robot.id, best_box.id))
                        best_box.assigned_to = robot.id
            
            for robot_id, box_id in assignments:
                self.blackboard.assign_task(robot_id, box_id)

class BlackboardReaderAgent(KnowledgeAgent):
    def __init__(self, blackboard: Blackboard, monitoring_interval: float = 0.5):
        super().__init__(blackboard)
        self.monitoring_interval = monitoring_interval
        self.collision_threshold = 3.0
    
    def run(self):
        while self.active:
            self._monitor_collisions()
            self._monitor_task_progress()
            self._update_collision_zones()
            time.sleep(self.monitoring_interval)
    
    def _monitor_collisions(self):
        with self.blackboard.lock:
            robots = list(self.blackboard.robots.values())
            
            for i, robot1 in enumerate(robots):
                for robot2 in robots[i+1:]:
                    distance = math.sqrt(
                        (robot1.x - robot2.x)**2 + 
                        (robot1.y - robot2.y)**2
                    )
                    
                    if distance < self.collision_threshold:
                        print(f"KA-BR: Collision warning between robots {robot1.id} and {robot2.id}")
                        
                        if robot1.status != RobotStatus.COLLISION_AVOIDANCE:
                            self.blackboard.update_robot_status(robot1.id, 
                                                               RobotStatus.COLLISION_AVOIDANCE)
                        if robot2.status != RobotStatus.COLLISION_AVOIDANCE:
                            self.blackboard.update_robot_status(robot2.id, 
                                                               RobotStatus.COLLISION_AVOIDANCE)
    
    def _monitor_task_progress(self):
        with self.blackboard.lock:
            for robot_id, robot_info in self.blackboard.robots.items():
                if robot_info.current_task:
                    box = self.blackboard.boxes.get(robot_info.current_task)
                    if box:
                        distance = math.sqrt(
                            (robot_info.x - box.x)**2 + 
                            (robot_info.y - box.y)**2
                        )
                        
                        if distance < 0.5:
                            print(f"KA-BR: Robot {robot_id} reached box {box.id}")
                            self.blackboard.update_robot_status(robot_id, RobotStatus.PICKING)
    
    def _update_collision_zones(self):
        with self.blackboard.lock:
            for robot_id, robot_info in self.blackboard.robots.items():
                if robot_info.status == RobotStatus.MOVING:
                    self.blackboard.reserve_collision_zone(
                        robot_id, robot_info.x, robot_info.y, radius=2.0
                    )
    
    def get_robot_paths(self, robot_id: int) -> List[Tuple[float, float]]:
        robot = self.blackboard.robots.get(robot_id)
        if not robot or not robot.current_task:
            return []
        
        box = self.blackboard.boxes.get(robot.current_task)
        if not box:
            return []
        
        return self.blackboard.get_safe_path(robot_id, box.x, box.y)

class PlanningAgent(KnowledgeAgent):
    def __init__(self, blackboard: Blackboard, planning_interval: float = 2.0):
        super().__init__(blackboard)
        self.planning_interval = planning_interval
    
    def run(self):
        while self.active:
            self._replan_stuck_robots()
            self._prioritize_tasks()
            time.sleep(self.planning_interval)
    
    def _replan_stuck_robots(self):
        with self.blackboard.lock:
            current_time = time.time()
            
            for robot_id, robot_info in self.blackboard.robots.items():
                if robot_info.status == RobotStatus.COLLISION_AVOIDANCE:
                    last_update = robot_info.last_update.timestamp()
                    
                    if current_time - last_update > 3.0:
                        print(f"PA: Replanning path for stuck robot {robot_id}")
                        
                        if robot_info.current_task:
                            box = self.blackboard.boxes.get(robot_info.current_task)
                            if box:
                                new_path = self._find_alternative_path(
                                    robot_info.x, robot_info.y, box.x, box.y, robot_id
                                )
                                robot_info.path = new_path
                                self.blackboard.update_robot_status(robot_id, RobotStatus.MOVING)
    
    def _find_alternative_path(self, start_x: float, start_y: float, 
                               end_x: float, end_y: float, robot_id: int) -> List[Tuple[float, float]]:
        waypoints = []
        num_waypoints = 5
        
        for i in range(num_waypoints):
            t = (i + 1) / (num_waypoints + 1)
            
            base_x = start_x + (end_x - start_x) * t
            base_y = start_y + (end_y - start_y) * t
            
            offset_angle = (i * math.pi / 3)
            offset_dist = 3.0
            
            waypoint_x = base_x + offset_dist * math.cos(offset_angle)
            waypoint_y = base_y + offset_dist * math.sin(offset_angle)
            
            waypoints.append((waypoint_x, waypoint_y))
        
        waypoints.append((end_x, end_y))
        return waypoints
    
    def _prioritize_tasks(self):
        with self.blackboard.lock:
            available_boxes = self.blackboard.get_available_boxes()
            
            for box in available_boxes:
                age = time.time() - box.id
                if age > 10:
                    box.priority = min(box.priority + 1, 10)

class CommunicationAgent(KnowledgeAgent):
    def __init__(self, blackboard: Blackboard, broadcast_interval: float = 1.0):
        super().__init__(blackboard)
        self.broadcast_interval = broadcast_interval
        self.message_queue = []
    
    def run(self):
        while self.active:
            self._broadcast_status()
            self._process_messages()
            time.sleep(self.broadcast_interval)
    
    def _broadcast_status(self):
        state = self.blackboard.get_system_state()
        
        active_robots = len([r for r in state['robots'].values() 
                           if r['status'] != 'idle'])
        pending_boxes = len([b for b in state['boxes'].values() 
                           if not b['picked']])
        
        if active_robots > 0 or pending_boxes > 0:
            print(f"CA: System Status - Active Robots: {active_robots}, "
                  f"Pending Boxes: {pending_boxes}, "
                  f"Completed Tasks: {len(state['completed_tasks'])}")
    
    def _process_messages(self):
        while self.message_queue:
            message = self.message_queue.pop(0)
            self._handle_message(message)
    
    def _handle_message(self, message: dict):
        msg_type = message.get('type')
        
        if msg_type == 'emergency_stop':
            with self.blackboard.lock:
                for robot_id in self.blackboard.robots:
                    self.blackboard.update_robot_status(robot_id, RobotStatus.IDLE)
        
        elif msg_type == 'priority_task':
            box_id = message.get('box_id')
            if box_id and box_id in self.blackboard.boxes:
                self.blackboard.boxes[box_id].priority = 10
    
    def send_message(self, message: dict):
        self.message_queue.append(message)