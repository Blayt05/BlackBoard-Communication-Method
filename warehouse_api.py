import random
import agentpy as ap
from fastapi import FastAPI, Request, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import time

# ------------------------
# Blackboard para tareas
# ------------------------
class BlackBoard:
    def __init__(self, model):
        self.model = model
        self.tasks = []
        self.assignments = {}  # box_id -> agent_id

    def add_task(self, obj_id, start, target, min_dist=0.5):
        # Asegurarnos de que target esté a una distancia mínima de start
        def dist(a, b):
            return ((a[0]-b[0])**2 + (a[2]-b[2])**2) ** 0.5

        # Si target está muy cerca, muestreamos otro target hasta cumplir min_dist
        attempts = 0
        while dist(start, target) < min_dist and attempts < 20:
            target = [random.uniform(-20, 20), start[1], random.uniform(-20, 20)]
            attempts += 1

        self.tasks.append({
            "obj_id": obj_id,
            "start": start,
            "target": target,
            "done": False
        })

    def get_task(self, agent_id):
        for task in self.tasks:
            if not task["done"] and task["obj_id"] not in self.assignments:
                self.assignments[task["obj_id"]] = agent_id
                return task
        return None

    def complete_task_for_box(self, box_id):
        for task in self.tasks:
            if task["obj_id"] == box_id:
                task["done"] = True
                if box_id in self.assignments:
                    del self.assignments[box_id]
                return True
        return False

    def assign_task_to_agent(self, agent_id, box_id, target):
        """
        Forzar que box_id sea asignada a agent_id con target específico.
        Si existe una task para esa caja la actualiza; si no existe la crea.
        """
        # Buscar task de esa caja
        for task in self.tasks:
            if task["obj_id"] == box_id:
                task["target"] = target
                task["done"] = False
                self.assignments[box_id] = agent_id
                return True

        # Si no existe, crear nueva task con start tomado del box actual
        box = next((b for b in self.model.boxes if b.id == box_id), None)
        start = box.pos if box is not None else [random.uniform(-20,20), 0.5, random.uniform(-20,20)]
        self.add_task(box_id, start, target)
        self.assignments[box_id] = agent_id
        return True


# ------------------------
# Modelo del warehouse
# ------------------------
class WorkerAgent(ap.Agent):
    def setup(self):
        # posición inicial (solo para spawn)
        self.pos = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
        self.task = None
        # ahora carrying y carrying_box serán controlados por Unity vía endpoints
        self.carrying = False
        self.carrying_box_id = None

    def step(self):
        bb = self.model.blackboard
        # Solo pedir tarea si no tiene
        if self.task is None:
            self.task = bb.get_task(self.id)
        # NO mover posiciones aquí — Unity se encargará del movimiento visual

class Box(ap.Agent):
    def setup(self):
        self.pos = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
        self.target = None

    def step(self):
        pass  # movimiento visual en Unity

class WarehouseModel(ap.Model):
    def setup(self):
        self.blackboard = BlackBoard(self)

        # Crear agentes
        self.workers = ap.AgentList(self, self.p.agents, WorkerAgent)
        for w in self.workers:
            w.pos = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
        self.workers_dict = {ag.id: ag for ag in self.workers}

        # Crear cajas
        self.boxes = ap.AgentList(self, self.p.objects, Box)
        for i, box in enumerate(self.boxes):
            box.pos = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
            # target inicial
            box.target = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
            self.blackboard.add_task(box.id, box.pos, box.target)

    def step(self):
        self.workers.step()
        self.boxes.step()

        # Revisar tareas completadas para reiniciarlas
        for task in self.blackboard.tasks:
            if task["done"]:
                # Generar un nuevo destino random con distancia mínima
                min_dist = 1.0
                new_target = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
                # evitar que sea casi igual al start
                def dist(a,b): return ((a[0]-b[0])**2 + (a[2]-b[2])**2)**0.5
                attempts = 0
                while dist(task["target"], new_target) < min_dist and attempts < 30:
                    new_target = [random.uniform(-20, 20), 0.5, random.uniform(-20, 20)]
                    attempts += 1

                task["start"] = task["target"]
                task["target"] = new_target
                task["done"] = False

                # Liberar asignación si existe
                if task["obj_id"] in self.blackboard.assignments:
                    del self.blackboard.assignments[task["obj_id"]]

                # Actualizar target de la caja en el modelo
                box = next(b for b in self.boxes if b.id == task["obj_id"])
                box.target = new_target


