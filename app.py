import os
import time
from datetime import date, timedelta

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, abort, request



load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuración AEMET
# ---------------------------------------------------------------------------
AEMET_KEY = os.environ.get("AEMET_KEY", "")
if not AEMET_KEY:
    print("⚠️  AEMET_KEY no definida. Crea un .env con AEMET_KEY=tu_clave")

BASE = "https://opendata.aemet.es/opendata/api"

def _dms_a_decimal(dms):
    """Convierte '405129N' o '0040642W' a decimal. Devuelve None si falla."""
    if not dms or len(dms) < 7:
        return None
    try:
        grados = int(dms[0:2])
        minutos = int(dms[2:4])
        segundos = int(dms[4:6])
        hemisferio = dms[-1].upper()
        decimal = grados + minutos / 60 + segundos / 3600
        if hemisferio in ("S", "W"):
            decimal = -decimal
        return round(decimal, 5)
    except (ValueError, IndexError):
        return None

import time

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

def _cargar_estaciones(provincias=("MADRID", "SEGOVIA", "AVILA"), altitud_min=800):
    """Consulta el inventario de AEMET y devuelve la lista filtrada."""
    try:
        url = f"{BASE}/valores/climatologicos/inventarioestaciones/todasestaciones"
        inventario = _aemet_datos(url)
    except Exception as exc:
        print(f"⚠️  No se pudo cargar el inventario de estaciones: {exc}")
        return []

    resultado = []
    for e in inventario:
        prov = e.get("provincia", "").upper().strip()
        try:
            alt = float(e.get("altitud", 0))
        except (ValueError, TypeError):
            continue
        if prov not in provincias or alt <= altitud_min:
            continue

        lat = _dms_a_decimal(e.get("latitud"))
        lon = _dms_a_decimal(e.get("longitud"))
        if lat is None or lon is None:
            continue

        resultado.append({
            "id": e["indicativo"],
            "nombre": e["nombre"].title(),
            "altitud": int(alt),
            "lat": lat,
            "lon": lon,
            "provincia": prov.title(),
        })

    # Ordenar por altitud descendente (las más altas primero)
    resultado.sort(key=lambda x: x["altitud"], reverse=True)
    print(f"✅ Cargadas {len(resultado)} estaciones de Madrid, Segovia y Ávila (> {altitud_min} m)")
    resutlado = resultado[:15]  # Limitar a las 10 más altas
    return resultado



ESTACIONES = _cargar_estaciones()

# # Estaciones de la Sierra de Madrid (altitud >= 1000 m)
# ESTACIONES = [
#     {"id": "2462",  "nombre": "Puerto de Navacerrada", "altitud": 1892},
#     {"id": "3266A", "nombre": "Puerto Alto del León",  "altitud": 1530},
#     {"id": "3111D", "nombre": "Somosierra",            "altitud": 1454},
#     {"id": "3104Y", "nombre": "Rascafría",             "altitud": 1159},
#     {"id": "3110C", "nombre": "Buitrago del Lozoya",   "altitud": 1030},
# ]

# ---------------------------------------------------------------------------
# Configuración AEMET
# ---------------------------------------------------------------------------
AEMET_KEY = os.environ.get("AEMET_KEY", "")
if not AEMET_KEY:
    print("⚠️  AEMET_KEY no definida. Crea un .env con AEMET_KEY=tu_clave")

# BASE = "https://opendata.aemet.es/opendata/api"

