#!/usr/bin/env python3
import requests
import time
import json
from datetime import datetime

BASE_URL = "http://localhost:5001"

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def test_initial_positions():
    print_section("POSICIONES INICIALES")
    
    # Obtener posiciones iniciales de cajas
    response = requests.get(f"{BASE_URL}/initial/boxes")
    if response.status_code == 200:
        data = response.json()
        print(f"\n✓ Cajas creadas: {data['total']}")
        for box in data['boxes']:
            print(f"  - Caja {box['id']}: pos({box['x']:.1f}, {box['y']:.1f}) prioridad={box['priority']}")
    
    # Obtener posiciones iniciales de robots
    response = requests.get(f"{BASE_URL}/initial/robots")
    if response.status_code == 200:
        data = response.json()
        print(f"\n✓ Robots creados: {data['total']}")
        for robot in data['robots']:
            print(f"  - Robot {robot['id']}: pos({robot['x']}, {robot['y']}) estado={robot['status']}")

def test_blackboard_status():
    print_section("ESTADO DEL BLACKBOARD")
    
    response = requests.get(f"{BASE_URL}/blackboard/status")
    if response.status_code == 200:
        data = response.json()
        print(f"\n✓ Robots registrados: {len(data['robots'])}")
        print(f"✓ Cajas registradas: {len(data['boxes'])}")
        print(f"✓ Asignaciones activas: {len(data['active_assignments'])}")
        print(f"✓ Tareas completadas: {len(data['completed_tasks'])}")
        print(f"✓ Zonas de colisión activas: {data['collision_zones']}")

def test_movement_simulation():
    print_section("SIMULACIÓN DE MOVIMIENTOS")
    
    print("\nEjecutando 10 pasos de simulación...")
    for step in range(10):
        response = requests.get(f"{BASE_URL}/movement/next")
        if response.status_code == 200:
            data = response.json()
            print(f"\n--- Paso {step + 1} ---")
            for movement in data['movements']:
                robot_id = movement['robot_id']
                from_pos = movement['from']
                to_pos = movement['to']
                status = movement['status']
                task = movement['current_task']
                
                moved = abs(from_pos['x'] - to_pos['x']) > 0.01 or abs(from_pos['y'] - to_pos['y']) > 0.01
                
                if moved:
                    print(f"  Robot {robot_id}: ({from_pos['x']:.1f},{from_pos['y']:.1f}) → ({to_pos['x']:.1f},{to_pos['y']:.1f}) [{status}]", end="")
                    if task:
                        print(f" Tarea: {task}")
                    else:
                        print()
        
        time.sleep(0.5)

def test_blackboard_decisions():
    print_section("DECISIONES DEL BLACKBOARD")
    
    response = requests.get(f"{BASE_URL}/blackboard/decisions")
    if response.status_code == 200:
        data = response.json()
        
        print("\n✓ Asignaciones de tareas:")
        if data['task_assignments']:
            for robot_id, assignment in data['task_assignments'].items():
                print(f"  - Robot {robot_id}: asignado a caja en {assignment['box_position']}")
        else:
            print("  - No hay asignaciones activas")
        
        print("\n✓ Robots evitando colisiones:")
        if data['collision_avoidance']:
            for robot in data['collision_avoidance']:
                print(f"  - Robot {robot['robot_id']} en posición {robot['position']}")
        else:
            print("  - No hay robots evitando colisiones")
        
        print("\n✓ Planificación de rutas:")
        if data['path_planning']:
            for robot_id, path_info in data['path_planning'].items():
                print(f"  - Robot {robot_id}: {len(path_info['planned_path'])} puntos en ruta")
        else:
            print("  - No hay rutas planificadas")
        
        print(f"\n✓ Tareas completadas: {data['completed_tasks']}")
        print(f"✓ Zonas de colisión activas: {data['active_collision_zones']}")
        
        print("\n✓ Últimos mensajes del log:")
        for msg in data['message_log'][-5:]:
            print(f"  [{msg['type']}] {msg['message']}")

def test_performance():
    print_section("MÉTRICAS DE RENDIMIENTO")
    
    response = requests.get(f"{BASE_URL}/blackboard/performance")
    if response.status_code == 200:
        data = response.json()
        
        system = data['system_state']
        metrics = data['performance_metrics']
        
        print("\n✓ Estado del sistema:")
        print(f"  - Robots totales: {system['total_robots']}")
        print(f"  - Robots activos: {system['active_robots']}")
        print(f"  - Cajas totales: {system['total_boxes']}")
        print(f"  - Cajas pendientes: {system['pending_boxes']}")
        print(f"  - Tareas completadas: {system['completed_tasks']}")
        
        print("\n✓ Métricas de rendimiento:")
        print(f"  - Tareas completadas: {metrics['tasks_completed']}")
        print(f"  - Colisiones evitadas: {metrics['collisions_avoided']}")
        print(f"  - Distancia total: {metrics['total_distance']:.1f}")
        print(f"  - Tiempo promedio de completado: {metrics['average_completion_time']:.2f}s")

def monitor_realtime():
    print_section("MONITOREO EN TIEMPO REAL")
    print("\nPresiona Ctrl+C para detener el monitoreo\n")
    
    try:
        step_count = 0
        while True:
            response = requests.get(f"{BASE_URL}/simulation/step")
            if response.status_code == 200:
                data = response.json()
                
                # Contar robots y cajas
                robots = [a for a in data['agents'] if a['type'] == 'robot']
                boxes = [a for a in data['agents'] if a['type'] == 'caja']
                picked_boxes = sum(1 for b in boxes if b['picked'])
                
                # Estado del blackboard
                bb_state = data['blackboard']
                active_tasks = len(bb_state['active_assignments'])
                completed = len(bb_state['completed_tasks'])
                
                print(f"\r[Paso {step_count:3d}] " +
                      f"Robots: {len(robots)} | " +
                      f"Cajas: {picked_boxes}/{len(boxes)} recogidas | " +
                      f"Tareas activas: {active_tasks} | " +
                      f"Completadas: {completed}", end="")
                
                step_count += 1
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        print("\n\nMonitoreo detenido")

def main():
    print("="*60)
    print(" PRUEBA DEL SISTEMA BLACKBOARD")
    print("="*60)
    print(f"\nConectando a {BASE_URL}...")
    
    try:
        # Verificar conexión
        response = requests.get(f"{BASE_URL}/blackboard/status", timeout=2)
        if response.status_code == 200:
            print("✓ Servidor conectado exitosamente")
        else:
            print("✗ Error al conectar con el servidor")
            return
    except requests.exceptions.RequestException as e:
        print(f"✗ No se pudo conectar al servidor: {e}")
        print("\nAsegúrate de que el servidor esté corriendo:")
        print("  python main.py")
        return
    
    # Ejecutar pruebas
    test_initial_positions()
    time.sleep(1)
    
    test_blackboard_status()
    time.sleep(1)
    
    test_blackboard_decisions()
    time.sleep(1)
    
    test_movement_simulation()
    time.sleep(1)
    
    test_performance()
    time.sleep(1)
    
    # Preguntar si quiere monitoreo en tiempo real
    print("\n" + "="*60)
    response = input("\n¿Desea iniciar el monitoreo en tiempo real? (s/n): ")
    if response.lower() == 's':
        monitor_realtime()
    
    print("\n✓ Pruebas completadas")

if __name__ == "__main__":
    main()