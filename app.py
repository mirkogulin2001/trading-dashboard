import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import json
# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Dashboard Montecarlo", layout="wide")

st.title("🛡️ Optimizador de Riesgo: Kelly & Montecarlo")
st.markdown("---")

# --- BARRA LATERAL (INPUTS) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    capital_inicial = st.number_input("Capital Inicial ($)", value=4000)
    dd_tolerado = st.slider("Max Drawdown Tolerado (%)", 5.0, 30.0, 15.0)
    n_simulaciones = st.slider("Simulaciones", 500, 5000, 2000)
    n_trades = st.slider("Proyección (Trades)", 50, 200, 100)
    
    st.markdown("### ☁️ Conexión Sheets")
    nombre_archivo = st.text_input("Archivo", "Registro2")
    nombre_hoja = st.text_input("Hoja", "Hoja24 ")
    
    boton_correr = st.button("🚀 EJECUTAR SIMULACIÓN", type="primary")

# --- FUNCIÓN DE CARGA BLINDADA (SOLUCIÓN JSON) ---
def cargar_datos_sheets(archivo, hoja):
    # 1. Leemos el bloque de texto crudo desde los secretos
    json_string = st.secrets["text_json"]
    
    # 2. Lo convertimos a un diccionario Python real
    credenciales_dict = json.loads(json_string)
    
    # 3. Autenticación
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credenciales_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 4. Abrir hoja
    sh = client.open(archivo)
    worksheet = sh.worksheet(hoja)
    
    # 5. Leer datos
    datos = worksheet.get("A:B")
    
    etiquetas = []
    valores = []
    
    for fila in datos:
        if len(fila) < 2: continue
        try:
            val = float(str(fila[1]).replace(',', '.').replace('%','').replace('$','').strip())
            etiquetas.append(str(fila[0]).lower())
            valores.append(val)
        except:
            continue
            
    return np.array(valores), np.array(etiquetas), worksheet
# --- LOGICA MONTECARLO ---
def simular(r_multiples, balance, riesgo, n_trades, n_sims):
    seleccion = np.random.choice(r_multiples, size=(n_sims, n_trades), replace=True)
    retornos = seleccion * riesgo
    mults = 1.0 + (retornos / 100.0)
    
    curvas = np.zeros((n_sims, n_trades + 1))
    curvas[:,0] = balance
    curvas[:,1:] = balance * np.cumprod(mults, axis=1)
    
    picos = np.maximum.accumulate(curvas, axis=1)
    dds = (curvas - picos) / picos
    max_dds = np.min(dds, axis=1) * -100
    
    return curvas, max_dds

# --- EJECUCIÓN PRINCIPAL ---
if boton_correr:
    with st.spinner('Conectando a Google Sheets y calculando...'):
        try:
            vals, tags, ws = cargar_datos_sheets(nombre_archivo, nombre_hoja)
            
            # Estadísticas
            wins = vals[np.char.find(tags, 'win') >= 0]
            losses = vals[np.char.find(tags, 'loss') >= 0]
            wr = len(wins) / len(vals)
            payoff = np.mean(wins) / abs(np.mean(losses))
            kelly = (wr - (1-wr)/payoff) * 100
            
            st.success(f"Datos Cargados: {len(vals)} trades. WinRate: {wr:.1%} | Payoff: {payoff:.2f}")
            
            # Optimización
            riesgos = np.linspace(0.1, min(kelly, 25.0), 50)
            mejor_r = 0.1
            
            progress_bar = st.progress(0)
            
            for i, r in enumerate(riesgos):
                _, dds = simular(vals, capital_inicial, r, n_trades, 500)
                if np.percentile(dds, 95) < dd_tolerado:
                    mejor_r = r
                else:
                    break
                progress_bar.progress((i + 1) / len(riesgos))
            
            progress_bar.empty()
            
            # Simulación Final
            curvas, dds_finales = simular(vals, capital_inicial, mejor_r, n_trades, n_simulaciones)
            mediana_final = np.median(curvas[:,-1])
            peor_caso = np.percentile(dds_finales, 95)
            
            # --- MOSTRAR RESULTADOS (KPIs) ---
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Riesgo Sugerido", f"{mejor_r:.2f}%", f"Kelly: {mejor_r/kelly:.2f}x")
            kpi2.metric("Capital Proyectado (Mediana)", f"${mediana_final:,.0f}", f"+{((mediana_final-capital_inicial)/capital_inicial)*100:.1f}%")
            kpi3.metric("Peor Drawdown (95%)", f"{peor_caso:.2f}%", f"Límite: {dd_tolerado}%", delta_color="inverse")
            
            # --- GRÁFICOS ---
            fig, ax = plt.subplots(1, 2, figsize=(15, 6))
            
            # Equity
            ax[0].plot(curvas[:100].T, color='gray', alpha=0.1)
            ax[0].plot(np.median(curvas, axis=0), color='green', linewidth=2)
            ax[0].set_title("Proyección de Capital")
            ax[0].axhline(capital_inicial, linestyle='--', color='black')
            
            # Histograma DD
            ax[1].hist(dds_finales, bins=30, color='red', alpha=0.7)
            ax[1].axvline(peor_caso, color='black', linewidth=2, linestyle='--')
            ax[1].set_title(f"Distribución de Riesgo (Peor caso: {peor_caso:.1f}%)")
            
            st.pyplot(fig)
            
            # --- ACTUALIZAR SHEET ---
            if st.button("💾 Guardar Riesgo en Google Sheets (G2)"):
                try:
                    ws.update_acell('G2', mejor_r/100)
                    st.toast("¡Guardado correctamente en G2!", icon="✅")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
                    
        except Exception as e:

            st.error(f"Ocurrió un error: {e}")

