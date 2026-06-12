import os
import json
from flask import Flask, request, jsonify
from datetime import datetime
from functools import wraps
from flask_apscheduler import APScheduler

# Intentar importar psycopg2 de manera segura
try:
    import psycopg2
    import psycopg2.extras
    USAR_DB = True
except ImportError:
    USAR_DB = False

app = Flask(__name__)
scheduler = APScheduler()

# Configuración limpia de variables de entorno de Render
API_KEY = os.environ.get("API_KEY", "clave-practica-07")
APP_ENV = os.environ.get("APP_ENV", "production")

def get_db():
    if not USAR_DB:
        return None
    try:
        # CONEXIÓN INTERNA DIRECTA: Usa el host interno privado que me pasaste.
        # En la red interna de Render, el tráfico no va cifrado, por lo que sslmode debe ser 'disable'.
        return psycopg2.connect(
            host="dpg-d8lfqha8qa3s73e66dhg-a",
            database="flask_db_36tl",
            user="flask_user",
            password="VX1dWJ4Om4rgDdRYCTIKNFSmkZzcL5fL",
            sslmode="disable",
            connect_timeout=10
        )
    except Exception as e:
        print(f"Error de conexión directa interna a DB: {e}")
        return None

def init_db():
    conn = get_db()
    if not conn:
        print("No se pudo inicializar la DB porque no hay conexión activa temporalmente.")
        return False
    cur = conn.cursor()
    try:
        # 1. Crear tabla de materias si no existe
        cur.execute("""
        CREATE TABLE IF NOT EXISTS materias (
            id SERIAL PRIMARY KEY,
            clave VARCHAR(15) NOT NULL UNIQUE,
            nombre VARCHAR(150) NOT NULL,
            semestre INTEGER NOT NULL CHECK (semestre BETWEEN 1 AND 9),
            creditos INTEGER DEFAULT 5,
            tipo VARCHAR(30) DEFAULT 'Obligatoria',
            horas_teoria INTEGER DEFAULT 3,
            horas_practica INTEGER DEFAULT 2,
            competencia VARCHAR(200),
            activa BOOLEAN DEFAULT true,
            fecha_registro TIMESTAMP DEFAULT NOW()
        );
        """)
        
        # 2. Crear tabla de reportes si no existe
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reportes (
            id SERIAL PRIMARY KEY,
            tipo VARCHAR(50),
            datos JSONB,
            fecha TIMESTAMP DEFAULT NOW()
        );
        """)
        
        # 3. Inyectar catálogo completo de Ingeniería en Informática evitando duplicados
        materias_iniciales = [
            ('INF-101', 'Fundamentos de Programacion', 1, 6, 'Obligatoria', 3, 3, 'Desarrollo de software'),
            ('INF-102', 'Matematicas Discretas', 1, 5, 'Obligatoria', 4, 1, 'Logica computacional'),
            ('INF-201', 'Estructura de Datos', 2, 6, 'Obligatoria', 3, 3, 'Desarrollo de software'),
            ('INF-202', 'Arquitectura de Computadoras', 2, 5, 'Obligatoria', 4, 1, 'Hardware y redes'),
            ('INF-301', 'Bases de Datos', 3, 6, 'Obligatoria', 3, 3, 'Gestion de datos'),
            ('INF-302', 'Redes de Computadoras', 3, 5, 'Obligatoria', 3, 2, 'Hardware y redes'),
            ('INF-401', 'Ingenieria de Software', 4, 6, 'Obligatoria', 3, 3, 'Desarrollo de software'),
            ('INF-402', 'Sistemas Operativos', 4, 5, 'Obligatoria', 3, 2, 'Infraestructura')
        ]
        
        for m in materias_iniciales:
            cur.execute("""
            INSERT INTO materias (clave, nombre, semestre, creditos, tipo, horas_teoria, horas_practica, competencia)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (clave) DO NOTHING;
            """, m)
            
        conn.commit()
        print("¡Base de datos sincronizada y protegida exitosamente!")
        return True
    except Exception as e:
        print(f"Error cargando los datos iniciales: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def tarea_cron_reporte():
    conn = get_db()
    if not conn:
        print("Cron Job: DB no disponible.")
        return
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM materias WHERE activa = true")
        total = cur.fetchone()["total"]
        
        cur.execute("SELECT semestre, COUNT(*) as cantidad FROM materias WHERE activa = true GROUP BY semestre")
        por_semestre = cur.fetchall()
        
        datos_reporte = {
            "total_materias": total,
            "distribucion_semestre": por_semestre,
            "ejecutado_por": "Cron Job Interno Gratuito",
            "timestamp": datetime.now().isoformat()
        }
        
        cur.execute("INSERT INTO reportes (tipo, datos) VALUES (%s, %s);", 
                    ("estadisticas_automaticas", json.dumps(datos_reporte)))
        conn.commit()
        print(f"[{datetime.now()}] Reporte estadístico Cron generado.")
    except Exception as e:
        print(f"Error en tarea Cron: {e}")
    finally:
        cur.close()
        conn.close()

def requiere_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return jsonify({
                "error": "API Key invalida",
                "instruccion": "Incluye X-API-Key en tus headers"
            }), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index():
    init_db()
    return jsonify({
        "msg": "API REST: Catalogo de Materias funcionando",
        "ambiente": APP_ENV,
        "cron_status": "Programador automatico interno activo"
    })

@app.route("/api/materias", methods=["GET"])
def listar_materias():
    init_db()
    conn = get_db()
    if not conn:
        return jsonify({"error": "Base de datos no disponible temporalmente"}), 503
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    semestre = request.args.get("semestre")
    tipo = request.args.get("tipo")
    competencia = request.args.get("competencia")
    
    query = "SELECT * FROM materias WHERE activa = true"
    params = []
    
    if semestre:
        query += " AND semestre = %s"
        params.append(int(semestre))
        
    if tipo:
        query += " AND tipo ILIKE %s"
        params.append(f"{tipo}")
        
    if competencia:
        query += " AND competencia ILIKE %s"
        params.append(f"%{competencia}%")
        
    query += " ORDER BY semestre, clave"
    cur.execute(query, params)
    materias = cur.fetchall()
    cur.close()
    conn.close()
    
    for m in materias:
        if m.get("fecha_registro"):
            m["fecha_registro"] = m["fecha_registro"].isoformat()
            
    return jsonify({"total": len(materias), "materias": materias})

@app.route("/api/materias", methods=["POST"])
@requiere_api_key
def crear_materia():
    conn = get_db()
    if not conn:
        return jsonify({"error": "DB no disponible"}), 503
    data = request.get_json()
    if not data or not all(k in data for k in ["clave", "nombre", "semestre"]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400
        
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
        INSERT INTO materias (clave, nombre, semestre, creditos, tipo, horas_teoria, horas_practica, competencia)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *;
        """, (data["clave"], data["nombre"], data["semestre"], data.get("creditos", 5),
              data.get("tipo", "Obligatoria"), data.get("horas_teoria", 3), data.get("horas_practica", 2), data.get("competencia", "")))
        nueva = cur.fetchone()
        conn.commit()
        if nueva and nueva.get("fecha_registro"):
            nueva["fecha_registro"] = nueva["fecha_registro"].isoformat()
        return jsonify({"mensaje": "Materia creada", "materia": nueva}), 201
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "La clave ya existe"}), 409
    finally:
        cur.close()
        conn.close()

