import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import gspread
import pandas as pd
import json
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Dashboard Trading Pro", layout="wide", page_icon="📈")

# Estilo CSS para forzar fondo oscuro en la app si el usuario no lo tiene
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Dashboard de Riesgo: Kelly & Montecarlo")
st.markdown("---")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración")
    capital_inicial = st.number_input("Capital Inicial ($)", value=4000)
    dd_tolerado = st.slider("Max Drawdown Tolerado (%)", 5.0, 30.0, 15.0)
    n_simulaciones = st.slider("Simulaciones", 500, 5000, 2000)
    n_trades = st.slider("Proyección (Trades)", 50, 200, 100)
    
    st.markdown("### ☁️ Conexión Sheets")
    nombre_archivo = st.text_input("Archivo", "Registro2")
    # AQUÍ ESTÁ EL FIX DEL ESPACIO:
    nombre_hoja = st.text_input("Hoja", "Hoja 24 ") 
    
    boton_correr = st.button("🚀 EJECUTAR ANÁLISIS", type="primary")

# --- FUNCIÓN DE CARGA BLINDADA ---
def cargar_datos_sheets(archivo, hoja):
    # 1. Cargar credenciales desde el bloque de texto JSON
    json_string = st.secrets["text_json"]
    credenciales_dict = json.loads(json_string)
    
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credenciales_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 2. Abrir archivo y hoja con manejo de errores
    try:
        sh = client.open(archivo)
    except:
        raise Exception(f"No encontré el archivo '{archivo}'. Revisa el nombre.")

    try:
        worksheet = sh.worksheet(hoja)
    except:
        lista = [s.title for s in sh.worksheets()]
        raise Exception(f"No existe la pestaña '{hoja}'. Las disponibles son: {lista}")
    
    # 3. Leer datos
    datos = worksheet.get("A:B")
    etiquetas, valores = [], []
    
    for fila in datos:
        if len(fila) < 2: continue
        try:
            val = float(str(fila[1]).replace(',', '.').replace('%','').replace('$','').strip())
            etiquetas.append(str(fila[0]).lower())
            valores.append(val)
        except:
            continue
            
    return np.array(valores), np.array(etiquetas), worksheet

