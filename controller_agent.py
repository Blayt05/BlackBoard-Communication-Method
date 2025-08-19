import threading
import time
from typing import List, Dict, Any
from blackboard import Blackboard, RobotStatus
from knowledge_agents import (
    SearchKnowledgeAgent, 
    BlackboardReaderAgent, 
    PlanningAgent,
    CommunicationAgent
)

class ControllerAgent:
    def __init__(self, blackboard: Blackboard):
        self.blackboard = blackboard
        self.knowledge_agents = []
        self.active = False
        self.control_thread = None
        self.performance_metrics = {
            'tasks_completed': 0,
            'collisions_avoided': 0,
            'total_distance': 0.0,
            'average_completion_time': 0.0
        }
        self.task_start_times = {}
        
        self._initialize_knowledge_agents()
    
    def _initialize_knowledge_agents(self):
        self.search_agent = SearchKnowledgeAgent(self.blackboard, search_interval=1.0)
        self.reader_agent = BlackboardReaderAgent(self.blackboard, monitoring_interval=0.5)
        self.planning_agent = PlanningAgent(self.blackboard, planning_interval=2.0)
        self.comm_agent = CommunicationAgent(self.blackboard, broadcast_interval=1.0)
        
        self.knowledge_agents = [
            self.search_agent,
            self.reader_agent,
            self.planning_agent,
            self.comm_agent
        ]
    
    def start(self):
        self.active = True
        
        for agent in self.knowledge_agents:
            agent.start()
            print(f"CA: Started {agent.__class__.__name__}")
        
        self.control_thread = threading.Thread(target=self._control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        
        print("CA: Controller Agent started successfully")
    
    def stop(self):
        self.active = False
        
        for agent in self.knowledge_agents:
            agent.stop()
            print(f"CA: Stopped {agent.__class__.__name__}")
        
        if self.control_thread:
            self.control_thread.join()
        
        print("CA: Controller Agent stopped")
    
    def _control_loop(self):
        while self.active:
            self._monitor_system_health()
            self._coordinate_agents()
            self._update_metrics()
            self._handle_emergencies()
            time.sleep(0.5)
    
    def _monitor_system_health(self):
        state = self.blackboard.get_system_state()
        
        stuck_robots = []
        for robot_id, robot_data in state['robots'].items():
            if robot_data['status'] == 'collision_avoidance':
                stuck_robots.append(robot_id)
        
        if len(stuck_robots) > len(state['robots']) * 0.5:
            print(f"CA: WARNING - {len(stuck_robots)} robots in collision avoidance mode")
            self._resolve_deadlock(stuck_robots)
    
    def _coordinate_agents(self):
        state = self.blackboard.get_system_state()
        
        total_boxes = len(state['boxes'])
        completed = len(state['completed_tasks'])
        
        if total_boxes > 0:
            completion_rate = completed / total_boxes
            
            if completion_rate < 0.3 and len(state['active_assignments']) == 0:
                self.search_agent.optimize_assignments()
        
        for robot_id, robot_data in state['robots'].items():
            if robot_data['current_task'] and robot_id not in self.task_start_times:
                self.task_start_times[robot_id] = time.time()
    
    def _update_metrics(self):
        state = self.blackboard.get_system_state()
        
        self.performance_metrics['tasks_completed'] = len(state['completed_tasks'])
        
        collision_avoidance_count = sum(
            1 for r in state['robots'].values() 
            if r['status'] == 'collision_avoidance'
        )
        self.performance_metrics['collisions_avoided'] += collision_avoidance_count
        
        if state['completed_tasks']:
            completion_times = []
            for robot_id in self.task_start_times:
                if robot_id not in state['active_assignments']:
                    if robot_id in self.task_start_times:
                        completion_time = time.time() - self.task_start_times[robot_id]
                        completion_times.append(completion_time)
            
            if completion_times:
                self.performance_metrics['average_completion_time'] = \
                    sum(completion_times) / len(completion_times)
    
    def _handle_emergencies(self):
        state = self.blackboard.get_system_state()
        
        for robot_id, robot_data in state['robots'].items():
            last_update = robot_data.get('last_update')
            if last_update:
                from datetime import datetime
                last_update_time = datetime.fromisoformat(last_update)
                time_since_update = (datetime.now() - last_update_time).total_seconds()
                
                if time_since_update > 30:
                    print(f"CA: Emergency - Robot {robot_id} not responding")
                    self._handle_unresponsive_robot(robot_id)
    
    def _resolve_deadlock(self, stuck_robots: List[int]):
        print(f"CA: Resolving deadlock for robots {stuck_robots}")
        
        for i, robot_id in enumerate(stuck_robots):
            if i % 2 == 0:
                self.blackboard.update_robot_status(robot_id, RobotStatus.IDLE)
                time.sleep(0.1)
            else:
                with self.blackboard.lock:
                    if robot_id in self.blackboard.robots:
                        robot = self.blackboard.robots[robot_id]
                        robot.x += 2.0
                        robot.y += 2.0
        
        for robot_id in stuck_robots:
            self.blackboard.update_robot_status(robot_id, RobotStatus.MOVING)
    
    def _handle_unresponsive_robot(self, robot_id: int):
        with self.blackboard.lock:
            if robot_id in self.blackboard.robots:
                robot = self.blackboard.robots[robot_id]
                
                if robot.current_task:
                    box_id = robot.current_task
                    if box_id in self.blackboard.boxes:
                        self.blackboard.boxes[box_id].assigned_to = None
                    
                    robot.current_task = None
                
                robot.status = RobotStatus.IDLE
                
                if robot_id in self.blackboard.task_assignments:
                    del self.blackboard.task_assignments[robot_id]
        
        print(f"CA: Reset unresponsive robot {robot_id}")
    
    def emergency_stop(self):
        print("CA: EMERGENCY STOP - Halting all robot operations")
        
        with self.blackboard.lock:
            for robot_id in self.blackboard.robots:
                self.blackboard.update_robot_status(robot_id, RobotStatus.IDLE)
        
        self.comm_agent.send_message({
            'type': 'emergency_stop',
            'timestamp': time.time()
        })
    
    def resume_operations(self):
        print("CA: Resuming normal operations")
        
        self.search_agent.optimize_assignments()
        
        with self.blackboard.lock:
            for robot_id, robot in self.blackboard.robots.items():
                if robot.current_task:
                    self.blackboard.update_robot_status(robot_id, RobotStatus.MOVING)
    
    def get_performance_report(self) -> Dict[str, Any]:
        state = self.blackboard.get_system_state()
        
        return {
            'system_state': {
                'total_robots': len(state['robots']),
                'active_robots': len([r for r in state['robots'].values() 
                                    if r['status'] != 'idle']),
                'total_boxes': len(state['boxes']),
                'pending_boxes': len([b for b in state['boxes'].values() 
                                    if not b['picked']]),
                'completed_tasks': len(state['completed_tasks'])
            },
            'performance_metrics': self.performance_metrics,
            'collision_zones': state['collision_zones'],
            'message_log_size': len(self.blackboard.message_log)
        }
    
    def set_robot_speed(self, robot_id: int, speed: float):
        with self.blackboard.lock:
            if robot_id in self.blackboard.robots:
                self.blackboard.robots[robot_id].velocity = speed
                print(f"CA: Set robot {robot_id} speed to {speed}")
    
    def prioritize_box(self, box_id: int, priority: int):
        with self.blackboard.lock:
            if box_id in self.blackboard.boxes:
                self.blackboard.boxes[box_id].priority = priority
                print(f"CA: Set box {box_id} priority to {priority}")
                
                self.comm_agent.send_message({
                    'type': 'priority_task',
                    'box_id': box_id,
                    'priority': priority
                })