# Estaciones de la Sierra de Madrid (altitud >= 1000 m)
# ESTACIONES = [
#     {"id": "2462",  "nombre": "Puerto de Navacerrada", "altitud": 1892, "lat": 40.7808, "lon": -4.0103},
#     {"id": "3266A", "nombre": "Puerto Alto del León",  "altitud": 1530, "lat": 40.6583, "lon": -4.1167},
#     {"id": "3111D", "nombre": "Somosierra",            "altitud": 1454, "lat": 41.1333, "lon": -3.5833},
#     {"id": "3104Y", "nombre": "Rascafría",             "altitud": 1159, "lat": 40.9000, "lon": -3.8833},
#     {"id": "3110C", "nombre": "Buitrago del Lozoya",   "altitud": 1030, "lat": 40.9833, "lon": -3.6333},
# ]

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
        "id": "boletus-edulis",
        "nombre": "Boletus edulis (Calabaza)",
        "cientifico": "Boletus edulis",
        "lluvia_ideal": 160, "lluvia_tol": 280,
        "temp_ideal": 15,    "temp_tol": 15,
        "meses_optimos": [9, 10, 11],
        "meses_limite": [8, 12],
        "foto": "img/boletus-edulis.jpg",
        "descripcion": "Seta de sombrero pardo y pie robusto con retículo blanco. Carne blanca que no azulea al corte. Una de las más apreciadas en cocina.",
        "habitat": "Pinares, robledales y hayedos, en suelos ácidos. Desde finales de verano hasta final del otoño.",
        "comestible": "Excelente comestible. Única confusión posible con Tylopilus felleus (amargo, no tóxico).",
        "altitud_tipica": "800 – 1.800 m",
    },
    {
        "id": "boletus-pinophilus",
        "nombre": "Boletus pinophilus (Hongo de pino)",
        "cientifico": "Boletus pinophilus",
        "lluvia_ideal": 160, "lluvia_tol": 280,
        "temp_ideal": 15,    "temp_tol": 15,
        "meses_optimos": [9, 10, 11],
        "meses_limite": [8, 12],
        "foto": "img/boletus-pinophilus.jpg",
        "descripcion": "Muy similar al Boletus edulis, pero con sombrero granate-rojizo uniforme y pie más rechoncho. Carne blanca, firme.",
        "habitat": "Exclusivo de pinares, tanto de pino silvestre como de pino negro. Otoño.",
        "comestible": "Excelente comestible, al nivel del Boletus edulis.",
        "altitud_tipica": "1.000 – 2.000 m",
    },
    {
        "id": "pleurotus-eryngii",
        "nombre": "Seta de Cardo",
        "cientifico": "Pleurotus eryngii",
        "lluvia_ideal": 80,  "lluvia_tol": 150,
        "temp_ideal": 16,    "temp_tol": 14,
        "meses_optimos": [10, 11],
        "meses_limite": [9, 12, 3, 4],
        "foto": "img/pleurotus-eryngii.jpg",
        "descripcion": "Seta de sombrero convexo y pie corto y grueso, que crece sobre las raíces del cardo corredor (Eryngium campestre).",
        "habitat": "Zonas secas y soleadas con cardos. Otoño y principios de primavera.",
        "comestible": "Excelente comestible, muy apreciada. Sin confusiones peligrosas si se respeta el hábitat sobre cardo.",
        "altitud_tipica": "500 – 1.500 m",
    },
    {
        "id": "lactarius-deliciosus",
        "nombre": "Níscalo",
        "cientifico": "Lactarius deliciosus",
        "lluvia_ideal": 120, "lluvia_tol": 240,
        "temp_ideal": 12,    "temp_tol": 12,
        "meses_optimos": [10, 11],
        "meses_limite": [9, 12, 1],
        "foto": "img/lactarius-deliciosus.jpg",
        "descripcion": "Seta anaranjada que exuda látex del mismo color al cortarla. La carne se oxida a verde con el roce. Pie hueco.",
        "habitat": "Exclusivo de pinares, en simbiosis con las raíces de los pinos. Otoño.",
        "comestible": "Excelente comestible. No confundir con otras especies de Lactarius de sabor picante o amargo.",
        "altitud_tipica": "800 – 2.000 m",
    },
    {
        "id": "marasmius-oreades",
        "nombre": "Senderuela",
        "cientifico": "Marasmius oreades",
        "lluvia_ideal": 100, "lluvia_tol": 180,
        "temp_ideal": 15,    "temp_tol": 15,
        "meses_optimos": [4, 5, 6, 9, 10],
        "meses_limite": [3, 7, 8, 11],
        "foto": "img/marasmius-oreades.jpg",
        "descripcion": "Seta pequeña de sombrero acampanado y pie fibroso, que crece formando corros o hileras en la hierba.",
        "habitat": "Praderas, prados y bordes de caminos. Primavera y otoño.",
        "comestible": "Comestible tras cocinado (en crudo contiene ácido cianhídrico). Solo se aprovechan los sombreros; el pie es duro. Cuidado con confundirla con Clitocybe tóxicas.",
        "altitud_tipica": "600 – 1.800 m",
    },
    {
        "id": "amanita-caesarea",
        "nombre": "Amanita caesarea (Oronja)",
        "cientifico": "Amanita caesarea",
        "lluvia_ideal": 180, "lluvia_tol": 280,
        "temp_ideal": 20,    "temp_tol": 12,
        "meses_optimos": [9, 10],
        "meses_limite": [8, 11],
        "foto": "img/amanita-caesarea.jpg",
        "descripcion": "Seta de sombrero anaranjado intenso, láminas amarillas y pie con anillo. Cuando nace está envuelta en un huevo blanco.",
        "habitat": "Bosques de frondosas (robledales, castañares), en suelos cálidos. Finales de verano y otoño.",
        "comestible": "Excelente comestible, pero requiere experiencia: puede confundirse con otras amanitas. No consumir sin identificación segura.",
        "altitud_tipica": "500 – 1.500 m",
    },
    {
        "id": "calocybe-gambosa",
        "nombre": "Perrochico (Calocybe gambosa)",
        "cientifico": "Calocybe gambosa",
        "lluvia_ideal": 100, "lluvia_tol": 180,
        "temp_ideal": 14,    "temp_tol": 12,
        "meses_optimos": [4, 5],
        "meses_limite": [3, 6],
        "foto": "img/calocybe-gambosa",
        "descripcion": "Seta primaveral de sombrero blanquecino y pie robusto, con un característico olor a harina fresca.",
        "habitat": "Prados, pastizales y linderos, formando corros o hileras. Primavera.",
        "comestible": "Excelente comestible. Cuidado con confundirla con Entoloma sinuatum (tóxica, otoñal, láminas rosadas).",
        "altitud_tipica": "Cotas bajas – 2.000 m",
    },
        {
        "id": "agaricus-campestris",
        "nombre": "Champiñón silvestre",
        "cientifico": "Agaricus campestris",
        "lluvia_ideal": 120, "lluvia_tol": 220,
        "temp_ideal": 16,    "temp_tol": 14,
        "meses_optimos": [4, 5, 9, 10],
        "meses_limite": [3, 6, 8, 11],
        "foto": "img/agaricus-campestris",
        "descripcion": "Seta de sombrero blanco y láminas rosadas que se vuelven pardas al madurar. Olor agradable a champiñón.",
        "habitat": "Praderas, pastizales y bordes de caminos. Primavera y otoño.",
        "comestible": "Excelente comestible. Cuidado extremo con confundirlo con Amanita phalloides o A. virosa (blancas, con anillo y volva).",
        "altitud_tipica": "500 – 1.500 m",
    },
    {
        "id": "agrocybe-aegerita",
        "nombre": "Seta de chopo",
        "cientifico": "Agrocybe aegerita",
        "lluvia_ideal": 140, "lluvia_tol": 240,
        "temp_ideal": 15,    "temp_tol": 14,
        "meses_optimos": [10, 11],
        "meses_limite": [9, 12, 4, 5],
        "foto": "img/agrocybe-aegerita.jpg",
        "descripcion": "Seta de sombrero pardo y pie largo, que crece en racimos sobre madera muerta de chopos y álamos.",
        "habitat": "Troncos y tocones de chopos, álamos y sauces, en riberas y sotos. Otoño y primavera.",
        "comestible": "Excelente comestible, muy apreciada en la zona del Duero y del sur de Europa.",
        "altitud_tipica": "500 – 1.200 m",
    },
    {
        "id": "morchella-esculenta",
        "nombre": "Colmenilla",
        "cientifico": "Morchella esculenta",
        "lluvia_ideal": 100, "lluvia_tol": 180,
        "temp_ideal": 14,    "temp_tol": 12,
        "meses_optimos": [3, 4, 5],
        "meses_limite": [2, 6],
        "foto": "img/morchella-esculenta.jpg",
        "descripcion": "Seta de sombrero con aspecto de esponja o panal de abeja, color ocre. Muy apreciada en cocina.",
        "habitat": "Bosques de ribera, encinares, pinares y zonas húmedas. Primavera.",
        "comestible": "Excelente comestible, pero tóxica en crudo: hay que cocinarla bien. Cuidado con confundirla con la colmenilla falsa (Gyromitra esculenta), muy tóxica.",
        "altitud_tipica": "600 – 1.800 m",
    },
    {
        "id": "craterellus-cornucopioides",
        "nombre": "Trompeta de los muertos",
        "cientifico": "Craterellus cornucopioides",
        "lluvia_ideal": 150, "lluvia_tol": 260,
        "temp_ideal": 14,    "temp_tol": 14,
        "meses_optimos": [10, 11],
        "meses_limite": [9, 12],
        "foto": "img/craterellus-cornucopioides.jpg",
        "descripcion": "Seta en forma de trompeta o embudo, de color gris negruzco. A menudo pasa desapercibida por su camuflaje con la hojarasca.",
        "habitat": "Bosques de frondosas (robledales, hayedos, castañares), en suelos húmedos. Otoño.",
        "comestible": "Excelente comestible, muy apreciada en cocina. Difícil de confundir.",
        "altitud_tipica": "700 – 1.700 m",
    },
]


