import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import gspread
import pandas as pd
import json
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Trading Dashboard Pro", layout="wide", page_icon="📈")

# Estilo CSS (Dark Mode & Tabs)
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
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

# --- 0. BARRA LATERAL (CONFIGURACIÓN GLOBAL) ---
with st.sidebar:
    st.header("⚙️ Configuración Global")
    
    st.markdown("### 💰 Cuenta")
    capital_inicial = st.number_input("Capital Inicial ($)", value=4000)
    dd_tolerado = st.slider("Max DD Tolerado (Meta %)", 5.0, 30.0, 15.0)
    
    st.markdown("### ☁️ Google Sheets")
    nombre_archivo = st.text_input("Nombre Archivo", "Registro2")
    
    st.markdown("---")
    st.markdown("### 🎲 Datos Simulación")
    nombre_hoja_sim = st.text_input("Pestaña (R-Multiples)", "Hoja 24 ")
    n_simulaciones = st.slider("Simulaciones", 500, 5000, 2000)
    
    st.markdown("---")
    st.info("Nota: La pestaña de Estadísticas Reales buscará automáticamente la hoja 'Base' y la columna 'R'.")


# --- 1. FUNCIONES DE CARGA Y CÁLCULO ---

def obtener_cliente_gspread():
    """Autenticación centralizada"""
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
    hoja_nombre = "Base" 
    columna_letra = "R"
    
    try:
        sh = client.open(archivo)
        ws = sh.worksheet(hoja_nombre)
    except:
        raise Exception(f"No encontré la hoja '{hoja_nombre}' en el archivo '{archivo}'.")
    
    datos_crudos = ws.get(f"{columna_letra}:{columna_letra}")
    pnl_dolares = []
    
    # Saltamos el encabezado
    for fila in datos_crudos[1:]:
        if not fila: continue
        try:
            val_str = str(fila[0]).replace(',', '.').replace('$','').replace('USD','').replace(' ','')
            val = float(val_str)
            pnl_dolares.append(val)
        except:
            continue
            
    return np.array(pnl_dolares)

# --- 2. INTERFAZ DE USUARIO (TABS) ---

tab_sim, tab_real = st.tabs(["🎲 Simulación & Riesgo", "📈 Estadísticas Reales ($)"])

