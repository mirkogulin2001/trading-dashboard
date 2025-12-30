import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import gspread
import pandas as pd
import json
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Trading Dashboard Pro", layout="wide", page_icon="📈")

# Estilo CSS (Dark Mode)
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    /* Ajuste para que las pestañas se vean bien */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1e1e1e;
        border-radius: 4px 4px 0px 0px;
        color: white;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00e5ff;
        color: black;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Trading Command Center")

# --- 1. FUNCIONES DE CARGA Y CÁLCULO ---

def obtener_cliente_gspread():
    """Autenticación centralizada para no repetir código"""
    json_string = st.secrets["text_json"]
    credenciales_dict = json.loads(json_string)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credenciales_dict, scopes=scope)
    return gspread.authorize(creds)

def cargar_datos_simulacion(archivo, hoja):
    """Carga datos para Montecarlo (Columna B de Hoja 24)"""
    client = obtener_cliente_gspread()
    try:
        sh = client.open(archivo)
        ws = sh.worksheet(hoja)
    except:
        raise Exception(f"Error abriendo '{archivo}' o pestaña '{hoja}'.")
    
    datos = ws.get("A:B")
    etiquetas, valores = [], []
    for fila in datos:
        if len(fila) < 2: continue
        try:
            val = float(str(fila[1]).replace(',', '.').replace('%','').replace('$','').strip())
            etiquetas.append(str(fila[0]).lower())
            valores.append(val)
        except: continue
    return np.array(valores), np.array(etiquetas), ws

def cargar_datos_reales(archivo):
    """Carga datos para Estadísticas Reales (Columna R de hoja 'Base')"""
    client = obtener_cliente_gspread()
    hoja_nombre = "Base" # <--- NOMBRE FIJO DE LA HOJA NUEVA
    columna_letra = "R"  # <--- COLUMNA DEL PnL ($)
    
    try:
        sh = client.open(archivo)
        ws = sh.worksheet(hoja_nombre)
    except:
        raise Exception(f"No encontré la hoja '{hoja_nombre}' en el archivo '{archivo}'.")
    
    # Obtenemos toda la columna R
    datos_crudos = ws.get(f"{columna_letra}:{columna_letra}")
    
    pnl_dolares = []
    
    # Empezamos desde el índice 1 para saltar el encabezado (fila 1)
    for fila in datos_crudos[1:]:
        if not fila: continue
        try:
            # Limpieza agresiva de símbolos de moneda
            val_str = str(fila[0]).replace(',', '.').replace('$','').replace('USD','').replace(' ','')
            val = float(val_str)
            pnl_dolares.append(val)
        except:
            continue
            
    return np.array(pnl_dolares)

def simular_montecarlo(r_multiples, balance, riesgo, n_trades, n_sims):
    seleccion = np.random.choice(r_multiples, size=(n_sims, n_trades), replace=True)
    retornos = seleccion * riesgo
    mults = 1.0 + (retornos / 100.0)
    curvas = np.zeros((n_sims, n_trades + 1))
    curvas[:,0] = balance
    curvas[:,1:] = balance * np.cumprod(mults, axis=1)
    picos = np.maximum.accumulate(curvas, axis=1)
    dds = (curvas - picos) / picos
    return curves, np.min(dds, axis=1) * -100

# --- 2. INTERFAZ DE USUARIO (TABS) ---

# Creamos las dos pestañas
tab_sim, tab_real = st.tabs(["🎲 Simulación & Riesgo", "📈 Estadísticas Reales ($)"])