# ---------------------------------------------------------------------------
# Cliente AEMET (petición en dos pasos)
# ---------------------------------------------------------------------------





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
    except Exception as exc:
        print(f"[ERROR] {estacion_id}: {type(exc).__name__}: {exc}") #AGT
        return None


def obtener_datos_por_estacion(provincia=None):
    clave = f"meteo:por_estacion:{provincia or 'todas'}"
    cacheado = cache_get(clave)
    if cacheado is not None:
        return cacheado

    print(f"[FILTRO] provincia = {provincia!r}")

    estaciones_filtradas = [
        est for est in ESTACIONES
        if provincia is None or est["provincia"].upper() == provincia.upper()
    ]
    print(f"[FILTRO] estaciones a consultar: {len(estaciones_filtradas)}")

    resultados = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futuros = {
            executor.submit(_meteo_una_estacion, est["id"]): est
            for est in estaciones_filtradas
        }
        for futuro in as_completed(futuros):
            est = futuros[futuro]
            datos = futuro.result()
            if datos is None:
                print(f"[FALLO] {est['nombre']}")
                continue
            lluvia, temp = datos
            resultados.append({
                "estacion": est["nombre"],
                "altitud": est["altitud"],
                "lat": est["lat"],
                "lon": est["lon"],
                "provincia": est["provincia"],
                "lluvia": round(lluvia, 1),
                "temp": round(temp, 1),
                "favorables": puntuar_especies(lluvia, temp),
            })

    if not resultados:
        raise RuntimeError(f"Ninguna estación devolvió datos (provincia: {provincia or 'todas'})")

    def _mejor_puntaje(z):
        return z["favorables"][0][0] if z["favorables"] else -1

    resultados.sort(key=_mejor_puntaje, reverse=True)
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
            resultado.append((p, e["nombre"], e["id"]))
    return sorted(resultado, key=lambda x: x[0], reverse=True)

