# 🍄 MicoMadrid

Consulta orientativa de especies de setas en la Sierra de Madrid según las
condiciones meteorológicas recientes.

## Qué hace

- Consulta la API OpenData de **AEMET** para cinco estaciones de la sierra:
  Puerto de Navacerrada, Puerto Alto del León, Somosierra, Rascafría y
  Buitrago del Lozoya.
- Calcula la **lluvia acumulada de los últimos 30 días** y la **temperatura actual**
  de cada estación.
- Aplica un **baremo continuo 0–10** a un catálogo de especies, con pesos
  65 % lluvia / 35 % temperatura y factor estacional.
- Muestra los resultados en tarjetas por estación, con barra de color, y en un
  mapa interactivo (Leaflet + capa base del IGN).

## Requisitos

- Python 3.10 o superior.
- Una **API Key de AEMET OpenData** (gratuita, sin caducidad):
  solicítala en https://opendata.aemet.es/centrodedescargas/inicio

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt