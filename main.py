import socket, json, agentpy as ap
import random
from flask import Flask, jsonify
import math
from blackboard import Blackboard, RobotStatus
from controller_agent import ControllerAgent
import threading

app = Flask(__name__)

blackboard = Blackboard()
controller = None

class Caja(ap.Agent):
    def setup(self):
        self.x = random.randint(0,50)
        self.y = random.randint(0,50)
        self.picked = False
        self.box_id = id(self)
        blackboard.register_box(self.box_id, self.x, self.y, priority=random.randint(0, 5))

class Robot(ap.Agent):
    def setup(self):
        self.x = random.randint(0,50)
        self.y = random.randint(0,50)
        self.v = 1
        self.target = None
        self.robot_id = id(self)
        self.current_path = []
        self.path_index = 0
        blackboard.register_robot(self.robot_id, self.x, self.y, self.v)
        
    def update_from_blackboard(self):
        with blackboard.lock:
            robot_info = blackboard.robots.get(self.robot_id)
            if robot_info:
                if robot_info.current_task and not self.target:
                    box_info = blackboard.boxes.get(robot_info.current_task)
                    if box_info:
                        self.target = (box_info.x, box_info.y)
                        self.current_path = blackboard.get_safe_path(self.robot_id, box_info.x, box_info.y)
                        self.path_index = 0
                
                if robot_info.status == RobotStatus.IDLE:
                    self.target = None
                    self.current_path = []
    
    def move_with_blackboard(self):
        blackboard.update_robot_position(self.robot_id, self.x, self.y)
        
        if self.current_path and self.path_index < len(self.current_path):
            next_point = self.current_path[self.path_index]
            dx = next_point[0] - self.x
            dy = next_point[1] - self.y
            dist = math.sqrt(dx**2 + dy**2)
            
            if dist < 0.5:
                self.path_index += 1
                if self.path_index >= len(self.current_path):
                    if self.target:
                        robot_info = blackboard.robots.get(self.robot_id)
                        if robot_info and robot_info.current_task:
                            blackboard.complete_task(self.robot_id, robot_info.current_task)
                            box = next((b for b in self.model.cajas if id(b) == robot_info.current_task), None)
                            if box:
                                box.picked = True
                    self.target = None
                    self.current_path = []
            elif dist > 0:
                move_dist = min(self.v, dist)
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist
        
        elif self.target and not self.current_path:
            dx = self.target[0] - self.x
            dy = self.target[1] - self.y
            dist = math.sqrt(dx**2 + dy**2)
            
            if dist > self.v:
                self.x += self.v * dx / dist
                self.y += self.v * dy / dist
            else:
                self.x = self.target[0]
                self.y = self.target[1]
                self.target = None
        
    def set_mission(self, boxes : Caja):
        min_dist = float('inf')
        closest = None
        
        for box in boxes:
            if not getattr(box, "picked", False):
                distance = math.sqrt((self.x - box.x)**2 + (self.y - box.y)**2)
                if distance < min_dist:
                    min_dist = distance
                    closest = box
        
        if closest != None:
            self.target = (closest.x, closest.y)
            
    def move_to_mission(self):
        if self.target:
            dy = self.target[1] - self.y
            dx = self.target[0] - self.x
            dist = math.sqrt(((dx) ** 2 + (dy) ** 2))
            if dist > self.v:
                self.x += self.v * dx / dist
                self.y += self.v * dy / dist
            else:
                self.x = self.target[0]
                self.y = self.target[1]
                self.target = None            

class Modelo(ap.Model):
    def setup(self):
        self.cajas = ap.AgentList(self, 5, Caja)
        self.robots = ap.AgentList(self, 3, Robot)
        
        global controller
        controller = ControllerAgent(blackboard)
        controller.start()

    def step(self):
        for r in self.robots:
            r.update_from_blackboard()
            r.move_with_blackboard()

        return [{"id": id(c), "type":"caja", "x": c.x, "y": c.y, "picked": c.picked} for c in self.cajas] + \
               [{"id": id(r), "type":"robot", "x": r.x, "y": r.y} for r in self.robots]

model = Modelo()
model.setup()

print("\n=== POSICIONES INICIALES DE AGENTES ===")
print(f"\nTotal de cajas: {len(model.cajas)}")
for i, caja in enumerate(model.cajas):
    print(f"Caja {i+1}: x={caja.x}, y={caja.y}, picked={caja.picked}")

print(f"\nTotal de robots: {len(model.robots)}")
for i, robot in enumerate(model.robots):
    print(f"Robot {i+1}: x={robot.x}, y={robot.y}")
print("="*40)

@app.route("/robots")
def get_robot_data():
    robots_data = model.step()
    formatted_data = jsonify(robots_data)
    print(formatted_data)
    return formatted_data

@app.route("/agentes")
def get_all_agents():
    """Endpoint para ver todas las posiciones actuales de los agentes"""
    agents_data = {
        "cajas": [{"id": i+1, "x": c.x, "y": c.y, "picked": c.picked} for i, c in enumerate(model.cajas)],
        "robots": [{"id": i+1, "x": r.x, "y": r.y, "velocidad": r.v, "target": r.target} for i, r in enumerate(model.robots)]
    }
    return jsonify(agents_data)

@app.route("/blackboard/status")
def get_blackboard_status():
    """Endpoint para ver el estado del sistema blackboard"""
    state = blackboard.get_system_state()
    return jsonify(state)