@app.route("/api/estadisticas", methods=["GET"])
def obtener_estadisticas():
    init_db()
    conn = get_db()
    if not conn:
        return jsonify({"error": "Base de datos no disponible temporalmente"}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM materias WHERE activa = true")
        total = cur.fetchone()["total"]
        
        cur.execute("SELECT semestre, COUNT(*) as cantidad FROM materias WHERE activa = true GROUP BY semestre ORDER BY semestre")
        por_semestre = cur.fetchall()
        
        cur.execute("SELECT tipo, COUNT(*) as cantidad FROM materias WHERE activa = true GROUP BY tipo")
        por_tipo = cur.fetchall()
        
        return jsonify({
            "total_materias": total,
            "distribucion_semestre": por_semestre,
            "distribucion_tipo": por_tipo,
            "fecha_calculo": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": f"Error calculando estadisticas: {e}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/api/status")
def status():
    conn = get_db()
    db_ok = False
    if conn:
        db_ok = True
        conn.close()
    return jsonify({
        "status": "ok",
        "base_datos": "Conectada" if db_ok else "Desconectada"
    })

if __name__ == "__main__":
    app.config['SCHEDULER_API_ENABLED'] = False
    scheduler.init_app(app)
    scheduler.add_job(id='cron_interno', func=tarea_cron_reporte, trigger='interval', hours=1)
    scheduler.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