# ==========================================
# PESTAÑA 1: SIMULACIÓN (TU CÓDIGO ANTERIOR)
# ==========================================
with tab_sim:
    st.markdown("### 🛡️ Optimizador de Riesgo (Kelly + Montecarlo)")
    
    # Barra de configuración (dentro del tab o global, aquí la pongo local para limpieza)
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1:
        capital_inicial = st.number_input("Capital Inicial ($)", value=4000)
        dd_tolerado = st.slider("Max Drawdown Tolerado (%)", 5.0, 30.0, 15.0)
    with col_conf2:
        nombre_archivo = st.text_input("Nombre Archivo Sheets", "Registro2")
        nombre_hoja_sim = st.text_input("Pestaña Datos R", "Hoja 24")

    if st.button("🚀 CORRER SIMULACIÓN", type="primary"):
        with st.spinner('Analizando futuros posibles...'):
            try:
                # Lógica Montecarlo (Resumida del código anterior)
                vals, tags, ws = cargar_datos_simulacion(nombre_archivo, nombre_hoja_sim)
                
                # Stats
                wins = vals[np.char.find(tags, 'win') >= 0]
                losses = vals[np.char.find(tags, 'loss') >= 0]
                wr = len(wins)/len(vals) if len(vals)>0 else 0
                payoff = np.mean(wins)/abs(np.mean(losses)) if len(losses)>0 else 0
                kelly = (wr - (1-wr)/payoff)*100
                
                # Optimización Rápida
                riesgos = np.linspace(0.1, min(kelly, 25.0), 40)
                mejor_r = 0.1
                for r in riesgos:
                    # Simulación interna rápida
                    sel = np.random.choice(vals, size=(500, 100), replace=True)
                    rets = sel * r
                    curves = capital_inicial * np.cumprod(1 + rets/100, axis=1)
                    # Cálculo DD rápido
                    peaks = np.maximum.accumulate(curves, axis=1)
                    dds = (curves - peaks)/peaks
                    if np.percentile(dds.min(axis=1)*-100, 95) < dd_tolerado:
                        mejor_r = r
                    else: break
                
                # Simulación Final Detallada
                n_trades_proj = 100
                n_sims_final = 2000
                
                # Recalculamos para graficar
                sel_f = np.random.choice(vals, size=(n_sims_final, n_trades_proj), replace=True)
                rets_f = sel_f * mejor_r
                # Insertamos columna de 0s para el capital inicial
                curves_f = np.zeros((n_sims_final, n_trades_proj + 1))
                curves_f[:,0] = capital_inicial
                curves_f[:,1:] = capital_inicial * np.cumprod(1 + rets_f/100, axis=1)
                
                peaks_f = np.maximum.accumulate(curves_f, axis=1)
                dds_f = (curves_f - peaks_f)/peaks_f
                dds_finales = dds_f.min(axis=1) * -100
                peor_caso = np.percentile(dds_finales, 95)
                mediana_final = np.median(curves_f[:,-1])

                # KPIs
                k1, k2, k3 = st.columns(3)
                k1.metric("Riesgo Sugerido", f"{mejor_r:.2f}%", f"Kelly: {mejor_r/kelly:.2f}x")
                k2.metric("Proyección Mediana", f"${mediana_final:,.0f}", f"+{((mediana_final-capital_inicial)/capital_inicial)*100:.1f}%")
                k3.metric("Riesgo Ruina (95%)", f"{peor_caso:.2f}%", f"Límite: {dd_tolerado}%", delta_color="inverse")

                # GRÁFICOS
                plt.style.use('dark_background')
                fig = plt.figure(figsize=(14, 8))
                gs = fig.add_gridspec(2, 2)
                
                # 1. Equity
                ax1 = fig.add_subplot(gs[0, 0])
                ax1.plot(curves_f[:100].T, color='gray', alpha=0.1)
                ax1.plot(np.median(curves_f, axis=0), color='#00ff41', linewidth=2)
                ax1.set_title("Proyección Montecarlo ($)")
                
                # 2. DD
                ax2 = fig.add_subplot(gs[0, 1])
                ax2.hist(dds_finales, bins=30, color='#ff0055', alpha=0.7)
                ax2.axvline(peor_caso, color='white', linestyle='--')
                ax2.set_title("Distribución de Drawdowns")
                
                # 3. ROI Dist
                ax3 = fig.add_subplot(gs[1, 0])
                roi_vals = ((curves_f[:,-1] - capital_inicial)/capital_inicial)*100
                ax3.hist(roi_vals, bins=40, color='#ffaa00', alpha=0.7)
                ax3.axvline(np.median(roi_vals), color='#00ff41', linestyle='--')
                ax3.set_title("Distribución de Retornos (%)")
                
                # 4. Curva Real R (Data Sim)
                ax4 = fig.add_subplot(gs[1, 1])
                real_r_curve = np.cumsum(vals)
                ax4.plot(real_r_curve, color='#00e5ff', marker='o', markersize=3)
                ax4.set_title(f"Historial R ({real_r_curve[-1]:.1f}R)")
                
                plt.tight_layout()
                st.pyplot(fig)
                
                # Guardar
                if st.button("💾 Guardar Riesgo en G2"):
                    ws.update_acell('G2', mejor_r/100)
                    st.toast("Guardado!", icon="✅")

            except Exception as e:
                st.error(f"Error en simulación: {e}")