# --- MOTOR MONTECARLO ---
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
    with st.spinner('Conectando a Google Sheets y procesando datos...'):
        try:
            # 1. Cargar
            vals, tags, ws = cargar_datos_sheets(nombre_archivo, nombre_hoja)
            
            # 2. Estadísticas Básicas
            wins = vals[np.char.find(tags, 'win') >= 0]
            losses = vals[np.char.find(tags, 'loss') >= 0]
            wr = len(wins) / len(vals) if len(vals) > 0 else 0
            avg_win = np.mean(wins) if len(wins) > 0 else 0
            avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 1
            payoff = avg_win / avg_loss
            kelly = (wr - (1-wr)/payoff) * 100
            
            st.success(f"✅ Datos Cargados: {len(vals)} trades | WR: {wr:.1%} | Payoff: 1:{payoff:.2f}")
            
            # 3. Optimización (Buscando el riesgo ideal)
            riesgos = np.linspace(0.1, min(kelly, 25.0), 50)
            mejor_r = 0.1
            
            progreso = st.progress(0)
            for i, r in enumerate(riesgos):
                _, dds = simular(vals, capital_inicial, r, n_trades, 500)
                if np.percentile(dds, 95) < dd_tolerado:
                    mejor_r = r
                else:
                    break
                progreso.progress((i + 1) / len(riesgos))
            progreso.empty()
            
            # 4. Simulación Final
            curvas, dds_finales = simular(vals, capital_inicial, mejor_r, n_trades, n_simulaciones)
            mediana_final = np.median(curvas[:,-1])
            peor_caso = np.percentile(dds_finales, 95)
            
            # 5. KPIs
            col1, col2, col3 = st.columns(3)
            col1.metric("Riesgo Óptimo (Safe)", f"{mejor_r:.2f}%", f"Kelly: {mejor_r/kelly:.2f}x")
            col2.metric("Proyección Mediana", f"${mediana_final:,.0f}", f"+{((mediana_final-capital_inicial)/capital_inicial)*100:.1f}%")
            col3.metric("Riesgo Ruina (95%)", f"{peor_caso:.2f}%", f"Límite: {dd_tolerado}%", delta_color="inverse")
            
            # --- SECCIÓN DE GRÁFICOS (MODO OSCURO) ---
            # Configurar estilo oscuro para Matplotlib
            plt.style.use('dark_background')
            
            # Creamos un layout de grilla
            fig = plt.figure(figsize=(16, 12))
            gs = fig.add_gridspec(2, 2)
            
            # Colores Neón
            c_mediana = '#00ff41' # Verde Hacker
            c_peor = '#ff0055'    # Magenta Neón
            c_real = '#00e5ff'    # Cian Eléctrico
            c_hist = '#ffff00'    # Amarillo
            
            # GRÁFICO 1: Proyección Equity ($) (Arriba Izquierda)
            ax1 = fig.add_subplot(gs[0, 0])
            ax1.plot(curvas[:100].T, color='gray', alpha=0.1)
            ax1.plot(np.median(curvas, axis=0), color=c_mediana, linewidth=2, label='Proyección Mediana')
            ax1.plot(np.percentile(curvas, 5, axis=0), color=c_peor, linewidth=2, linestyle='--', label='Peor Caso (5%)')
            ax1.axhline(capital_inicial, color='white', linestyle=':', alpha=0.5)
            ax1.set_title("1. Proyección Futura de Capital ($)", fontsize=14, color='white', fontweight='bold')
            ax1.legend(facecolor='black', edgecolor='white')
            ax1.grid(color='gray', linestyle=':', alpha=0.3)
            
            # GRÁFICO 2: Distribución de Drawdown (Arriba Derecha)
            ax2 = fig.add_subplot(gs[0, 1])
            ax2.hist(dds_finales, bins=40, color=c_peor, alpha=0.7, edgecolor='white')
            ax2.axvline(peor_caso, color='white', linewidth=2, linestyle='--', label=f'Peor Caso: {peor_caso:.1f}%')
            ax2.axvline(dd_tolerado, color=c_hist, linewidth=2, label='Límite')
            ax2.set_title("2. Riesgo de Caída (Drawdown)", fontsize=14, color='white', fontweight='bold')
            ax2.legend(facecolor='black', edgecolor='white')
            ax2.grid(color='gray', linestyle=':', alpha=0.3)
            
            # GRÁFICO 3: CURVA REAL EN R (Abajo - Ancho Completo)
            ax3 = fig.add_subplot(gs[1, :]) # Ocupa toda la fila de abajo
            curva_real = np.cumsum(vals)
            curva_real = np.insert(curva_real, 0, 0) # Empezar en 0
            
            ax3.plot(curva_real, color=c_real, linewidth=3, marker='o', markersize=4, label='Mi Curva Real')
            ax3.fill_between(range(len(curva_real)), 0, curva_real, color=c_real, alpha=0.15)
            ax3.axhline(0, color='white', linestyle='-')
            ax3.set_title(f"3. MI RENDIMIENTO REAL HISTÓRICO (Total: {curva_real[-1]:.2f}R)", fontsize=16, color=c_real, fontweight='bold')
            ax3.set_ylabel("R-Múltiplos Acumulados", color='white')
            ax3.set_xlabel("Número de Trade", color='white')
            ax3.legend(facecolor='black', edgecolor='white')
            ax3.grid(color='gray', linestyle=':', alpha=0.3)
            
            plt.tight_layout()
            st.pyplot(fig)
            
            # --- GUARDAR EN SHEETS ---
            st.markdown("---")
            col_save, _ = st.columns([1, 3])
            if col_save.button("💾 Guardar Riesgo en G2"):
                try:
                    ws.update_acell('G2', mejor_r/100)
                    st.toast(f"¡Guardado! Riesgo {mejor_r:.2f}% en celda G2.", icon="✅")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

        except Exception as e:
            st.error(f"❌ Ocurrió un error: {e}")
