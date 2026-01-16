import streamlit as st
import pandas as pd
import numpy as np
import gspread
import json
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Modo Diagnóstico", layout="wide")

st.title("🚑 Modo Diagnóstico")
st.write("Si puedes leer esto, Streamlit está vivo.")

# --- 1. PRUEBA DE SECRETOS ---
st.header("1. Prueba de Credenciales")
if "text_json" in st.secrets:
    st.success("✅ Secretos detectados correctamente.")
else:
    st.error("❌ No se detectan los secretos (text_json). Revisa el dashboard de Streamlit.")

# --- 2. PRUEBA DE CONEXIÓN A SHEETS ---
st.header("2. Prueba de Conexión a Google Sheets")
nombre_archivo = st.text_input("Nombre del Archivo", "Registro2")
boton_test = st.button("Probar Conexión")

if boton_test:
    try:
        # Intento de conexión básico
        json_string = st.secrets["text_json"]
        credenciales_dict = json.loads(json_string)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(credenciales_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        st.info(f"Intentando abrir '{nombre_archivo}'...")
        sh = client.open(nombre_archivo)
        st.success(f"✅ Archivo '{nombre_archivo}' encontrado.")
        
        # Listar hojas
        hojas = [s.title for s in sh.worksheets()]
        st.write(f"Pestañas encontradas: {hojas}")
        
        # Prueba de lectura de Hoja 24
        ws = sh.worksheet("Hoja 24") # Ojo con el nombre
        val_a1 = ws.acell('A1').value
        st.success(f"✅ Lectura exitosa: Celda A1 contiene '{val_a1}'")
        
    except Exception as e:
        st.error(f"❌ FALLÓ LA CONEXIÓN: {e}")

# --- 3. PRUEBA DE GRÁFICOS (PLOTLY) ---
st.header("3. Prueba de Gráficos")
if st.button("Generar Gráfico de Prueba"):
    try:
        fig = go.Figure(data=[go.Bar(y=[2, 1, 3])])
        st.plotly_chart(fig)
        st.success("✅ Plotly funciona bien.")
    except Exception as e:
        st.error(f"❌ FALLÓ EL GRÁFICO: {e}")