@app.route("/blackboard/performance")
def get_performance():
    """Endpoint para ver las métricas de rendimiento"""
    if controller:
        report = controller.get_performance_report()
        return jsonify(report)
    return jsonify({"error": "Controller not initialized"}), 500

@app.route("/blackboard/emergency_stop", methods=["POST"])
def emergency_stop():
    """Endpoint para detener todos los robots en caso de emergencia"""
    if controller:
        controller.emergency_stop()
        return jsonify({"status": "Emergency stop activated"})
    return jsonify({"error": "Controller not initialized"}), 500

@app.route("/blackboard/resume", methods=["POST"])
def resume_operations():
    """Endpoint para reanudar las operaciones después de una parada"""
    if controller:
        controller.resume_operations()
        return jsonify({"status": "Operations resumed"})
    return jsonify({"error": "Controller not initialized"}), 500

@app.route("/posiciones")
def show_positions():
    """Endpoint para ver posiciones en formato texto"""
    output = "<h2>Posiciones Actuales de Agentes</h2>"
    output += "<h3>Cajas:</h3><ul>"
    for i, caja in enumerate(model.cajas):
        output += f"<li>Caja {i+1}: x={caja.x:.2f}, y={caja.y:.2f}, recogida={caja.picked}</li>"
    output += "</ul><h3>Robots:</h3><ul>"
    for i, robot in enumerate(model.robots):
        output += f"<li>Robot {i+1}: x={robot.x:.2f}, y={robot.y:.2f}, v={robot.v}</li>"
    output += "</ul>"
    return output

@app.route("/initial/boxes")
def get_initial_boxes():
    """Endpoint para obtener las posiciones iniciales de las cajas"""
    boxes_data = []
    for caja in model.cajas:
        box_id = id(caja)
        box_info = blackboard.boxes.get(box_id)
        boxes_data.append({
            "id": box_id,
            "x": caja.x,
            "y": caja.y,
            "priority": box_info.priority if box_info else 0,
            "picked": caja.picked
        })
    return jsonify({
        "event": "boxes_created",
        "total": len(boxes_data),
        "boxes": boxes_data
    })

@app.route("/initial/robots")
def get_initial_robots():
    """Endpoint para obtener las posiciones iniciales de los robots"""
    robots_data = []
    for robot in model.robots:
        robot_id = id(robot)
        robot_info = blackboard.robots.get(robot_id)
        robots_data.append({
            "id": robot_id,
            "x": robot.x,
            "y": robot.y,
            "velocity": robot.v,
            "status": robot_info.status.value if robot_info else "idle"
        })
    return jsonify({
        "event": "robots_created",
        "total": len(robots_data),
        "robots": robots_data
    })

@app.route("/movement/next")
def get_next_movement():
    """Endpoint para obtener el siguiente movimiento de los robots"""
    movements = []
    
    for robot in model.robots:
        robot.update_from_blackboard()
        old_x, old_y = robot.x, robot.y
        robot.move_with_blackboard()
        
        robot_id = id(robot)
        robot_info = blackboard.robots.get(robot_id)
        
        movement_data = {
            "robot_id": robot_id,
            "from": {"x": old_x, "y": old_y},
            "to": {"x": robot.x, "y": robot.y},
            "status": robot_info.status.value if robot_info else "idle",
            "target": robot.target,
            "current_task": robot_info.current_task if robot_info else None,
            "path": robot.current_path,
            "path_index": robot.path_index
        }
        movements.append(movement_data)
    
    return jsonify({
        "event": "robot_movements",
        "movements": movements,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/blackboard/decisions")
def get_blackboard_decisions():
    """Endpoint para ver las decisiones tomadas por el sistema blackboard"""
    decisions = {
        "task_assignments": {},
        "collision_avoidance": [],
        "path_planning": {},
        "message_log": blackboard.message_log[-10:]
    }
    
    for robot_id, box_id in blackboard.task_assignments.items():
        robot_info = blackboard.robots.get(robot_id)
        box_info = blackboard.boxes.get(box_id)
        if robot_info and box_info:
            decisions["task_assignments"][robot_id] = {
                "robot_position": (robot_info.x, robot_info.y),
                "box_position": (box_info.x, box_info.y),
                "box_priority": box_info.priority,
                "status": robot_info.status.value
            }
    
    for robot_id, robot_info in blackboard.robots.items():
        if robot_info.status == RobotStatus.COLLISION_AVOIDANCE:
            decisions["collision_avoidance"].append({
                "robot_id": robot_id,
                "position": (robot_info.x, robot_info.y)
            })
        
        if robot_info.path:
            decisions["path_planning"][robot_id] = {
                "current_position": (robot_info.x, robot_info.y),
                "planned_path": robot_info.path,
                "target_task": robot_info.current_task
            }
    
    decisions["completed_tasks"] = len(blackboard.completed_tasks)
    decisions["active_collision_zones"] = len(blackboard.collision_zones)
    
    return jsonify(decisions)

@app.route("/simulation/step")
def simulation_step():
    """Ejecuta un paso de la simulación y devuelve el estado completo"""
    step_data = model.step()
    
    blackboard_state = blackboard.get_system_state()
    
    return jsonify({
        "agents": step_data,
        "blackboard": blackboard_state,
        "timestamp": datetime.now().isoformat()
    })

from datetime import datetime

if __name__ == "__main__":
    app.run(debug=True, port=5001)