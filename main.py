import socket, json, agentpy as ap
import random

class Caja(ap.Agent):
    def setup(self):
        self.x = random.uniform(0,10)
        self.y = random.uniform(0,10)

class Robot(ap.Agent):
    def setup(self):
        self.x = random.uniform(0,10)
        self.y = random.uniform(0,10)
        self.v = 0.5

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