# ==========================================
# PESTAÑA 1: SIMULACIÓN 
# ==========================================
with tab_sim:
    st.markdown("### 🛡️ Optimizador de Riesgo (Kelly + Montecarlo)")
    
    if st.button("🚀 CORRER SIMULACIÓN", type="primary"):
        with st.spinner('Analizando futuros posibles...'):
            try:
                # Carga
                vals, tags, ws = cargar_datos_simulacion(nombre_archivo, nombre_hoja_sim)
                
                # Stats Simples
                wins = vals[np.char.find(tags, 'win') >= 0]
                losses = vals[np.char.find(tags, 'loss') >= 0]
                wr = len(wins)/len(vals) if len(vals)>0 else 0
                payoff = np.mean(wins)/abs(np.mean(losses)) if len(losses)>0 else 0
                kelly = (wr - (1-wr)/payoff)*100
                
                # Optimización
                riesgos = np.linspace(0.1, min(kelly, 25.0), 40)
                mejor_r = 0.1
                for r in riesgos:
                    sel = np.random.choice(vals, size=(500, 100), replace=True)
                    rets = sel * r
                    curves = capital_inicial * np.cumprod(1 + rets/100, axis=1)
                    peaks = np.maximum.accumulate(curves, axis=1)
                    dds = (curves - peaks)/peaks
                    if np.percentile(dds.min(axis=1)*-100, 95) < dd_tolerado:
                        mejor_r = r
                    else: break
                
                # Simulación Final
                n_trades_proj = 100
                sel_f = np.random.choice(vals, size=(n_simulaciones, n_trades_proj), replace=True)
                rets_f = sel_f * mejor_r
                curves_f = np.zeros((n_simulaciones, n_trades_proj + 1))
                capital_inicial = 4000
                curves_f[:,1:] = capital_inicial * np.cumprod(1 + rets_f/100, axis=1)
                
                peaks_f = np.maximum.accumulate(curves_f, axis=1)
                dds_f = (curves_f - peaks_f)/peaks_f
                dds_finales = dds_f.min(axis=1) * -100
                peor_caso = np.percentile(dds_finales, 95)
                mediana_final = np.median(curves_f[:,-1])

                # KPIs Simulación
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
                
                # 4. Curva Real R
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
# PESTAÑA 2: ESTADÍSTICAS REALES (CON DD CHART)
# ==========================================
with tab_real:
    st.markdown("### 📊 Rendimiento Real (Datos Hoja 'Base')")
    
    if st.button("🔄 ACTUALIZAR DATOS REALES"):
        with st.spinner('Procesando historial...'):
            try:
                # 1. Cargar Datos PnL
                pnl_real = cargar_datos_reales(nombre_archivo)
                
                if len(pnl_real) == 0:
                    st.warning("No se encontraron datos en la columna R de la hoja Base.")
                else:
                    # 2. Cálculos Matemáticos
                    
                    # A. Curva de Equity Real ($)
                    equity_curve_usd = np.cumsum(pnl_real)-125
                    equity_curve_total = equity_curve_usd
                    equity_curve_total = np.insert(equity_curve_total, 0)
                    
                    # B. Métricas
                    total_pnl = np.sum(pnl_real)-125
                    n_trades = len(pnl_real)
                    
                    wins = pnl_real[pnl_real > 0]
                    losses = pnl_real[pnl_real <= 0]
                    win_rate = (len(wins) / n_trades) * 100
                    avg_win = np.mean(wins) if len(wins) > 0 else 0
                    avg_loss = np.abs(np.mean(losses)) if len(losses) > 0 else 0
                    ratio_rb = avg_win / avg_loss if avg_loss > 0 else 0
                    
                    # C. Cálculo de Vector de Drawdowns (Para graficar)
                    picos = np.maximum.accumulate(equity_curve_total)
                    drawdowns_pct_vector = (equity_curve_total - picos) / picos * 100
                    
                    # Escalares para métricas
                    max_dd_usd = np.max(picos - equity_curve_total)
                    max_dd_pct = np.min(drawdowns_pct_vector) # Es negativo (ej: -12%)
                    current_dd_pct = drawdowns_pct_vector[-1] # El último valor es el actual
                    
                    # 3. Visualización de KPIs
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    
                    c1.metric("PnL Total", f"${total_pnl:,.2f}", delta_color="normal")
                    c2.metric("Win Rate", f"{win_rate:.1f}%")
                    c3.metric("R/B Ratio", f"{ratio_rb:.2f}")
                    c4.metric("Trades", f"{n_trades}")
                    c5.metric("Max DD ($)", f"-${max_dd_usd:,.2f}")
                    # Mostramos el Max DD % en rojo
                    c6.metric("Max DD (%)", f"{max_dd_pct:.2f}%", f"Actual: {current_dd_pct:.2f}%", delta_color="inverse")

                    # 4. GRÁFICOS REALES (SUBPLOT UNDERWATER)
                    plt.style.use('dark_background')
                    
                    # Creamos figura con 2 paneles (Altura 3:1)
                    fig_real, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(16, 8), gridspec_kw={'height_ratios': [3, 1]})
                    
                    # PANEL 1: EQUITY ($)
                    ax1.plot(equity_curve_total, color='#00e5ff', linewidth=2, label='Balance')
                    ax1.fill_between(range(len(equity_curve_total)), capital_inicial, equity_curve_total, color='#00e5ff', alpha=0.1)
                    ax1.axhline(capital_inicial, color='white', linestyle='--', linewidth=1, label='Capital Inicial')
                    ax1.set_title(f"Crecimiento de Cuenta (Balance Actual: ${equity_curve_total[-1]:,.2f})", fontsize=14, fontweight='bold', color='white')
                    ax1.set_ylabel("Balance ($)", color='white')
                    ax1.grid(color='gray', linestyle=':', alpha=0.3)
                    ax1.legend()
                    
                    # PANEL 2: DRAWDOWN (%)
                    # Pintamos de rojo/rosa el área de drawdown
                    ax2.plot(drawdowns_pct_vector, color='#ff0055', linewidth=1)
                    ax2.fill_between(range(len(drawdowns_pct_vector)), 0, drawdowns_pct_vector, color='#ff0055', alpha=0.3)
                    ax2.axhline(0, color='gray', linestyle='-', linewidth=0.5)
                    ax2.set_ylabel("Drawdown %", color='white')
                    ax2.set_xlabel("Número de Trade", color='white')
                    ax2.set_title(f"Profundidad de Drawdown (Max: {max_dd_pct:.2f}% | Actual: {current_dd_pct:.2f}%)", fontsize=10, color='#ff0055')
                    ax2.grid(color='gray', linestyle=':', alpha=0.3)
                    
                    # Ajustamos espacio entre gráficas
                    plt.subplots_adjust(hspace=0.1)
                    
                    st.pyplot(fig_real)
                    
                    # 5. Tabla
                    st.markdown("#### 📝 Últimos 5 Trades")
                    df_recientes = pd.DataFrame(pnl_real[-5:], columns=["PnL ($)"])
                    st.dataframe(df_recientes.style.format("${:.2f}"))

            except Exception as e:
                st.error(f"Error cargando estadísticas: {e}")

