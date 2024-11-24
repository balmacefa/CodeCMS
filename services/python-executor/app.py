from flask import Flask, request, jsonify
import os

app = Flask(__name__)

routes = {}

@app.route('/register-route', methods=['POST'])
def register_route():
    data = request.json
    route = data['route']
    code = data['code']

    routes[route] = code
    return jsonify({"message": f"Ruta {route} registrada correctamente."})

@app.route('/<path:path>', methods=['GET', 'POST'])
def execute_route(path):
    route = f"/{path}"
    if route not in routes:
        return jsonify({"error": "Ruta no encontrada"}), 404

    code = routes[route]
    exec_globals = {}
    try:
        exec(code, exec_globals)
        result = exec_globals.get("result", "Código ejecutado sin error.")
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
