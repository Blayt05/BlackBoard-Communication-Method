import socket, json, agentpy as ap
import random
from flask import Flask, jsonify
import math

app = Flask(__name__)

class Caja(ap.Agent):
    def setup(self):
        self.x = random.uniform(0,10)
        self.y = random.uniform(0,10)
        self.picked = False

class Robot(ap.Agent):
    def setup(self):
        self.x = random.uniform(0,10)
        self.y = random.uniform(0,10)
        self.v = 0.5
        self.target = None
        
    def set_mission(self, boxes : Caja):
        min_dist = float('inf')
        closest = None
        
        for box in boxes:
            if getattr(box, "picked", False):
                distance = math.sqrt((self.x - box.x)**2 + (self.y - box.y)**2)
                if distance < min_dist:
                    min_dist = distance
                    closest = box
        
        if closest != None:
            self.target = (closest.x, closest.y)
            closest = closest
            
    def move_to_mission(self):
        if self.target:
            dx = self.target.x - self.x
            dy = self.target.y - self.y
            dist = math.sqrt(((dx) ** 2 + (dy) ** 2))
            if dist > self.v:
                self.x = self.v * dx / dist
                self.y = self.v * dy / dist
            else:
                self.x = self.target.x
                self.y = self.target.y
                setattr(self.target, "picked", True)
                self.target = None            

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

model = Modelo()

app.route("/robots")
def get_robot_data():
    robots_data = model.step()
    formatted_data = jsonify(robots_data)
    print(formatted_data)
    return formatted_data