# ------------------------
# FastAPI
# ------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

parameters = {
    "agents": 11,
    "objects": 30,
    "steps": 100,
}
model = WarehouseModel(parameters)
model.setup()

# Endpoint que Unity consulta cada tick
@app.get("/coords")
def get_coords():
    model.step()
    objects = []
    # Para cada agente: enviar destino (donde Unity debe mover al NavMeshAgent)
    for ag in model.workers:
        dest = {"x": ag.pos[0], "y": ag.pos[1], "z": ag.pos[2]}  # fallback: stay
        if ag.task is not None:
            # si el agente está cargando, destino = task target
            if getattr(ag, "carrying", False):
                dest = {"x": ag.task["target"][0], "y": ag.task["target"][1], "z": ag.task["target"][2]}
            else:
                # si no carga aún, su destino es la posición actual de la caja a recoger
                box = next((b for b in model.boxes if b.id == ag.task["obj_id"]), None)
                if box:
                    dest = {"x": box.pos[0], "y": box.pos[1], "z": box.pos[2]}
        objects.append({
            "id": f"Agent{ag.id}",
            "position": dest,
            "speed": 1.0,
        })

    # Para cajas: enviar su posición inicial (y permitir que Unity luego maneje movimiento visual).
    # Además, si la caja fue actualizada por Unity en /drop, box.pos habrá cambiado.
    for box in model.boxes:
        objects.append({
            "id": f"Box{box.id}",
            "position": {"x": box.pos[0], "y": box.pos[1], "z": box.pos[2]},
            "speed": 0.5,
        })

    return {"timestamp": int(time.time()), "objects": objects}

# Endpoint que Unity llama cuando un agente recoge una caja
@app.post("/pickup")
async def pickup(req: Request):
    data = await req.json()
    print("RECIBIDO /pickup:", data)
    agent_id_str = data.get("agent")  # "Agent0"
    box_id_str = data.get("box")      # "Box1"
    if agent_id_str is None or box_id_str is None:
        return {"ok": False, "error": "missing agent or box"}

    aid = int(agent_id_str.replace("Agent", ""))
    bid = int(box_id_str.replace("Box", ""))

    # marcar en el modelo que el agent está cargando esa caja
    ag = model.workers_dict.get(aid)
    if ag:
        ag.carrying = True
        ag.carrying_box_id = bid
    # establecer la asignación si no estaba
    model.blackboard.assignments[bid] = aid

    return {"ok": True}

# Endpoint que Unity llama cuando suelta la caja (drop) - incluye la posición final
@app.post("/drop")
async def drop(req: Request):
    data = await req.json()
    print("RECIBIDO /drop:", data)
    agent_id_str = data.get("agent")
    box_id_str = data.get("box")
    pos = data.get("position")  # {x,y,z}

    if agent_id_str is None or box_id_str is None or pos is None:
        return {"ok": False, "error": "missing fields"}

    aid = int(agent_id_str.replace("Agent", ""))
    bid = int(box_id_str.replace("Box", ""))

    # actualizar el modelo de python: caja en nueva posición
    box = next((b for b in model.boxes if b.id == bid), None)
    if box:
        box.pos = [pos["x"], pos["y"], pos["z"]]

    # marcar la tarea asociada como completada y liberar asignación
    model.blackboard.complete_task_for_box(bid)

    # marcar que el agente ya no carga
    ag = model.workers_dict.get(aid)
    if ag:
        ag.carrying = False
        ag.carrying_box_id = None

    print(f"Box {bid} actualizado a pos {box.pos}, tarea marcada done")
    return {"ok": True}

@app.post("/assign")
async def assign_task(body: dict = Body(...)):
    agent_str = body.get("agent")
    box_str = body.get("box")
    pos = body.get("target")
    if not agent_str or not box_str or not pos:
        return {"ok": False, "error": "missing fields"}

    try:
        aid = int(agent_str.replace("Agent", ""))
        bid = int(box_str.replace("Box", ""))
    except:
        return {"ok": False, "error": "bad id format"}

    # Validar existencia
    if aid not in model.workers_dict:
        return {"ok": False, "error": f"agent {agent_str} not found"}
    box = next((b for b in model.boxes if b.id == bid), None)
    if box is None:
        return {"ok": False, "error": f"box {box_str} not found"}

    target = [pos["x"], pos["y"], pos["z"]]
    model.blackboard.assign_task_to_agent(aid, bid, target)
    return {"ok": True, "assigned": {"agent": agent_str, "box": box_str, "target": target}}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
