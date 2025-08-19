import socket, json, agentpy as ap
import random

class Caja(ap.Agent):
    def setup(self):
        self.x = random.uniform(0,50)
        self.y = random.uniform(0,50)

class Robot(ap.Agent):
    def setup(self):
        self.x = self.model.random.randint(0, 49)
        self.y = self.model.random.randint(0, 49)
        self.target = None  # destino final (x, y)

    def set_target(self, tx, ty):
        self.target = (tx, ty)

    def move_step(self, occupied_positions):
        if not self.target:
            return  # no hay destino

        tx, ty = self.target

        # Paso en Y primero
        if self.y < ty:
            new_pos = (self.x, self.y+1)
        elif self.y > ty:
            new_pos = (self.x, self.y-1)
        # Luego X
        elif self.x < tx:
            new_pos = (self.x+1, self.y)
        elif self.x > tx:
            new_pos = (self.x-1, self.y)
        else:
            return  # ya está en destino

        # Verificar si está libre
        if new_pos not in occupied_positions:
            self.x, self.y = new_pos
        # Si está ocupado, el robot se queda quieto (aquí podrías implementar A*)


class Modelo(ap.Model):
    def setup(self):
        self.cajas = ap.AgentList(self, 3, Caja)
        self.robots = ap.AgentList(self, 1, Robot)

    def step(self):
        for r in self.robots:
            r.x += random.uniform(-r.v, r.v)
            r.y += random.uniform(-r.v, r.v)

        return [{"id": id(c), "type":"caja", "x": c.x, "y": c.y} for c in self.cajas] + \
               [{"id": id(r), "type":"robot", "x": r.x, "y": r.y} for r in self.robots]

# Servidor
HOST, PORT = "127.0.0.1", 65432
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST, PORT))
s.listen(1)
conn, addr = s.accept()

model = Modelo()
while True:
    data = model.step()
    conn.sendall(json.dumps(data).encode())