# ==========================================
# PESTAÑA 2: ESTADÍSTICAS REALES (NUEVO)
# ==========================================
with tab_real:
    st.markdown("### 📊 Rendimiento Real (Datos Hoja 'Base')")
    
    if st.button("🔄 ACTUALIZAR DATOS REALES"):
        with st.spinner('Descargando historial completo de la hoja Base...'):
            try:
                # 1. Cargar Datos PnL
                pnl_real = cargar_datos_reales(nombre_archivo)
                
                if len(pnl_real) == 0:
                    st.warning("No se encontraron datos en la columna R de la hoja Base.")
                else:
                    # 2. Cálculos Matemáticos
                    # Curva acumulada
                    equity_curve = np.cumsum(pnl_real)
                    equity_curve = np.insert(equity_curve, 0, 0) # Empezamos en 0
                    
                    # Métricas
                    total_pnl = np.sum(pnl_real)
                    n_trades = len(pnl_real)
                    
                    wins = pnl_real[pnl_real > 0]
                    losses = pnl_real[pnl_real <= 0]
                    
                    win_rate = (len(wins) / n_trades) * 100
                    
                    avg_win = np.mean(wins) if len(wins) > 0 else 0
                    avg_loss = np.abs(np.mean(losses)) if len(losses) > 0 else 0 # Evitar div/0
                    
                    ratio_rb = avg_win / avg_loss if avg_loss > 0 else 0
                    
                    # Cálculo Max Drawdown sobre PnL Acumulado
                    # (Peak - Actual) / Peak no funciona bien con PnL si el PnL es negativo.
                    # Usamos Drawdown absoluto en Dinero y Relativo al pico máximo de ganancia
                    picos = np.maximum.accumulate(equity_curve)
                    # Nota: Calcular DD % sobre PnL solo tiene sentido si asumimos un capital. 
                    # Aquí calcularemos el "Max Drawdown $" (Caída máxima en dólares)
                    caidas_dolares = picos - equity_curve
                    caidas_dolares_porcentual = (((picos - equity_curve)/equity_curve)*100)
                    max_dd_dolares = np.max(caidas_dolares)
                    max_dd_porcentual = np.max(caidas_dolares_porcentual)

                    # 3. Visualización de KPIs
                    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5, col_kpi6  = st.columns(6)
                    
                    col_kpi1.metric("PnL Total", f"${total_pnl:,.2f}", delta_color="normal")
                    col_kpi2.metric("Win Rate", f"{win_rate:.1f}%")
                    col_kpi3.metric("R/B Ratio", f"{ratio_rb:.2f}")
                    col_kpi4.metric("Trades", f"{n_trades}")
                    col_kpi5.metric("Max DD ($)", f"-${max_dd_dolares:,.2f}", help="Máxima caída en dólares desde un pico de ganancias")
                    col_kpi6.metric("Max DD (%)", f" -%{max_dd_porcentual:,.2f}", help="Máxima caída porcentual desde un pico de ganancias")

                    # 4. Gráficos Reales
                    plt.style.use('dark_background')
                    fig_real = plt.figure(figsize=(16, 6))
                    
                    # Gráfico de Área (PnL Acumulado)
                    ax_main = fig_real.add_subplot(111)
                    ax_main.plot(equity_curve, color='#00e5ff', linewidth=2, label='PnL Acumulado')
                    ax_main.fill_between(range(len(equity_curve)), 0, equity_curve, color='#00e5ff', alpha=0.15)
                    
                    # Línea de 0
                    ax_main.axhline(0, color='white', linestyle='-', linewidth=1)
                    
                    # Decoración
                    ax_main.set_title("Curva de Equity Real ($)", fontsize=16, fontweight='bold', color='white')
                    ax_main.set_ylabel("Beneficio/Pérdida ($)", color='white')
                    ax_main.set_xlabel("Número de Trade", color='white')
                    ax_main.grid(color='gray', linestyle=':', alpha=0.3)
                    ax_main.legend()
                    
                    st.pyplot(fig_real)
                    
                    # 5. Tabla de Datos Recientes (Opcional, útil)
                    st.markdown("#### 📝 Últimos 5 Trades")
                    df_recientes = pd.DataFrame(pnl_real[-5:], columns=["PnL ($)"])
                    st.dataframe(df_recientes.style.format("${:.2f}"))

            except Exception as e:
                st.error(f"Error cargando estadísticas: {e}")





