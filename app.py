import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import gspread
import pandas as pd
import json
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Dashboard Trading Pro", layout="wide", page_icon="📈")

# Estilo CSS para forzar fondo oscuro (Dark Mode)
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
    # Dejamos el espacio fijo para evitar errores
    nombre_hoja = st.text_input("Hoja", "Hoja 24") 
    
    boton_correr = st.button("🚀 EJECUTAR ANÁLISIS", type="primary")

# --- FUNCIÓN DE CARGA BLINDADA ---
def cargar_datos_sheets(archivo, hoja):
    # 1. Cargar credenciales desde el bloque JSON en Secrets
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
    with st.spinner('Conectando a Google Sheets y calculando...'):
        try:
            # 1. Cargar Datos
            vals, tags, ws = cargar_datos_sheets(nombre_archivo, nombre_hoja)
            
            # 2. Estadísticas Básicas
            wins = vals[np.char.find(tags, 'win') >= 0]
            losses = vals[np.char.find(tags, 'loss') >= 0]
            wr = len(wins) / len(vals) if len(vals) > 0 else 0
            avg_win = np.mean(wins) if len(wins) > 0 else 0
            avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 1
            payoff = avg_win / avg_loss if avg_loss > 0 else 0
            kelly = (wr - (1-wr)/payoff) * 100
            
            st.success(f"✅ Datos: {len(vals)} trades | WR: {wr:.1%} | Payoff: 1:{payoff:.2f}")
            
            # 3. Optimización
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
            
            # Cálculos de Equity Final
            equity_finales = curvas[:,-1]
            mediana_final = np.median(equity_finales)
            
            # CÁLCULOS NUEVOS: ROI (Retorno %)
            roi_simulaciones = ((equity_finales - capital_inicial) / capital_inicial) * 100
            roi_mediana_dist = np.median(roi_simulaciones)
            roi_peor = np.percentile(roi_simulaciones, 5) # El corte del peor 5% de los casos
            
            # Cálculo de DD
            peor_dd = np.percentile(dds_finales, 95)
            
            # 5. KPIs
            col1, col2, col3 = st.columns(3)
            col1.metric("Riesgo Óptimo", f"{mejor_r:.2f}%", f"Kelly: {mejor_r/kelly:.2f}x")
            col2.metric("Retorno Mediano", f"+{roi_mediana_dist:.1f}%", f"${mediana_final:,.0f}")
            col3.metric("Riesgo Ruina (95%)", f"{peor_dd:.2f}%", f"Límite: {dd_tolerado}%", delta_color="inverse")
            
            # --- GRÁFICOS (4 PANELES) ---
            plt.style.use('dark_background')
            fig = plt.figure(figsize=(16, 12))
            gs = fig.add_gridspec(2, 2) # Grilla de 2x2
            
            # Colores Neón
            c_mediana = '#00ff41' # Verde
            c_peor = '#ff0055'    # Rosa/Rojo
            c_real = '#00e5ff'    # Cian
            c_roi = '#ffaa00'     # Naranja
            
            # GRÁFICO 1: Proyección Equity ($) (Arriba Izq)
            ax1 = fig.add_subplot(gs[0, 0])
            ax1.plot(curvas[:100].T, color='gray', alpha=0.1)
            ax1.plot(np.median(curvas, axis=0), color=c_mediana, linewidth=2, label='Mediana')
            ax1.plot(np.percentile(curvas, 5, axis=0), color=c_peor, linewidth=2, linestyle='--', label='Peor Caso (5%)')
            ax1.axhline(capital_inicial, color='white', linestyle=':', alpha=0.5)
            ax1.set_title("1. Proyección Capital ($)", fontsize=12, color='white', fontweight='bold')
            ax1.legend(facecolor='black', edgecolor='white', fontsize=8)
            ax1.grid(color='gray', linestyle=':', alpha=0.3)
            
            # GRÁFICO 2: Distribución Drawdown (Arriba Der)
            ax2 = fig.add_subplot(gs[0, 1])
            ax2.hist(dds_finales, bins=40, color=c_peor, alpha=0.7, edgecolor='white')
            ax2.axvline(peor_dd, color='white', linewidth=2, linestyle='--', label=f'Peor 5%: {peor_dd:.1f}%')
            ax2.axvline(dd_tolerado, color='yellow', linewidth=2, label='Límite')
            ax2.set_title("2. Riesgo de Caída (%)", fontsize=12, color='white', fontweight='bold')
            ax2.legend(facecolor='black', edgecolor='white', fontsize=8)
            ax2.grid(color='gray', linestyle=':', alpha=0.3)
            
            # GRÁFICO 3: Distribución Retornos ROI (Abajo Izq) [NUEVO]
            ax3 = fig.add_subplot(gs[1, 0])
            ax3.hist(roi_simulaciones, bins=40, color=c_roi, alpha=0.7, edgecolor='white')
            ax3.axvline(roi_peor, color='white', linewidth=2, linestyle='--', label=f'Peor 5%: {roi_peor:.1f}%')
            ax3.axvline(roi_mediana_dist, color=c_mediana, linewidth=2, label=f'Mediana: {roi_mediana_dist:.1f}%')
            ax3.axvline(0, color='gray', linestyle='-', linewidth=1) # Línea de Break Even
            ax3.set_title("3. Distribución Retornos (%)", fontsize=12, color='white', fontweight='bold')
            ax3.legend(facecolor='black', edgecolor='white', fontsize=8)
            ax3.grid(color='gray', linestyle=':', alpha=0.3)
            
            # GRÁFICO 4: Curva Real Histórica (Abajo Der)
            ax4 = fig.add_subplot(gs[1, 1])
            curva_real = np.cumsum(vals)
            curva_real = np.insert(curva_real, 0, 0)
            
            ax4.plot(curva_real, color=c_real, linewidth=2, marker='o', markersize=3, label='Mi Curva')
            ax4.fill_between(range(len(curva_real)), 0, curva_real, color=c_real, alpha=0.15)
            ax4.axhline(0, color='white', linestyle='-')
            ax4.set_title(f"4. Mi Historial Real ({curva_real[-1]:.1f}R)", fontsize=12, color=c_real, fontweight='bold')
            ax4.set_ylabel("R-Múltiplos", color='white', fontsize=8)
            ax4.legend(facecolor='black', edgecolor='white', fontsize=8)
            ax4.grid(color='gray', linestyle=':', alpha=0.3)
            
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
