from flask import Flask, request, jsonify

app = Flask(__name__)

data = {
    "robots" : [],
    "boxes" : []
}

@app.route("/")
def hello_world():
    return "<p>Hello, world!<p>"

@app.route("/new_robot_coors", methods=["POST"])
def update_robot_coors():
    data = request.get_json()
    data["robots"] = data.get("robots", [])
    return jsonify({"status" : "robots updated"})

@app.route("/new_box_coors", methods=["POST"])
def update_robot_coors():
    data = request.get_json()
    data["boxes"] = data.get("boxes", [])
    return jsonify({"status" : "boxes updated"})

@app.route("/board_status", methods=["GET"])
def read_data():
    print(data)
    return jsonify(data)
    