import os
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, render_template
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuración AEMET
# ---------------------------------------------------------------------------
AEMET_KEY = os.environ.get("AEMET_KEY", "")
if not AEMET_KEY:
    print("⚠️  AEMET_KEY no definida. Crea un .env con AEMET_KEY=tu_clave")

BASE = "https://opendata.aemet.es/opendata/api"

# Estaciones de la Sierra de Madrid (altitud >= 1000 m)
ESTACIONES = [
    {"id": "2462",  "nombre": "Puerto de Navacerrada", "altitud": 1892},
    {"id": "3266A", "nombre": "Puerto Alto del León",  "altitud": 1530},
    {"id": "3111D", "nombre": "Somosierra",            "altitud": 1454},
    {"id": "3104Y", "nombre": "Rascafría",             "altitud": 1159},
    {"id": "3110C", "nombre": "Buitrago del Lozoya",   "altitud": 1030},
]

# ---------------------------------------------------------------------------
# Configuración AEMET
# ---------------------------------------------------------------------------
AEMET_KEY = os.environ.get("AEMET_KEY", "")
if not AEMET_KEY:
    print("⚠️  AEMET_KEY no definida. Crea un .env con AEMET_KEY=tu_clave")

BASE = "https://opendata.aemet.es/opendata/api"

# Estaciones de la Sierra de Madrid (altitud >= 1000 m)
ESTACIONES = [
    {"id": "2462",  "nombre": "Puerto de Navacerrada", "altitud": 1892, "lat": 40.7808, "lon": -4.0103},
    {"id": "3266A", "nombre": "Puerto Alto del León",  "altitud": 1530, "lat": 40.6583, "lon": -4.1167},
    {"id": "3111D", "nombre": "Somosierra",            "altitud": 1454, "lat": 41.1333, "lon": -3.5833},
    {"id": "3104Y", "nombre": "Rascafría",             "altitud": 1159, "lat": 40.9000, "lon": -3.8833},
    {"id": "3110C", "nombre": "Buitrago del Lozoya",   "altitud": 1030, "lat": 40.9833, "lon": -3.6333},
]

# ---------------------------------------------------------------------------
# Caché simple en memoria (TTL 30 min)
# ---------------------------------------------------------------------------
CACHE_TTL = 30 * 60  # segundos
_cache = {}  # {clave: {"valor": ..., "expira": timestamp}}


def cache_get(clave):
    entrada = _cache.get(clave)
    if entrada and entrada["expira"] > time.time():
        return entrada["valor"]
    return None


def cache_set(clave, valor):
    _cache[clave] = {"valor": valor, "expira": time.time() + CACHE_TTL}
    
# ---------------------------------------------------------------------------
# Catálogo de especies y baremo continuo
# ---------------------------------------------------------------------------
ESPECIES = [
    {
        "nombre": "Boletus edulis (Calabaza)",
        "lluvia_ideal": 160, "lluvia_tol": 280,
        "temp_ideal": 15,    "temp_tol": 15,
        "meses_optimos": [9, 10, 11],
        "meses_limite": [8, 12],
    },
    {
        "nombre": "Lactarius deliciosus (Níscalo)",
        "lluvia_ideal": 120, "lluvia_tol": 240,
        "temp_ideal": 12,    "temp_tol": 12,
        "meses_optimos": [10, 11],
        "meses_limite": [9, 12, 1],
    },
    {
        "nombre": "Macrolepiota procera (Parasol)",
        "lluvia_ideal": 140, "lluvia_tol": 260,
        "temp_ideal": 18,    "temp_tol": 14,
        "meses_optimos": [9, 10],
        "meses_limite": [8, 11],
    },
    {
        "nombre": "Amanita caesarea (Oronja)",
        "lluvia_ideal": 180, "lluvia_tol": 280,
        "temp_ideal": 20,    "temp_tol": 12,
        "meses_optimos": [9, 10],
        "meses_limite": [8, 11],
    },
    {
        "nombre": "Cantharellus cibarius (Rebozuelo)",
        "lluvia_ideal": 200, "lluvia_tol": 320,
        "temp_ideal": 17,    "temp_tol": 14,
        "meses_optimos": [9, 10, 11],
        "meses_limite": [8, 12],
    },
]