def calcular_resumen(zonas):
    """Devuelve dict con la mejor zona y la mejor especie global."""
    mejor = None  # (puntaje, especie, zona)
    for z in zonas:
        for puntaje, nombre, _id in z["favorables"]:
            if mejor is None or puntaje > mejor[0]:
                mejor = (puntaje, nombre, z)

    if mejor is None:
        return None

    puntaje, especie, zona = mejor
    return {
        "especie": especie,
        "puntaje": puntaje,
        "estacion": zona["estacion"],
        "altitud": zona["altitud"],
    }


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    provincia = request.args.get("provincia")
    try:
        zonas = obtener_datos_por_estacion(provincia)
    except Exception as exc:
        return render_template(
            "index.html",
            error=f"No se pudo obtener el tiempo: {exc}",
            zonas=[],
            resumen=None,
            provincia=provincia,
        )

    resumen = calcular_resumen(zonas)
    return render_template(
        "index.html",
        zonas=zonas,
        resumen=resumen,
        provincia=provincia,
    )


@app.route("/sobre")
def sobre():
    return render_template("sobre.html")


@app.route("/contacto")
def contacto():
    return render_template("contacto.html")

@app.route("/recargar")
def recargar():
    """Vacía la caché y vuelve al inicio con datos frescos."""
    _cache.clear()
    return redirect(url_for("inicio"))

@app.route("/especie/<slug>")
def especie(slug):
    for e in ESPECIES:
        if e["id"] == slug:
            return render_template("especie.html", especie=e)
    abort(404)

@app.route("/especies")
def especies():
    return render_template("especies.html", especies=ESPECIES)

if __name__ == "__main__":
    app.run(debug=True)
    
