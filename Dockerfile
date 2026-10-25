# Usa una imagen oficial de Python ligera
FROM python:3.11-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia el archivo de dependencias y las instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación
COPY . .

# Expone el puerto que Render espera (aunque Render usa la variable PORT)
EXPOSE 10000

# Comando para arrancar la aplicación con Gunicorn
# Usa la variable de entorno PORT que Render asigna automáticamente
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]