# ---------------------------------------------------------------------------
# Cliente AEMET (petición en dos pasos)
# ---------------------------------------------------------------------------
def _aemet_get(url):
    headers = {"api_key": AEMET_KEY, "Accept": "application/json"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def _aemet_datos(url_primera_llamada):
    meta = _aemet_get(url_primera_llamada)
    if meta.get("estado") != 200 or "datos" not in meta:
        raise RuntimeError(f"AEMET respondió: {meta.get('descripcion', meta)}")
    r = requests.get(meta["datos"], timeout=15)
    r.raise_for_status()
    return r.json()




# OBTENER METEO SIERRA DE MADRID

def _meteo_una_estacion(estacion_id):
    """Devuelve (lluvia_30d, temp_actual) para una estación, o None si falla."""
    try:
        # Temperatura actual
        url_obs = f"{BASE}/observacion/convencional/datos/estacion/{estacion_id}"
        obs = _aemet_datos(url_obs)
        if not obs:
            return None
        ultima = max(obs, key=lambda x: x.get("fint", ""))
        temp = ultima.get("ta")
        if temp is None:
            return None
        if isinstance(temp, str):
            temp = temp.replace(",", ".")
        try:
            temp = float(temp)
        except (ValueError, TypeError):
            return None

        # Lluvia 30 días
        hoy = date.today()
        hace_30 = hoy - timedelta(days=30)
        f_ini = f"{hace_30.isoformat()}T00%3A00%3A00UTC"
        f_fin = f"{hoy.isoformat()}T00%3A00%3A00UTC"
        url_clima = (
            f"{BASE}/valores/climatologicos/diarios/datos/"
            f"fechaini/{f_ini}/fechafin/{f_fin}/estacion/{estacion_id}"
        )
        dias = _aemet_datos(url_clima)

        lluvia = 0.0
        for d in dias:
            prec = d.get("prec")
            if prec is None or prec == "":
                continue
            if isinstance(prec, str):
                prec = prec.strip()
                if prec.lower() == "ip":
                    continue
                prec = prec.replace(",", ".")
            try:
                lluvia += float(prec)
            except (ValueError, TypeError):
                continue

        return (lluvia, temp)
    except Exception:
        return None


def obtener_datos_por_estacion():
    """
    Devuelve lista de dicts:
      [{"estacion": nombre, "altitud": m, "lluvia": mm, "temp": °C,
        "favorables": [(puntaje, nombre), ...]}, ...]
    Omite estaciones que fallen.
    """
    clave = "meteo:por_estacion"
    cacheado = cache_get(clave)
    if cacheado is not None:
        return cacheado

    resultados = []
    for est in ESTACIONES:
        datos = _meteo_una_estacion(est["id"])
        if datos is None:
            continue
        lluvia, temp = datos
        favorables = puntuar_especies(lluvia, temp)
        resultados.append({
            "estacion": est["nombre"],
            "altitud": est["altitud"],
            "lat": est["lat"],
            "lon": est["lon"],
            "lluvia": round(lluvia, 1),
            "temp": round(temp, 1),
            "favorables": favorables,
        })

    if not resultados:
        raise RuntimeError("Ninguna estación devolvió datos")

    cache_set(clave, resultados)
    return resultados


# ---------------------------------------------------------------------------
# Baremo
# ---------------------------------------------------------------------------
def _factor_estacional(especie, mes):
    if mes in especie["meses_optimos"]:
        return 1.0
    if mes in especie["meses_limite"]:
        return 0.5
    return 0.0


def puntuar(especie, lluvia, temp, mes=None):
    """Devuelve puntuación 0–10 (0 si fuera de temporada)."""
    if mes is None:
        mes = date.today().month

    factor = _factor_estacional(especie, mes)
    if factor == 0:
        return 0.0

    p_lluvia = 10 * max(0.0, 1 - abs(lluvia - especie["lluvia_ideal"]) / especie["lluvia_tol"])
    p_temp   = 10 * max(0.0, 1 - abs(temp   - especie["temp_ideal"])   / especie["temp_tol"])

    base = 0.65 * p_lluvia + 0.35 * p_temp
    return round(base * factor, 1)


# def nivel_cualitativo(puntos):
#     ...


def puntuar_especies(lluvia, temp, mes=None):
    if mes is None:
        mes = date.today().month
    resultado = []
    for e in ESPECIES:
        p = puntuar(e, lluvia, temp, mes)
        if p > 0:
            resultado.append((p, e["nombre"]))
    return sorted(resultado, key=lambda x: x[0], reverse=True)


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    try:
        zonas = obtener_datos_por_estacion()
    except Exception as exc:
        return render_template("index.html", error=f"No se pudo obtener el tiempo: {exc}")

    return render_template("index.html", zonas=zonas)


@app.route("/sobre")
def sobre():
    return render_template("sobre.html")


@app.route("/contacto")
def contacto():
    return render_template("contacto.html")




if __name__ == "__main__":
    app.run(debug=True)
    
